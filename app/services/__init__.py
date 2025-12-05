"""
Services Package

Domain-driven service organization: domain services for presentation, infrastructure for core services.
"""

# Domain services (presentation layer)
from app.services.community.dashboard_service import CommunityDashboardService
from app.services.user.dashboard_service import UserDashboardService

# Infrastructure services (core simulation, background jobs, utilities)
from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine
from app.services.infrastructure.control_service import CommunityControlService
from app.services.infrastructure.background_service import (
    BackgroundSimulationService,
    get_background_service
)
from app.services.infrastructure.system_notice_service import SystemNoticeService

__all__ = [
    # Domain services (presentation)
    "CommunityDashboardService",
    "UserDashboardService",
    # Infrastructure (core services)
    "CommunityModelService",
    "CommunitySimulationEngine",
    "CommunityControlService",
    "BackgroundSimulationService",
    "get_background_service",
    "SystemNoticeService",
]

