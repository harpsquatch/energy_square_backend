"""
User Dashboard Service

Uses the community simulation engine to generate user dashboard data from normalized patterns.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine

logger = logging.getLogger(__name__)


class UserDashboardService:
    """Service to generate user dashboard data using the simulation engine."""
    
    def __init__(self):
        """Initialize the service and setup simulation engine."""
        # Initialize model service
        self.model_service = CommunityModelService(watch_for_changes=True)
        
        # Try to use background service, fallback to direct engine
        self.background_service = None
        self.simulation_engine = None
        self._use_background = False
        
        try:
            from app.services.infrastructure.background_service import get_background_service
            self.background_service = get_background_service()
            # Don't access simulation_engine directly - background service uses lazy initialization
            self._use_background = True
            logger.info("UserDashboardService initialized with background simulation service")
        except Exception as e:
            logger.warning(f"Background service not available, using direct engine: {e}")
            self.simulation_engine = CommunitySimulationEngine(
                model_service=self.model_service
            )
            self._use_background = False
            logger.info("UserDashboardService initialized with simulation engine")
    
    def get_user_data_at_timestamp(self, user_id: str, target_dt: datetime) -> Optional[Dict[str, Any]]:
        """Get user data at a specific timestamp from simulation engine."""
        try:
            model = self.model_service.get_model()
            if model is None:
                logger.warning("Model not loaded")
                return None
            
            # Find member by ID
            member = None
            for m in model.members:
                if m.member_id == user_id:
                    member = m
                    break
            
            if member is None:
                logger.warning(f"Member {user_id} not found in community model")
                return None
            
            # Use cached data from background service if available
            if self._use_background and self.background_service:
                result = self.background_service.get_member_data(user_id, target_dt)
                if result:
                    return self._convert_member_to_user_data(result, member, target_dt)
            
            # Fallback to direct simulation - ensure engine is initialized
            if self.simulation_engine is None:
                self.simulation_engine = CommunitySimulationEngine(model_service=self.model_service)
            result = self.simulation_engine.simulate_member(member, target_dt)
            
            # Convert to user dashboard format
            return self._convert_member_to_user_data(result, member, target_dt)
        except Exception as e:
            logger.error(f"Error getting user data at timestamp: {e}", exc_info=True)
            return None
    
    def _convert_member_to_user_data(self, member_result: Dict[str, Any], member, timestamp: datetime) -> Dict[str, Any]:
        """Convert simulation member result to user dashboard format."""
        battery_soc = member_result.get('battery_soc', 0.0)
        battery_capacity = member.assets.battery_capacity_kwh
        battery_available = battery_capacity * battery_soc
        
        # Calculate carbon offset
        solar_generation_kw = member_result.get('solar_generation_kw', 0.0)
        model = self.model_service.get_model()
        if not model:
            carbon_offset_kg = 0.0
        else:
            carbon_offset_kg = solar_generation_kw * model.community_control.carbon_offset_factor_kg_per_kwh
        
        return {
            'user_id': member.member_id,
            'timestamp': timestamp.isoformat(),
            'solar_generation_kw': member_result.get('solar_generation_kw', 0.0),
            'consumption_kw': member_result.get('consumption_kw', 0.0),
            'battery_power_kw': member_result.get('battery_power_kw', 0.0),
            'battery_soc_pct': battery_soc * 100.0,
            'battery_capacity_kwh': battery_capacity,
            'battery_available_kwh': battery_available,
            'net_balance_kw': member_result.get('net_balance_kw', 0.0),
            'grid_export_kw': member_result.get('grid_export_kw', 0.0),
            'grid_import_kw': member_result.get('grid_import_kw', 0.0),
            'carbon_offset_kg': carbon_offset_kg,
            'user_type': member.member_type.value,
        }
    
    def _get_period_totals(self, user_id: str, start_dt: datetime, end_dt: datetime) -> Dict[str, float]:
        """Get aggregated totals for a user over a time period."""
        totals = {
            'solar_kwh': 0.0,
            'consumption_kwh': 0.0,
            'carbon_offset_kg': 0.0,
        }
        
        try:
            model = self.model_service.get_model()
            if model is None:
                return totals
            
            # Find member
            member = None
            for m in model.members:
                if m.member_id == user_id:
                    member = m
                    break
            
            if member is None:
                return totals
            
            # Sample at hourly intervals
            current_hour = start_dt.replace(minute=0, second=0, microsecond=0)
            
            # Limit to max hours to prevent hanging (max 48 hours)
            max_hours = 48
            iteration = 0
            
            while current_hour < end_dt and iteration < max_hours:
                try:
                    result = self.simulation_engine.simulate_member(member, current_hour)
                    if result:
                        interval_hours = 1.0
                        totals['solar_kwh'] += result.get('solar_generation_kw', 0) * interval_hours
                        totals['consumption_kwh'] += result.get('consumption_kw', 0) * interval_hours
                        model = self.model_service.get_model()
                        if model:
                            totals['carbon_offset_kg'] += result.get('solar_generation_kw', 0) * model.community_control.carbon_offset_factor_kg_per_kwh * interval_hours
                except Exception as e:
                    logger.warning(f"Error simulating at {current_hour}: {e}")
                
                current_hour += timedelta(hours=1)
                iteration += 1
        except Exception as e:
            logger.error(f"Error in _get_period_totals: {e}", exc_info=True)
        
        return totals
    
    async def get_user_dashboard(self, user_id: str, include_users: bool = False) -> Dict[str, Any]:
        """
        Get complete user dashboard data for a specific user.
        
        Uses the community simulation engine to generate real-time data from
        normalized patterns based on community model configuration.
        
        Args:
            user_id: The user ID (member_id) to fetch dashboard data for
            include_users: If True, include the list of all available users in the response
        
        Returns data matching the frontend's expected structure.
        """
        model = self.model_service.get_model()
        if model is None:
            logger.warning("Model not loaded, returning defaults")
            return self._default_user_data(user_id)
        
        now = datetime.now(ZoneInfo(model.community.timezone))
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)
        
        # Get current user data
        current_data = self.get_user_data_at_timestamp(user_id, now)
        
        if not current_data:
            logger.warning(f"No current data found for user {user_id}, returning defaults")
            return self._default_user_data(user_id)
        
        # Get today's totals - ONLY use background service cached data, don't calculate synchronously
        today_data = {'solar_kwh': 0.0, 'consumption_kwh': 0.0, 'carbon_offset_kg': 0.0}
        month_data = {'solar_kwh': 0.0, 'consumption_kwh': 0.0, 'carbon_offset_kg': 0.0}
        
        # Only try to get totals from background service if available (cached data)
        # Don't calculate synchronously to avoid hanging
        if self._use_background and self.background_service:
            try:
                # Get hourly history from background service for this member
                # For today: last 24 hours, for month: last 30 days (limited to available cache)
                hours_requested = int(min(720, (now - today_start).total_seconds() / 3600 + 24))
                history = self.background_service.get_hourly_history(member_id=user_id, hours=hours_requested)
                logger.info(f"Requested {hours_requested} hours of history for {user_id}, got {len(history) if history else 0} entries")
                if history:
                    for entry in history:
                        data = entry.get('data', {})
                        timestamp_str = entry.get('timestamp', '')
                        if not timestamp_str:
                            continue
                        try:
                            # Parse ISO timestamp string
                            entry_timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except Exception:
                            continue
                        
                        interval_hours = 1.0
                        solar_kwh = data.get('solar_generation_kw', 0) * interval_hours
                        consumption_kwh = data.get('consumption_kw', 0) * interval_hours
                        
                        # Today's totals (since today_start)
                        if entry_timestamp >= today_start:
                            today_data['solar_kwh'] += solar_kwh
                            today_data['consumption_kwh'] += consumption_kwh
                            if model:
                                today_data['carbon_offset_kg'] += solar_kwh * model.community_control.carbon_offset_factor_kg_per_kwh
                        
                        # Month totals (since month_start)
                        if entry_timestamp >= month_start:
                            month_data['solar_kwh'] += solar_kwh
                            month_data['consumption_kwh'] += consumption_kwh
                            if model:
                                month_data['carbon_offset_kg'] += solar_kwh * model.community_control.carbon_offset_factor_kg_per_kwh
            except Exception as e:
                logger.debug(f"Could not get totals from background service: {e}")
                # Continue with zeros - background service will populate this over time
        
        # Get member profile info
        member = None
        for m in model.members:
            if m.member_id == user_id:
                member = m
                break
        
        profile_info = self._get_user_profile_info(member) if member else {}
        
        # Get P2P trade information for current hour
        p2p_trades_info = self._get_p2p_trades_info(user_id, now)
        
        # Build response matching frontend expectations
        response = {
            "data_available": True,
            "message": None,
            # Current metrics (daily totals in kWh)
            "produced_kwh_today": round(today_data.get('solar_kwh', 0), 2),
            "consumed_kwh_today": round(today_data.get('consumption_kwh', 0), 2),
            "net_kwh_today": round(today_data.get('solar_kwh', 0) - today_data.get('consumption_kwh', 0), 2),
            # Current instantaneous values (in kW)
            "current_generation_kw": round(current_data.get('solar_generation_kw', 0), 2),
            "current_consumption_kw": round(current_data.get('consumption_kw', 0), 2),
            "current_net_balance_kw": round(abs(current_data.get('net_balance_kw', 0)), 2),
            
            # Grid and P2P energy flow
            "grid_import_kw": round(current_data.get('grid_import_kw', 0), 2),
            "grid_export_kw": round(current_data.get('grid_export_kw', 0), 2),
            "grid_import_rate_usd_per_kwh": model.community_control.import_rate_usd_per_kwh if model else 0.30,
            "grid_export_rate_usd_per_kwh": model.community_control.export_rate_usd_per_kwh if model else 0.25,
            
            # P2P trade information
            "p2p_trades": p2p_trades_info,
            "p2p_bought_kw": sum(t.get("energy_kwh", 0) for t in p2p_trades_info.get("buying_from", [])),
            "p2p_sold_kw": sum(t.get("energy_kwh", 0) for t in p2p_trades_info.get("selling_to", [])),
            
            # P2P financial impact
            "p2p_savings_today": self._calculate_p2p_savings(p2p_trades_info, model.community_control.import_rate_usd_per_kwh if model else 0.30),
            "p2p_revenue_today": sum(t.get("total_revenue", 0) for t in p2p_trades_info.get("selling_to", [])),
            
            # Battery status
            "battery_soc_pct": round(current_data.get('battery_soc_pct', 0), 1),
            "battery_capacity_kwh": round(current_data.get('battery_capacity_kwh', 0), 2),
            "battery_available_kwh": round(current_data.get('battery_available_kwh', 0), 2),
            
            # Financials - to be populated by marketplace service
            "credits_today": 0.0,
            "total_credits": 0.0,
            "current_rate_eur_kwh": model.community_control.import_rate_usd_per_kwh if model else 0.30,
            "recent_transactions": [],
            
            # Carbon offset
            "carbon_offset_today_kg": round(today_data.get('carbon_offset_kg', 0), 2),
            "carbon_offset_month_kg": round(month_data.get('carbon_offset_kg', 0), 2),
            "carbon_offset_community_rank": 0,
            
            # Demand Response - to be populated by DR service
            "dr_engagement": 0.0,
            "dr_events_participated": 0,
            "dr_total_rewards_eur": 0.0,
            
            # User profile
            "location": profile_info.get('location', 'Community Member'),
            "solar_capacity_kw": round(profile_info.get('solar_capacity_kw', 0), 2),
            
            # Alerts - to be populated by alerts service
            "user_alerts": [],
        }
        
        # Optionally include users list
        if include_users:
            response["available_users"] = self.list_available_users()
        
        return response
    
    def _get_p2p_trades_info(self, user_id: str, current_time: datetime) -> Dict[str, Any]:
        """Get P2P trade information for the current user at the current time."""
        try:
            from app.services.infrastructure.marketplace_service import get_marketplace_service
            
            marketplace_service = get_marketplace_service()
            
            # Get all trades for this user
            all_trades = marketplace_service.get_member_trades(user_id)
            
            # Filter for current hour trades (convert to UTC for comparison)
            if current_time.tzinfo is None:
                current_hour = current_time.replace(tzinfo=ZoneInfo("UTC"))
            else:
                current_hour = current_time.astimezone(ZoneInfo("UTC"))
            current_hour = current_hour.replace(minute=0, second=0, microsecond=0)
            
            buying_from = []  # Trades where user is buyer
            selling_to = []   # Trades where user is seller
            
            for trade in all_trades:
                if trade.get("status") != "executed":
                    continue
                
                # Check if trade time block matches current hour (both in UTC)
                trade_time = trade.get("time_block")
                if isinstance(trade_time, str):
                    trade_time = datetime.fromisoformat(trade_time)
                
                # Ensure timezone-aware and convert to UTC
                if trade_time.tzinfo is None:
                    trade_time = trade_time.replace(tzinfo=ZoneInfo("UTC"))
                else:
                    trade_time = trade_time.astimezone(ZoneInfo("UTC"))
                
                trade_hour = trade_time.replace(minute=0, second=0, microsecond=0)
                
                logger.debug(
                    f"P2P trade check for {user_id}: trade_hour={trade_hour.isoformat()}, "
                    f"current_hour={current_hour.isoformat()}, match={trade_hour == current_hour}"
                )
                
                if trade_hour == current_hour:
                    if trade.get("buyer_id") == user_id:
                        # User is buying from someone
                        buying_from.append({
                            "seller_id": trade.get("seller_id"),
                            "energy_kwh": trade.get("energy_kwh", 0),
                            "price_per_kwh": trade.get("price_per_kwh", 0),
                            "total_cost": trade.get("buyer_amount", 0),
                            "transaction_id": trade.get("transaction_id"),
                            "timestamp": trade.get("executed_at", trade.get("created_at"))
                        })
                    elif trade.get("seller_id") == user_id:
                        # User is selling to someone
                        selling_to.append({
                            "buyer_id": trade.get("buyer_id"),
                            "energy_kwh": trade.get("energy_kwh", 0),
                            "price_per_kwh": trade.get("price_per_kwh", 0),
                            "total_revenue": trade.get("seller_amount", 0),
                            "transaction_id": trade.get("transaction_id"),
                            "timestamp": trade.get("executed_at", trade.get("created_at"))
                        })
            
            logger.info(
                f"P2P trades for {user_id} at {current_hour.isoformat()}: "
                f"buying_from={len(buying_from)}, selling_to={len(selling_to)}"
            )
            
            return {
                "buying_from": buying_from,
                "selling_to": selling_to
            }
        except Exception as e:
            logger.error(f"Error getting P2P trades info: {e}", exc_info=True)
            return {
                "buying_from": [],
                "selling_to": []
            }
    
    def _calculate_p2p_savings(self, p2p_trades_info: Dict[str, Any], grid_import_rate: float) -> float:
        """Calculate total savings from P2P trades compared to grid import."""
        savings = 0.0
        
        buying_from = p2p_trades_info.get("buying_from", [])
        for trade in buying_from:
            energy_kwh = trade.get("energy_kwh", 0)
            p2p_price = trade.get("price_per_kwh", 0)
            grid_cost = energy_kwh * grid_import_rate
            p2p_cost = trade.get("total_cost", 0)
            # Savings = what we would have paid to grid - what we paid for P2P
            savings += grid_cost - p2p_cost
        
        return round(savings, 2)
    
    def _get_user_profile_info(self, member) -> Dict[str, Any]:
        """Get user profile information from member model."""
        if member is None:
            return {
                'location': 'Unknown',
                'solar_capacity_kw': 0,
                'battery_capacity_kwh': 0,
                'user_type': 'Consumer',
            }
        
        # Get location label (if set)
        location = "Community Member"
        if member.connection_point:
            location = member.connection_point  # Just use the label directly (e.g., "North Zone")
        
        return {
            'location': location,
            'solar_capacity_kw': member.assets.pv_capacity_kw,
            'battery_capacity_kwh': member.assets.battery_capacity_kwh,
            'user_type': 'Prosumer' if member.member_type.value == 'prosumer' else 'Consumer',
        }
    
    def list_available_users(self) -> list:
        """List all available users (members) from the community model."""
        try:
            model = self.model_service.get_model()
            if model is None:
                return []
            
            user_list = []
            for member in model.members:
                profile = self._get_user_profile_info(member)
                user_list.append({
                    'user_id': member.member_id,
                    'name': f"User {member.member_id.replace('_', ' ').title()}",
                    'location': profile.get('location', 'Community Member'),
                    'solar_capacity_kw': profile.get('solar_capacity_kw', 0),
                    'battery_capacity_kwh': profile.get('battery_capacity_kwh', 0),
                    'user_type': profile.get('user_type', 'Consumer'),
                })
            
            return sorted(user_list, key=lambda x: x['user_id'])
        except Exception as e:
            logger.error(f"Error listing users: {e}", exc_info=True)
            return []
    
    def _default_user_data(self, user_id: str) -> Dict[str, Any]:
        """Return default data structure when no data is available."""
        # Get model for default rate
        model = self.model_service.get_model()
        default_rate = model.community_control.import_rate_usd_per_kwh if model else 0.30
        
        return {
            "data_available": False,
            "message": "Data not available",
            "produced_kwh_today": 0.0,
            "consumed_kwh_today": 0.0,
            "net_kwh_today": 0.0,
            "battery_soc_pct": 0.0,
            "battery_capacity_kwh": 0.0,
            "battery_available_kwh": 0.0,
            "credits_today": 0.0,
            "total_credits": 0.0,
            "current_rate_eur_kwh": default_rate,
            "recent_transactions": [],
            "carbon_offset_today_kg": 0.0,
            "carbon_offset_month_kg": 0.0,
            "carbon_offset_community_rank": 0,
            "dr_engagement": 0.0,
            "dr_events_participated": 0,
            "dr_total_rewards_eur": 0.0,
            "location": "Unknown",
            "solar_capacity_kw": 0.0,
            "user_alerts": [],
        }
