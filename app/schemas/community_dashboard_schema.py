"""
Community Dashboard domain schemas
"""

from typing import List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class CommunityDashboardData(BaseModel):
    """Community dashboard data schema"""
    total_energy_flow: Dict[str, Any] = Field(..., description="Total energy flow metrics")
    storage_network: Dict[str, Any] = Field(..., description="Storage network overview")
    grid_interaction: Dict[str, Any] = Field(..., description="Grid interaction data")
    participation_summary: Dict[str, Any] = Field(..., description="Participation summary")
    carbon_metrics: Dict[str, Any] = Field(..., description="Carbon metrics")
    marketplace_activity: Dict[str, Any] = Field(..., description="Marketplace activity")
    alerts_system_notices: List[Dict[str, Any]] = Field(default_factory=list, description="System notices")
    leaderboards: Dict[str, List[Dict[str, Any]]] = Field(..., description="Leaderboards")


class EnergyTrendsData(BaseModel):
    """Energy trends data schema"""
    date: datetime = Field(..., description="Date of the data point")
    produced: float = Field(..., description="Energy produced (kWh)")
    consumed: float = Field(..., description="Energy consumed (kWh)")
    sold: float = Field(..., description="Energy sold (kWh)")
    bought: float = Field(..., description="Energy bought (kWh)")
    carbon_offset: float = Field(..., description="Carbon offset (kg CO2)")
    efficiency: float = Field(..., description="Efficiency percentage")


class GridTelemetry(BaseModel):
    """Live grid telemetry values for integration view"""
    frequency_hz: float = Field(..., description="Grid frequency in Hz")
    voltage_v: float = Field(..., description="Voltage in Volts")
    load_pct: float = Field(..., description="Grid load percentage")
    renewable_pct: float = Field(..., description="Renewable share percentage")
    timestamp: datetime = Field(..., description="Timestamp of telemetry")


