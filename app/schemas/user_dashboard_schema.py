"""
User Dashboard domain schemas
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any


class UserTransaction(BaseModel):
    id: str
    type: str = Field(..., description="buy or sell")
    amount_kwh: float
    price_per_kwh: float
    total_eur: float
    counterparty_id: str = ""
    timestamp: str


class UserDashboardData(BaseModel):
    produced_kwh_today: float = Field(..., description="Energy produced today (kWh)")
    consumed_kwh_today: float = Field(..., description="Energy consumed today (kWh)")
    net_kwh_today: float = Field(..., description="Net energy (produced - consumed) today (kWh)")
    battery_soc_pct: float = Field(..., description="Battery state of charge (%)")
    battery_capacity_kwh: float = Field(..., description="Battery capacity (kWh)")
    battery_available_kwh: float = Field(..., description="Available energy in battery (kWh)")
    credits_today: float = Field(..., description="Energy credits earned today (kWh)")
    total_credits: float = Field(..., description="Total energy credits (kWh)")
    current_rate_eur_kwh: float = Field(..., description="Current P2P market rate (€/kWh)")
    recent_transactions: List[Dict[str, Any]] = Field(default_factory=list, description="Recent P2P transactions")
    carbon_offset_today_kg: float = Field(..., description="Carbon offset today (kg CO₂)")
    carbon_offset_month_kg: float = Field(..., description="Carbon offset this month (kg CO₂)")
    carbon_offset_community_rank: int = Field(..., description="User's rank in community carbon offset")
    dr_engagement: float = Field(..., description="Demand response engagement percentage")
    dr_events_participated: int = Field(..., description="Number of DR events participated in")
    dr_total_rewards_eur: float = Field(..., description="Total DR rewards earned (€)")
    user_alerts: List[Dict[str, Any]] = Field(default_factory=list, description="System alerts specific to this user")

