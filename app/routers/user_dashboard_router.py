from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from app.services.community_dashboard_service import DataPresentationService
from app.services.user_dashboard_service import UserDashboardService
from app.services.user_device_service import UserDeviceService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

data_presentation = DataPresentationService()
user_dashboard_service = UserDashboardService(data_presentation)
device_service = UserDeviceService()


@router.get("/user-dashboard")
async def get_user_dashboard(user_id: str = "demo") -> Dict[str, Any]:
    try:
        return await user_dashboard_service.get_user_dashboard(user_id)
    except Exception as e:
        logger.error(f"Error getting user dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get user dashboard data")


@router.post("/initialize-sample-users")
async def initialize_sample_users():
    """Initialize 5 sample users with different device configurations"""
    try:
        users = await device_service.initialize_sample_users()
        return {
            "status": "success",
            "message": f"Initialized {len(users)} sample users",
            "users": users
        }
    except Exception as e:
        logger.error(f"Error initializing sample users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initialize sample users")


