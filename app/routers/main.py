# This file will be moved to routers/main.py
from fastapi import APIRouter
from app.routers.community_dashboard_router import router as community_dashboard_router
from app.routers.user_dashboard_router import router as user_dashboard_router
from app.routers.system_notice_router import router as system_notice_router
from app.routers.config import router as config_router

api_router = APIRouter()

api_router.include_router(community_dashboard_router, prefix="/community-dashboard", tags=["community-dashboard"])
api_router.include_router(user_dashboard_router, prefix="/user", tags=["user-dashboard"])
api_router.include_router(system_notice_router, prefix="/system", tags=["system-notices"])
api_router.include_router(config_router, prefix="/config", tags=["community-config"])
