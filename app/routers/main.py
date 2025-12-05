from fastapi import APIRouter

from app.routers.community_dashboard_router import router as community_dashboard_router
from app.routers.system_notice_router import router as system_notice_router
from app.routers.user_dashboard_router import router as user_dashboard_router
from app.routers.demand_response_router import router as demand_response_router
from app.routers.marketplace_router import router as marketplace_router
from app.routers.auth_router import router as auth_router
from app.routers.device_router import router as device_router

api_router = APIRouter()

api_router.include_router(
    auth_router, 
    prefix="/auth", 
    tags=["authentication"]
)
api_router.include_router(
    community_dashboard_router, 
    prefix="/community-dashboard", 
    tags=["community-dashboard"]
)
api_router.include_router(
    user_dashboard_router, 
    prefix="/user", 
    tags=["user-dashboard"]
)
api_router.include_router(
    system_notice_router, 
    prefix="/system", 
    tags=["system-notices"]
)
api_router.include_router(
    demand_response_router, 
    prefix="/demand-response", 
    tags=["demand-response"]
)
api_router.include_router(
    marketplace_router, 
    prefix="/marketplace", 
    tags=["marketplace"]
)
api_router.include_router(
    device_router, 
    prefix="/user", 
    tags=["devices"]
)
