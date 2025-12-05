"""
Community Dashboard API Endpoints

This module provides endpoints for community dashboard data using the
community simulation engine with normalized pattern files.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from app.services.infrastructure.control_service import CommunityControlService
from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine
from app.services.community.dashboard_service import CommunityDashboardService
from app.services.infrastructure.background_service import get_background_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy service initialization (singleton instances)
_community_service = None
_model_service = None
_simulation_engine = None
_control_service = None

def get_community_service():
    """Get or create community dashboard service (lazy initialization)."""
    global _community_service
    if _community_service is None:
        _community_service = CommunityDashboardService()
    return _community_service

def get_model_service():
    """Get or create model service (lazy initialization)."""
    global _model_service
    if _model_service is None:
        _model_service = get_community_service().model_service
    return _model_service

def get_simulation_engine():
    """Get or create simulation engine (lazy initialization)."""
    global _simulation_engine
    if _simulation_engine is None:
        _simulation_engine = get_community_service().simulation_engine
    return _simulation_engine

def get_control_service():
    """Get or create control service (lazy initialization)."""
    global _control_service
    if _control_service is None:
        _control_service = CommunityControlService(get_model_service(), get_simulation_engine())
    return _control_service


@router.get("/presentation/community-dashboard")
async def get_community_dashboard_presentation_data(include_trends: bool = False, trends_days: int = 30):
    """
    Get community dashboard data - main endpoint for frontend dashboard.
    
    Uses the community simulation engine to generate real-time data from
    normalized patterns based on community model configuration.
    
    Includes:
    - Current energy flow (generation, consumption, net)
    - Storage network status
    - Grid interaction metrics (voltage, frequency, stability)
    - Carbon metrics
    - Optional: Energy trends for charts (if include_trends=true)
    """
    try:
        result = await get_community_service().get_community_dashboard_data(
            include_trends=include_trends, 
            trends_days=trends_days
        )
        return result
    except Exception as e:
        logger.error(f"Error getting community dashboard data: {e}", exc_info=True)
        # Fallback: return basic data without trends to prevent complete failure
        try:
            default_result = await get_community_service().get_community_dashboard_data(
                include_trends=False, 
                trends_days=1
            )
            return default_result
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get community dashboard data: {str(e)}"
            )


@router.get("/status")
async def get_community_status():
    """
    Get current community status including member count and configuration.
    
    Returns community model information and member statistics.
    """
    try:
        status = get_control_service().get_community_status()
        return status
    except Exception as e:
        logger.error(f"Error getting community status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get community status: {str(e)}"
        )


@router.get("/member/{member_id}/status")
async def get_member_status(member_id: str):
    """Get status of a specific member."""
    try:
        status = get_control_service().get_member_status(member_id)
        if status is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member {member_id} not found"
            )
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting member status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get member status: {str(e)}"
        )


@router.get("/simulation/current")
async def get_current_simulation():
    """
    Get current simulation state with detailed member and community data.
    
    Returns raw simulation engine output for debugging and detailed analysis.
    """
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        model = get_model_service().get_model()
        if model is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Community model not loaded"
            )
        
        now = datetime.now(ZoneInfo(model.community.timezone))
        result = get_simulation_engine().simulate_community(now)
        return result
    except Exception as e:
        logger.error(f"Error getting current simulation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get simulation data: {str(e)}"
        )


@router.get("/simulation/background/status")
async def get_background_service_status():
    """Get status of the background simulation service."""
    try:
        from app.services.infrastructure.background_service import get_background_service
        background_service = get_background_service()
        status = background_service.get_cache_status()
        
        # Add model source info
        model_svc = background_service.model_service
        status["model_source"] = "MongoDB" if model_svc._mongodb_available else "File"
        status["mongodb_available"] = model_svc._mongodb_available
        status["community_id"] = model_svc.community_id
        
        return {
            "status": "success",
            "background_service": status
        }
    except Exception as e:
        logger.error(f"Error getting background service status: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "background_service": None
        }


@router.get("/model/status")
async def get_model_status():
    """Get detailed status of the loaded community model, showing which values are defaults vs from MongoDB."""
    try:
        model_service = get_model_service()
        status = model_service.get_model_status()
        return {
            "status": "success",
            "model_status": status
        }
    except Exception as e:
        logger.error(f"Error getting model status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get model status: {str(e)}"
        )


@router.post("/model/reload")
async def reload_community_model():
    """Force reload community model from MongoDB."""
    try:
        from app.services.infrastructure.model_service import CommunityModelService
        model_service = CommunityModelService(watch_for_changes=True)
        model_service.refresh_mongodb_status()
        success = model_service.reload_model()
        if success:
            model = model_service.get_model()
            return {
                "status": "success",
                "message": "Model reloaded successfully from MongoDB",
                "source": "MongoDB",
                "community_id": model.community.community_id if model else None,
                "members_count": len(model.members) if model else 0
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to reload model"
            )
    except Exception as e:
        logger.error(f"Error reloading model: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload model: {str(e)}"
        )


@router.get("/cache-status")
async def get_cache_status():
    """Get background service cache status - for debugging."""
    try:
        bg_service = get_background_service()
        status = bg_service.get_cache_status()
        
        # Also get sample data
        today_data = bg_service.get_today_data()
        
        return {
            "status": status,
            "today_sample": {
                "count": len(today_data),
                "first_timestamp": today_data[0].get('timestamp') if today_data else None,
                "last_timestamp": today_data[-1].get('timestamp') if today_data else None,
            }
        }
    except Exception as e:
        logger.error(f"Error getting cache status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cache status: {str(e)}"
        )

