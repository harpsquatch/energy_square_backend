"""
User Dashboard API Endpoints

This module provides endpoints for user dashboard data using the
community simulation engine with normalized pattern files.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.services.user.dashboard_service import UserDashboardService

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy service initialization (singleton instance)
_user_dashboard_service = None

def get_user_dashboard_service():
    """Get or create user dashboard service (lazy initialization)."""
    global _user_dashboard_service
    if _user_dashboard_service is None:
        _user_dashboard_service = UserDashboardService()
    return _user_dashboard_service


@router.get("/user-dashboard")
async def get_user_dashboard(user_id: str = "user_001", include_users: bool = False) -> Dict[str, Any]:
    """
    Get user dashboard data - main endpoint for user dashboard.
    
    Uses the community simulation engine to generate real-time data from
    normalized patterns based on community model configuration.
    
    Args:
        user_id: The user ID (member_id) to fetch dashboard data for
        include_users: If True, include the list of all available users (for initial load)
    """
    try:
        return await get_user_dashboard_service().get_user_dashboard(user_id, include_users=include_users)
    except Exception as e:
        logger.error(f"Error getting user dashboard: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get user dashboard data: {str(e)}"
        )


