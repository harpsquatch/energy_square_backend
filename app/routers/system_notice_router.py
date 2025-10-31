from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from app.schemas.system_notice_schema import SystemNoticeIn, SystemNoticeOut
from app.services.system_notice_service import SystemNoticeService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
notice_service = SystemNoticeService()


@router.get("/system-notices", response_model=List[SystemNoticeOut])
async def list_all_notices():
    """List all system notices (community + user-specific). For system controller/admin."""
    try:
        return await notice_service.list_all_alerts(limit=50)
    except Exception as e:
        logger.error(f"Error listing all notices: {e}")
        raise HTTPException(status_code=500, detail="Failed to list system notices")


@router.get("/system-notices/community", response_model=List[SystemNoticeOut])
async def list_community_notices():
    """List community-level notices only."""
    try:
        return await notice_service.list_community_alerts(limit=50)
    except Exception as e:
        logger.error(f"Error listing community notices: {e}")
        raise HTTPException(status_code=500, detail="Failed to list community notices")


@router.get("/system-notices/user/{user_id}", response_model=List[SystemNoticeOut])
async def list_user_notices(user_id: str):
    """List notices for a specific user (community + user-specific)."""
    try:
        return await notice_service.list_user_alerts(user_id, limit=50)
    except Exception as e:
        logger.error(f"Error listing user notices: {e}")
        raise HTTPException(status_code=500, detail="Failed to list user notices")


@router.post("/system-notices", response_model=SystemNoticeOut)
async def create_system_notice(payload: SystemNoticeIn):
    """Create a system notice. If user_id is provided, creates user-specific alert; otherwise community-level."""
    try:
        if payload.user_id:
            return await notice_service.create_user_alert(
                user_id=payload.user_id,
                type=payload.type,
                severity=payload.severity,
                message=payload.message
            )
        else:
            return await notice_service.create_community_alert(
                type=payload.type,
                severity=payload.severity,
                message=payload.message,
                affected_users=payload.affected_users
            )
    except Exception as e:
        logger.error(f"Error creating system notice: {e}")
        raise HTTPException(status_code=500, detail="Failed to create system notice")


