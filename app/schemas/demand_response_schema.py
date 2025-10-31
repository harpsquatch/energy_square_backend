"""
Demand Response domain schemas
"""

from typing import List
from pydantic import BaseModel, Field
from datetime import datetime


class DemandResponseEvent(BaseModel):
    """Active demand response event info"""
    id: str = Field(..., description="Event identifier")
    title: str = Field(..., description="Event title")
    start_time: datetime = Field(..., description="Start time")
    end_time: datetime = Field(..., description="End time")
    target_reduction_kw: float = Field(..., description="Requested reduction (kW)")
    reward_per_kwh: float = Field(..., description="Reward per kWh reduced (€)")
    status: str = Field(..., description="Event status")


class DemandResponseData(BaseModel):
    """Demand response metrics and recommendations"""
    engagement: float = Field(..., description="Current engagement level (0-1)")
    potential_shed_kw: float = Field(..., description="Estimated shed potential (kW)")
    price_signal_eur_kwh: float = Field(..., description="Latest price signal (€/kWh)")
    active_events: List[DemandResponseEvent] = Field(default_factory=list, description="Active DR events")
    recommendations: List[str] = Field(default_factory=list, description="Recommended actions")
    aggregate_generation_kw: float = Field(0, description="Aggregate current generation (kW)")
    aggregate_consumption_kw: float = Field(0, description="Aggregate current consumption (kW)")
    net_balance_kw: float = Field(0, description="Net balance (generation - consumption) kW")
    aggregate_potential_shed_kw: float = Field(0, description="Aggregate shed potential for community (kW)")
    alerts: List[str] = Field(default_factory=list, description="User-facing alerts/notifications")


class DemandResponseProgram(BaseModel):
    """Simple DR program record"""
    id: str = Field(..., description="Program id")
    title: str = Field(..., description="Program title")
    reason: str = Field(..., description="Trigger reason, e.g., High Price")
    start_time: datetime = Field(..., description="Start time")
    end_time: datetime = Field(..., description="End time")
    target_reduction_kw: float = Field(..., description="Target reduction (kW)")
    reward_per_kwh: float = Field(..., description="Reward per kWh reduced (€)")
    status: str = Field(..., description="Status: active|upcoming|ended")


