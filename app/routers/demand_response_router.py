"""
Demand Response API Endpoints

Endpoints for creating DR events and managing member participation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.infrastructure.demand_response_service import get_demand_response_service
from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.dr_trigger_service import get_trigger_service
from app.services.infrastructure.background_service import get_background_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy service initialization
_model_service = None


def get_model_service():
    """Get or create model service (lazy initialization)."""
    global _model_service
    if _model_service is None:
        _model_service = CommunityModelService(watch_for_changes=True)
    return _model_service


# Request/Response models
class CreateEventRequest(BaseModel):
    """Request to create a DR event."""
    title: str = Field(..., description="Event title")
    start_time: Optional[datetime] = Field(None, description="Start time (defaults to now)")
    duration_hours: float = Field(2.0, gt=0, le=24, description="Duration in hours")
    target_reduction_pct: float = Field(0.2, ge=0, le=1, description="Target reduction percentage")
    price_signal: float = Field(0.15, ge=0, description="Payment per kWh reduced (USD)")
    reason: str = Field("Peak demand management", description="Reason for DR event")


class OptInRequest(BaseModel):
    """Request to opt into a DR event."""
    member_id: str = Field(..., description="Member ID")
    event_id: str = Field(..., description="Event ID")
    reduction_pct: Optional[float] = Field(None, ge=0, le=1, description="Custom reduction percentage")


class OptOutRequest(BaseModel):
    """Request to opt out of a DR event."""
    member_id: str = Field(..., description="Member ID")
    event_id: str = Field(..., description="Event ID")


@router.get("/events")
async def get_all_events():
    """
    Get all demand response events (active and past).
    
    Returns list of all DR events with their status and participant counts.
    """
    try:
        dr_service = get_demand_response_service()
        events = await dr_service.get_all_events_async()
        
        return {
            "status": "success",
            "count": len(events),
            "events": [event.to_dict() for event in events]
        }
    except Exception as e:
        logger.error(f"Error getting DR events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get DR events: {str(e)}"
        )


@router.get("/events/active")
async def get_active_events():
    """
    Get currently active demand response events.
    
    Returns only events that are active right now.
    """
    try:
        dr_service = get_demand_response_service()
        
        # Get timezone from model
        model_service = get_model_service()
        model = model_service.get_model()
        if model:
            current_time = datetime.now(ZoneInfo(model.community.timezone))
        else:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        active_events = dr_service.get_active_events(current_time)
        
        return {
            "status": "success",
            "current_time": current_time.isoformat(),
            "count": len(active_events),
            "events": [event.to_dict() for event in active_events]
        }
    except Exception as e:
        logger.error(f"Error getting active DR events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active DR events: {str(e)}"
        )


@router.post("/events/create")
async def create_event(request: CreateEventRequest):
    """
    Create a new demand response event.
    
    Community managers can create DR events to reduce peak demand.
    Members will be notified and can opt in to participate.
    """
    try:
        dr_service = get_demand_response_service()
        
        # Get timezone from model
        model_service = get_model_service()
        model = model_service.get_model()
        if model:
            tz = ZoneInfo(model.community.timezone)
        else:
            tz = ZoneInfo("UTC")
        
        # Use provided start time or default to now
        if request.start_time:
            start_time = request.start_time
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=tz)
        else:
            start_time = datetime.now(tz)
        
        event_id = dr_service.create_event(
            title=request.title,
            start_time=start_time,
            duration_hours=request.duration_hours,
            target_reduction_pct=request.target_reduction_pct,
            price_signal=request.price_signal,
            reason=request.reason
        )
        
        return {
            "status": "success",
            "message": "DR event created successfully",
            "event_id": event_id,
            "start_time": start_time.isoformat(),
            "end_time": (start_time + timedelta(hours=request.duration_hours)).isoformat()
        }
    except Exception as e:
        logger.error(f"Error creating DR event: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create DR event: {str(e)}"
        )


@router.post("/opt-in")
async def opt_in(request: OptInRequest):
    """
    Opt a member into a demand response event.
    
    When a member opts in, their consumption will be reduced during the event
    based on the reduction percentage.
    """
    try:
        dr_service = get_demand_response_service()
        
        # Verify member exists
        model_service = get_model_service()
        member = model_service.get_member(request.member_id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {request.member_id} not found"
            )
        
        success = dr_service.opt_in(
            member_id=request.member_id,
            event_id=request.event_id,
            reduction_pct=request.reduction_pct
        )
        
        if success:
            # Trigger immediate simulation update to reflect participation change
            try:
                background_service = get_background_service()
                background_service.trigger_immediate_update(
                    reason=f"DR opt-in: {request.member_id} joined event {request.event_id}"
                )
            except Exception as e:
                logger.warning(f"Could not trigger immediate update: {e}")
                # Continue - update will happen on next hourly cycle
            
            return {
                "status": "success",
                "message": f"Member {request.member_id} opted into DR event {request.event_id}",
                "member_id": request.member_id,
                "event_id": request.event_id
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DR event {request.event_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opting in to DR event: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to opt in: {str(e)}"
        )


@router.post("/opt-out")
async def opt_out(request: OptOutRequest):
    """
    Opt a member out of a demand response event.
    
    Member's consumption will return to normal.
    """
    try:
        dr_service = get_demand_response_service()
        
        success = dr_service.opt_out(
            member_id=request.member_id,
            event_id=request.event_id
        )
        
        if success:
            # Trigger immediate simulation update to reflect participation change
            try:
                background_service = get_background_service()
                background_service.trigger_immediate_update(
                    reason=f"DR opt-out: {request.member_id} left event {request.event_id}"
                )
            except Exception as e:
                logger.warning(f"Could not trigger immediate update: {e}")
                # Continue - update will happen on next hourly cycle
            
            return {
                "status": "success",
                "message": f"Member {request.member_id} opted out of DR event {request.event_id}",
                "member_id": request.member_id,
                "event_id": request.event_id
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DR event {request.event_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opting out of DR event: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to opt out: {str(e)}"
        )


@router.get("/member/{member_id}/status")
async def get_member_dr_status(member_id: str):
    """
    Get demand response status for a specific member.
    
    Shows which events they're participating in and their current reduction.
    """
    try:
        dr_service = get_demand_response_service()
        
        # Get timezone from model
        try:
            model_service = get_model_service()
            model = model_service.get_model()
            if model:
                current_time = datetime.now(ZoneInfo(model.community.timezone))
            else:
                current_time = datetime.now(ZoneInfo("UTC"))
        except Exception as e:
            logger.warning(f"Could not get timezone from model: {e}, using UTC")
            current_time = datetime.now(ZoneInfo("UTC"))
        
        # Get all events member is participating in
        try:
            all_events = await dr_service.get_all_events_async()
            member_events = [
                event for event in all_events
                if member_id in event.participants
            ]
        except Exception as e:
            logger.warning(f"Could not get events: {e}, returning empty list")
            all_events = []
            member_events = []
        
        # Get current reduction
        try:
            current_reduction = dr_service.get_member_reduction(member_id, current_time)
        except Exception as e:
            logger.warning(f"Could not get member reduction: {e}, using 0")
            current_reduction = 0.0
        
        return {
            "status": "success",
            "member_id": member_id,
            "current_time": current_time.isoformat(),
            "current_reduction_pct": current_reduction,
            "participating_events": [event.to_dict() for event in member_events],
            "event_count": len(member_events)
        }
    except Exception as e:
        logger.error(f"Error getting member DR status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get member DR status: {str(e)}"
        )


@router.get("/recommendations")
async def get_recommendations():
    """
    Get active DR event recommendations.
    
    Returns intelligent suggestions based on current conditions.
    Manager can approve or dismiss these recommendations.
    """
    try:
        trigger_service = get_trigger_service()
        recommendations = trigger_service.get_active_recommendations()
        
        return {
            "status": "success",
            "count": len(recommendations),
            "recommendations": [rec.to_dict() for rec in recommendations]
        }
    except Exception as e:
        logger.error(f"Error getting DR recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recommendations: {str(e)}"
        )


@router.post("/recommendations/{recommendation_id}/dismiss")
async def dismiss_recommendation(recommendation_id: str):
    """
    Dismiss a DR event recommendation.
    
    Manager chose not to create the recommended event.
    """
    try:
        trigger_service = get_trigger_service()
        success = trigger_service.dismiss_recommendation(recommendation_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Recommendation {recommendation_id} dismissed"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recommendation {recommendation_id} not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dismissing recommendation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dismiss recommendation: {str(e)}"
        )


@router.post("/debug/force-update")
async def force_simulation_update():
    """
    DEBUG: Force an immediate simulation update to apply current DR state.
    """
    try:
        from app.services.infrastructure.background_service import get_background_service
        
        background_service = get_background_service()
        success = background_service.trigger_immediate_update("DEBUG: Manual force update")
        
        if success:
            return {
                "status": "success",
                "message": "Simulation updated successfully"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to trigger update"
            }
    except Exception as e:
        logger.error(f"Error forcing update: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to force update: {str(e)}"
        )

