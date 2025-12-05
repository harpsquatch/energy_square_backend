"""
P2P Marketplace API Endpoints

Endpoints for P2P energy trading: offers, requests, trades, and settlements.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.infrastructure.marketplace_service import get_marketplace_service
from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.background_service import get_background_service
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy service initialization
_model_service = None
_simulation_engine = None


def get_model_service():
    """Get or create model service (lazy initialization)."""
    global _model_service
    if _model_service is None:
        _model_service = CommunityModelService(watch_for_changes=True)
    return _model_service


def get_simulation_engine():
    """Get or create simulation engine (lazy initialization)."""
    global _simulation_engine
    if _simulation_engine is None:
        model_service = get_model_service()
        _simulation_engine = CommunitySimulationEngine(model_service)
    return _simulation_engine


# Request/Response models
class CreateOfferRequest(BaseModel):
    """Request to create a trade offer."""
    seller_id: str = Field(..., description="Prosumer member ID")
    available_surplus_kw: float = Field(..., gt=0, description="Available surplus energy in kW")
    price_per_kwh: float = Field(..., gt=0, description="Price per kWh (USD)")
    time_blocks: List[datetime] = Field(..., min_items=1, description="Time blocks when energy is available")


class CreateRequestRequest(BaseModel):
    """Request to create a trade request."""
    buyer_id: str = Field(..., description="Consumer member ID")
    required_energy_kwh: float = Field(..., gt=0, description="Required energy in kWh")
    max_price_per_kwh: float = Field(..., gt=0, description="Maximum price willing to pay (USD)")
    time_blocks: List[datetime] = Field(..., min_items=1, description="Time blocks when energy is needed")
    preferred_seller_id: Optional[str] = Field(None, description="Optional preferred seller for preferential matching")


class MatchTradeRequest(BaseModel):
    """Request to match a trade offer with a request."""
    offer_id: str = Field(..., description="Trade offer ID")
    request_id: str = Field(..., description="Trade request ID")
    energy_kwh: float = Field(..., gt=0, description="Energy to trade (kWh)")


@router.post("/offers")
async def create_trade_offer(request: CreateOfferRequest):
    """
    Create a trade offer from a prosumer.
    
    Prosumers can list their available surplus energy for sale.
    """
    try:
        marketplace_service = get_marketplace_service()
        
        # Get timezone from model
        model_service = get_model_service()
        model = model_service.get_model()
        if model:
            tz = ZoneInfo(model.community.timezone)
        else:
            tz = ZoneInfo("UTC")
        
        # Ensure time blocks are timezone-aware and normalized to hour boundary
        time_blocks = []
        for tb in request.time_blocks:
            if isinstance(tb, str):
                tb = datetime.fromisoformat(tb)
            if tb.tzinfo is None:
                tb = tb.replace(tzinfo=tz)
            # Normalize to hour boundary (remove minutes, seconds, microseconds)
            tb = tb.replace(minute=0, second=0, microsecond=0)
            time_blocks.append(tb)
        
        offer_id = marketplace_service.create_trade_offer(
            seller_id=request.seller_id,
            available_surplus_kw=request.available_surplus_kw,
            price_per_kwh=request.price_per_kwh,
            time_blocks=time_blocks
        )
        
        return {
            "status": "success",
            "offer_id": offer_id,
            "message": "Trade offer created successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating trade offer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create trade offer: {str(e)}"
        )


@router.get("/offers")
async def get_offers():
    """
    Get all active trade offers.
    
    Returns list of available offers from prosumers.
    """
    try:
        marketplace_service = get_marketplace_service()
        offers = marketplace_service.get_active_offers()
        
        return {
            "status": "success",
            "count": len(offers),
            "offers": offers
        }
    except Exception as e:
        logger.error(f"Error getting trade offers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trade offers: {str(e)}"
        )


@router.post("/requests")
async def create_trade_request(request: CreateRequestRequest):
    """
    Create a trade request from a consumer.
    
    Consumers can request energy from prosumers.
    """
    try:
        marketplace_service = get_marketplace_service()
        
        # Get timezone from model
        model_service = get_model_service()
        model = model_service.get_model()
        if model:
            tz = ZoneInfo(model.community.timezone)
        else:
            tz = ZoneInfo("UTC")
        
        # Ensure time blocks are timezone-aware and normalized to hour boundary
        time_blocks = []
        for tb in request.time_blocks:
            if isinstance(tb, str):
                tb = datetime.fromisoformat(tb)
            if tb.tzinfo is None:
                tb = tb.replace(tzinfo=tz)
            # Normalize to hour boundary (remove minutes, seconds, microseconds)
            tb = tb.replace(minute=0, second=0, microsecond=0)
            time_blocks.append(tb)
        
        request_id = marketplace_service.create_trade_request(
            buyer_id=request.buyer_id,
            required_energy_kwh=request.required_energy_kwh,
            max_price_per_kwh=request.max_price_per_kwh,
            time_blocks=time_blocks,
            preferred_seller_id=request.preferred_seller_id
        )
        
        return {
            "status": "success",
            "request_id": request_id,
            "message": "Trade request created successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating trade request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create trade request: {str(e)}"
        )


@router.get("/requests")
async def get_requests():
    """
    Get all active trade requests.
    
    Returns list of active requests from consumers.
    """
    try:
        marketplace_service = get_marketplace_service()
        requests = marketplace_service.get_active_requests()
        
        return {
            "status": "success",
            "count": len(requests),
            "requests": requests
        }
    except Exception as e:
        logger.error(f"Error getting trade requests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trade requests: {str(e)}"
        )


@router.post("/trades")
async def execute_trade(request: MatchTradeRequest):
    """
    Match a trade offer with a request and execute the trade.
    
    This creates a transaction and immediately executes it.
    """
    try:
        marketplace_service = get_marketplace_service()
        
        # Match the trade (creates transaction)
        transaction_id = marketplace_service.match_trade(
            offer_id=request.offer_id,
            request_id=request.request_id,
            energy_kwh=request.energy_kwh
        )
        
        # Execute the transaction immediately
        success = marketplace_service.execute_trade(transaction_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to execute trade"
            )
        
        # Trigger immediate simulation update to reflect P2P trade
        try:
            background_service = get_background_service()
            background_service.trigger_immediate_update()
        except Exception as e:
            logger.warning(f"Could not trigger immediate update: {e}")
        
        return {
            "status": "success",
            "transaction_id": transaction_id,
            "message": "Trade executed successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error executing trade: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute trade: {str(e)}"
        )


@router.get("/trades")
async def get_trades(
    member_id: Optional[str] = None,
    status_filter: Optional[str] = None
):
    """
    Get all trades with optional filters.
    
    Args:
        member_id: Filter by member ID (seller or buyer)
        status_filter: Filter by status (pending, executed, cancelled)
    """
    try:
        marketplace_service = get_marketplace_service()
        
        if member_id:
            trades = marketplace_service.get_member_trades(member_id)
        else:
            trades = await marketplace_service.get_all_transactions_async()
        
        # Apply status filter if provided
        if status_filter:
            trades = [t for t in trades if t.get("status") == status_filter]
        
        return {
            "status": "success",
            "count": len(trades),
            "trades": trades
        }
    except Exception as e:
        logger.error(f"Error getting trades: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trades: {str(e)}"
        )


@router.get("/trades/{member_id}")
async def get_member_trades(member_id: str):
    """
    Get all trades for a specific member.
    
    Returns trades where the member is either seller or buyer.
    """
    try:
        marketplace_service = get_marketplace_service()
        trades = marketplace_service.get_member_trades(member_id)
        
        return {
            "status": "success",
            "member_id": member_id,
            "count": len(trades),
            "trades": trades
        }
    except Exception as e:
        logger.error(f"Error getting member trades: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get member trades: {str(e)}"
        )


@router.get("/surplus/{member_id}")
async def get_member_surplus(member_id: str):
    """
    Get current available surplus for a member.
    
    Calculates surplus from simulation engine based on current generation and consumption.
    """
    try:
        model_service = get_model_service()
        model = model_service.get_model()
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Community model not found"
            )
        
        # Find member
        member = None
        for m in model.members:
            if m.member_id == member_id:
                member = m
                break
        
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {member_id} not found"
            )
        
        # Get current time
        tz = ZoneInfo(model.community.timezone)
        current_time = datetime.now(tz)
        
        # Run simulation for this member
        simulation_engine = get_simulation_engine()
        member_result = simulation_engine.simulate_member(member, current_time)
        
        # Calculate available surplus (grid_export_kw)
        available_surplus_kw = member_result.get("grid_export_kw", 0.0)
        
        return {
            "status": "success",
            "member_id": member_id,
            "available_surplus_kw": round(available_surplus_kw, 3),
            "current_generation_kw": member_result.get("solar_generation_kw", 0.0),
            "current_consumption_kw": member_result.get("consumption_kw", 0.0),
            "net_balance_kw": member_result.get("net_balance_kw", 0.0),
            "timestamp": current_time.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting member surplus: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get member surplus: {str(e)}"
        )


@router.get("/stats")
async def get_marketplace_stats():
    """
    Get marketplace statistics including dynamic pricing.
    
    Returns aggregate statistics about trades, offers, and requests.
    Also includes current price (calculated from demand/supply) and 24h price history.
    """
    try:
        marketplace_service = get_marketplace_service()
        
        # Get all transactions
        all_trades = await marketplace_service.get_all_transactions_async()
        
        # Calculate statistics
        total_trades = len(all_trades)
        executed_trades = [t for t in all_trades if t.get("status") == "executed"]
        total_energy_traded = sum(t.get("energy_kwh", 0) for t in executed_trades)
        total_value = sum(t.get("gross_amount", 0) for t in executed_trades)
        total_service_fees = sum(t.get("service_fee", 0) for t in executed_trades)
        
        # Get active offers and requests
        active_offers = marketplace_service.get_active_offers()
        active_requests = marketplace_service.get_active_requests()
        
        # Calculate available surplus from offers
        total_available_surplus = sum(o.get("available_surplus_kw", 0) for o in active_offers)
        
        # Calculate total demand from requests
        total_demand = sum(r.get("required_energy_kwh", 0) for r in active_requests)
        
        # Calculate current price from demand/supply
        current_price = await marketplace_service.calculate_current_price(active_offers, active_requests)
        
        # Store current price snapshot in MongoDB
        await marketplace_service.save_price_snapshot(current_price)
        
        # Get 24h price history
        price_history = await marketplace_service.get_price_history_24h()
        
        # Calculate 24h stats
        prices_24h = [p.get("price", 0) for p in price_history if p.get("price", 0) > 0]
        min_24h = min(prices_24h) if prices_24h else current_price
        max_24h = max(prices_24h) if prices_24h else current_price
        avg_24h = sum(prices_24h) / len(prices_24h) if prices_24h else current_price
        
        return {
            "status": "success",
            "statistics": {
                "total_trades": total_trades,
                "executed_trades": len(executed_trades),
                "total_energy_traded_kwh": round(total_energy_traded, 3),
                "total_value_usd": round(total_value, 2),
                "total_service_fees_usd": round(total_service_fees, 2),
                "active_offers": len(active_offers),
                "active_requests": len(active_requests),
                "total_available_surplus_kw": round(total_available_surplus, 3),
                "total_demand_kwh": round(total_demand, 3),
                "current_price": round(current_price, 4),
                "price_24h": {
                    "min": round(min_24h, 4),
                    "max": round(max_24h, 4),
                    "average": round(avg_24h, 4),
                    "current": round(current_price, 4)
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting marketplace stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get marketplace stats: {str(e)}"
        )


@router.get("/user/{member_id}/profile")
async def get_user_profile(member_id: str):
    """
    Get user profile and wallet data from MongoDB.
    
    Returns user profile (name, role, tier, rating) and wallet (energy credits, cash balance).
    """
    try:
        from app.db.database import get_database, Collections
        from datetime import datetime
        
        db = await get_database()
        users_collection = db[Collections.USERS]
        
        # Get user from MongoDB
        user_doc = await users_collection.find_one({"member_id": member_id})
        
        if not user_doc:
            # Return default profile if user not found
            return {
                "status": "success",
                "profile": {
                    "id": member_id,
                    "name": f"User {member_id}",
                    "role": "consumer",
                    "tier": "bronze",
                    "verified": False,
                    "rating": 0.0,
                    "total_trades": 0,
                    "success_rate": 0.0,
                    "smart_meter_connected": False,
                    "device_certification": False
                },
                "wallet": {
                    "energy_credits": 0.0,
                    "cash_balance": 0.0,
                    "pending_credits": 0.0,
                    "pending_cash": 0.0
                }
            }
        
        # Get user's trade statistics
        marketplace_service = get_marketplace_service()
        all_trades = await marketplace_service.get_all_transactions_async()
        user_trades = [t for t in all_trades if t.get("seller_id") == member_id or t.get("buyer_id") == member_id]
        executed_trades = [t for t in user_trades if t.get("status") == "executed"]
        
        # Get energy credit balance from MongoDB (primary currency)
        marketplace_service = get_marketplace_service()
        energy_credit_balance = await marketplace_service.get_energy_credit_balance_async(member_id)
        
        # Get cash balance from withdrawals (credits converted to cash)
        from app.db.database import get_database, Collections
        db_credits = await get_database()
        credits_collection = db_credits[Collections.ENERGY_CREDITS]
        credits_doc = await credits_collection.find_one({"member_id": member_id})
        total_withdrawn = 0.0
        if credits_doc:
            withdrawals = [t for t in credits_doc.get("transactions", []) if t.get("type") == "withdrawal"]
            total_withdrawn = sum(float(t.get("cash_amount", 0)) for t in withdrawals)
        
        # Calculate wallet from executed trades (for display purposes)
        total_energy_sold = sum(t.get("energy_kwh", 0) for t in executed_trades if t.get("seller_id") == member_id)
        total_energy_bought = sum(t.get("energy_kwh", 0) for t in executed_trades if t.get("buyer_id") == member_id)
        total_revenue = sum(t.get("seller_amount", 0) for t in executed_trades if t.get("seller_id") == member_id)
        total_spent = sum(t.get("buyer_amount", 0) for t in executed_trades if t.get("buyer_id") == member_id)
        
        # Calculate success rate (executed vs total)
        success_rate = (len(executed_trades) / len(user_trades) * 100) if user_trades else 0.0
        
        # Determine role based on trades
        role = "prosumer" if total_energy_sold > 0 and total_energy_bought > 0 else ("producer" if total_energy_sold > 0 else "consumer")
        
        # Determine tier based on total trades
        total_trades_count = len(executed_trades)
        if total_trades_count >= 100:
            tier = "platinum"
        elif total_trades_count >= 50:
            tier = "gold"
        elif total_trades_count >= 20:
            tier = "silver"
        else:
            tier = "bronze"
        
        # Calculate rating (simple: based on success rate)
        rating = min(5.0, max(0.0, (success_rate / 20.0)))  # Scale success rate to 0-5
        
        profile = {
            "id": member_id,
            "name": user_doc.get("full_name") or user_doc.get("name") or f"User {member_id}",
            "role": role,
            "tier": tier,
            "verified": user_doc.get("verified", False),
            "rating": round(rating, 1),
            "total_trades": total_trades_count,
            "success_rate": round(success_rate, 1),
            "smart_meter_connected": user_doc.get("smart_meter_connected", False),
            "device_certification": user_doc.get("device_certification", False)
        }
        
        wallet = {
            "energy_credits": round(energy_credit_balance, 2),  # Current energy credit balance from MongoDB
            "cash_balance": round(total_withdrawn, 2),  # Total cash withdrawn from credits
            "pending_credits": 0.0,  # Could be calculated from pending trades
            "pending_cash": 0.0  # Could be calculated from pending trades
        }
        
        return {
            "status": "success",
            "profile": profile,
            "wallet": wallet
        }
    except Exception as e:
        logger.error(f"Error getting user profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user profile: {str(e)}"
        )


@router.post("/user/{member_id}/withdraw")
async def withdraw_energy_credits_endpoint(member_id: str, amount: float):
    """
    Withdraw energy credits as cash.
    
    Converts energy credits to real money (1:1 conversion).
    """
    try:
        marketplace_service = get_marketplace_service()
        
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Withdrawal amount must be greater than 0"
            )
        
        result = await marketplace_service.withdraw_energy_credits(member_id, amount)
        
        return {
            "status": "success",
            "withdrawal": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error withdrawing energy credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to withdraw energy credits: {str(e)}"
        )


@router.post("/user/{member_id}/buy-credits")
async def buy_energy_credits_endpoint(member_id: str, amount: float):
    """
    Buy energy credits with cash.
    
    Converts real money to energy credits (1:1 conversion: $1 = 1 credit).
    """
    try:
        marketplace_service = get_marketplace_service()
        
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Purchase amount must be greater than 0"
            )
        
        result = await marketplace_service.buy_energy_credits(member_id, amount)
        
        return {
            "status": "success",
            "purchase": result
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error buying energy credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to buy energy credits: {str(e)}"
        )


@router.get("/user/{member_id}/credits")
async def get_energy_credits(member_id: str):
    """
    Get energy credit balance and transaction history for a member.
    """
    try:
        marketplace_service = get_marketplace_service()
        
        balance = await marketplace_service.get_energy_credit_balance_async(member_id)
        
        # Get transaction history from MongoDB
        from app.db.database import get_database, Collections
        db = await get_database()
        credits_collection = db[Collections.ENERGY_CREDITS]
        
        doc = await credits_collection.find_one({"member_id": member_id})
        transactions = doc.get("transactions", []) if doc else []
        
        return {
            "status": "success",
            "member_id": member_id,
            "balance": balance,
            "transactions": transactions[-20:]  # Last 20 transactions
        }
    except Exception as e:
        logger.error(f"Error getting energy credits: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get energy credits: {str(e)}"
        )

