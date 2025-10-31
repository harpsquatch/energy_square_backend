"""
Analytics API Endpoints for Energy Square Platform

This module provides analytics endpoints that serve data to the frontend
without requiring authentication or database dependencies.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from app.services.community_dashboard_service import DataPresentationService
from app.schemas.community_dashboard_schema import CommunityDashboardData, EnergyTrendsData, GridTelemetry
from app.schemas.demand_response_schema import DemandResponseData, DemandResponseProgram
from app.services.demand_response_service import DemandResponseService
from app.services.user_dashboard_service import UserDashboardService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize service
data_presentation = DataPresentationService()
dr_service = DemandResponseService(data_presentation)
user_dashboard_service = UserDashboardService(data_presentation)


@router.get("/test-community")
async def test_community_endpoint():
    """Test endpoint to debug community dashboard issues"""
    try:
        return data_presentation.test_community_data()
    except Exception as e:
        logger.error(f"Community dashboard test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Community dashboard test failed"
        )


@router.get("/debug")
async def debug_endpoint():
    """Debug endpoint to test basic functionality"""
    try:
        return await data_presentation.get_debug_info()
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Debug endpoint failed"
        )




@router.get("/community", response_model=CommunityDashboardData)
async def get_community_analytics():
    """Get community-level analytics"""
    try:
        return await data_presentation.get_community_dashboard_data()
    except Exception as e:
        logger.error(f"Error getting community analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get community analytics"
        )


@router.get("/energy-trends", response_model=List[EnergyTrendsData])
async def get_energy_trends(days: int = 30):
    """Get energy trends over time based on real data patterns"""
    try:
        return await data_presentation.get_energy_trends(days)
    except Exception as e:
        logger.error(f"Error getting energy trends: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get energy trends"
        )




# Data Presentation Endpoints
@router.get("/presentation/community-dashboard", response_model=CommunityDashboardData)
async def get_community_dashboard_presentation_data():
    """Get community dashboard data formatted for presentation layer"""
    try:
        return await data_presentation.get_community_dashboard_data()
    except Exception as e:
        logger.error(f"Error getting frontend community dashboard data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get frontend community dashboard data"
        )


@router.get("/demand-response", response_model=DemandResponseData)
async def get_demand_response():
    """Get demand response metrics and recommendations"""
    try:
        return await dr_service.get_demand_response_metrics()
    except Exception as e:
        logger.error(f"Error getting demand response metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get demand response metrics"
        )

@router.get("/demand-response/programs", response_model=List[DemandResponseProgram])
async def list_demand_response_programs():
    try:
        return dr_service.list_programs()
    except Exception as e:
        logger.error(f"Error listing DR programs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list DR programs")

@router.post("/demand-response/programs", response_model=DemandResponseProgram)
async def create_demand_response_program(payload: Dict[str, Any]):
    try:
        return dr_service.create_program(payload)
    except Exception as e:
        logger.error(f"Error creating DR program: {e}")
        raise HTTPException(status_code=500, detail="Failed to create DR program")


@router.get("/grid-telemetry", response_model=GridTelemetry)
async def get_grid_telemetry():
    """Get derived grid telemetry values"""
    try:
        return await data_presentation.get_grid_telemetry()
    except Exception as e:
        logger.error(f"Error getting grid telemetry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get grid telemetry"
        )


    


    


