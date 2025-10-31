from typing import Dict, Any, List
from app.services.community_dashboard_service import DataPresentationService
from app.services.community_config import get_community_config
from app.services.marketplace_service import MarketplaceService
from app.services.demand_response_service import DemandResponseService
from app.services.system_notice_service import SystemNoticeService
from app.services.user_device_service import UserDeviceService
import logging

logger = logging.getLogger(__name__)


class UserDashboardService:
    def __init__(self, data_presentation: DataPresentationService):
        self.data_presentation = data_presentation
        self.marketplace_service = MarketplaceService(data_presentation)
        self.dr_service = DemandResponseService(data_presentation)
        self.notice_service = SystemNoticeService()
        self.device_service = UserDeviceService()

    async def _get_user_carbon_offset(self, user_id: str, households: int) -> Dict[str, float]:
        """Calculate user's carbon offset metrics (today and month)."""
        try:
            config = await get_community_config()
            emission_factor = getattr(config, 'emission_factor_kg_per_kwh', 0.35)

            # Today's offset
            flow_24h = await self.data_presentation.get_24h_energy_flow()
            produced_today = sum([p.get('produced', 0) for p in flow_24h])
            produced_today_per_user = produced_today / households
            carbon_offset_today = produced_today_per_user * emission_factor

            # Month's offset (30 days)
            trends_30d = await self.data_presentation.get_energy_trends(30)
            produced_month = sum([t.get('produced', 0) for t in trends_30d])
            produced_month_per_user = produced_month / households
            carbon_offset_month = produced_month_per_user * emission_factor

            return {
                'carbon_offset_today_kg': round(carbon_offset_today, 2),
                'carbon_offset_month_kg': round(carbon_offset_month, 2)
            }
        except Exception as e:
            logger.warning(f"Error calculating user carbon offset: {e}")
            return {'carbon_offset_today_kg': 0.0, 'carbon_offset_month_kg': 0.0}

    async def _get_user_dr_participation(self, user_id: str) -> Dict[str, Any]:
        """Get user's demand response participation metrics."""
        try:
            # Get community DR metrics and scale down per user
            dr_metrics = await self.dr_service.get_demand_response_metrics()
            engagement = dr_metrics.get('engagement', 0.75)

            # Estimate user participation from MongoDB if available, else use community engagement
            db = await get_database()
            user_dr_stats = await db["user_dr_participation"].find_one(
                {"user_id": user_id},
                {"_id": 0}
            )

            if user_dr_stats:
                events_participated = user_dr_stats.get('events_participated', 0)
                total_rewards = user_dr_stats.get('total_rewards_eur', 0.0)
            else:
                # Fallback: estimate from community engagement
                active_events = dr_metrics.get('active_events', [])
                events_participated = len(active_events) if engagement > 0.5 else 0
                total_rewards = events_participated * 5.0  # Estimate €5 per event

            return {
                'dr_engagement': round(engagement * 100, 1),  # Percentage
                'dr_events_participated': int(events_participated),
                'dr_total_rewards_eur': round(total_rewards, 2)
            }
        except Exception as e:
            logger.warning(f"Error getting user DR participation: {e}")
            return {
                'dr_engagement': 75.0,
                'dr_events_participated': 0,
                'dr_total_rewards_eur': 0.0
            }

    async def _get_user_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        """Get system alerts specific to this user (community + user-specific)."""
        try:
            return await self.notice_service.list_user_alerts(user_id, limit=10)
        except Exception as e:
            logger.warning(f"Error getting user alerts: {e}")
            return []

    async def _get_user_carbon_rank(self, user_id: str, households: int, user_offset_month: float) -> int:
        """Estimate user's rank in community carbon offset rankings.
        MVP: simple percentile-based estimate.
        """
        try:
            config = await get_community_config()
            # Community total offset this month
            trends_30d = await self.data_presentation.get_energy_trends(30)
            community_produced_month = sum([t.get('produced', 0) for t in trends_30d])
            emission_factor = getattr(config, 'emission_factor_kg_per_kwh', 0.35)
            community_offset_month = community_produced_month * emission_factor
            avg_user_offset = community_offset_month / households if households > 0 else 0

            # Rough rank estimate: if user is above average, rank higher
            if user_offset_month >= avg_user_offset * 1.2:
                return 1  # Top tier
            elif user_offset_month >= avg_user_offset:
                rank_range = max(2, int(households * 0.3))  # Top 30%
                return max(2, int(households * 0.1) + 1)
            else:
                rank_range = int(households * 0.7)  # Bottom 70%
                return max(int(households * 0.3), households - rank_range)

        except Exception as e:
            logger.warning(f"Error calculating user carbon rank: {e}")
            return 0

    async def get_user_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Compute per-user dashboard metrics from individual user device data (bottom-up approach)."""
        # Get user's device data (solar capacity, battery, consumption)
        user_device = await self.device_service.get_user_device_data(user_id)
        
        # Get community 24h flow for production pattern
        flow_24h = await self.data_presentation.get_24h_energy_flow()
        
        # Calculate user's production today based on their solar capacity share
        produced_kwh_today = await self.device_service.calculate_user_production_today(
            user_id, flow_24h
        )
        
        # Calculate user's consumption today from their device data
        consumed_kwh_today = await self.device_service.calculate_user_consumption_today(user_id)
        
        net_kwh_today = produced_kwh_today - consumed_kwh_today

        # Battery data from user device
        battery_capacity_kwh = user_device.get("battery_capacity_kwh", 0.0)
        battery_soc_pct = user_device.get("battery_soc_pct", 0.0)
        battery_available_kwh = battery_capacity_kwh * (battery_soc_pct / 100.0)
        
        # Get user count for carbon offset calculations
        community_metrics = await self.device_service.aggregate_community_metrics()
        households = max(1, community_metrics.get("user_count", 1))

        # P2P Marketplace data
        credits = await self.marketplace_service.get_user_credits(user_id)
        market_rates = await self.marketplace_service.get_current_market_rates()
        transactions = await self.marketplace_service.get_user_transactions(user_id, limit=10)

        # Carbon offset metrics
        carbon = await self._get_user_carbon_offset(user_id, households)
        carbon_rank = await self._get_user_carbon_rank(user_id, households, carbon['carbon_offset_month_kg'])

        # Demand Response participation
        dr_participation = await self._get_user_dr_participation(user_id)

        # User alerts
        user_alerts = await self._get_user_alerts(user_id)

        return {
            'produced_kwh_today': round(produced_kwh_today, 2),
            'consumed_kwh_today': round(consumed_kwh_today, 2),
            'net_kwh_today': round(net_kwh_today, 2),
            'battery_soc_pct': round(battery_soc_pct, 1),
            'battery_capacity_kwh': round(per_user_capacity, 2),
            'battery_available_kwh': round(battery_available_kwh, 2),
            'credits_today': credits['credits_today'],
            'total_credits': credits['total_credits'],
            'current_rate_eur_kwh': market_rates['current_rate_eur_kwh'],
            'recent_transactions': transactions,
            'carbon_offset_today_kg': carbon['carbon_offset_today_kg'],
            'carbon_offset_month_kg': carbon['carbon_offset_month_kg'],
            'carbon_offset_community_rank': carbon_rank,
            'dr_engagement': dr_participation['dr_engagement'],
            'dr_events_participated': dr_participation['dr_events_participated'],
            'dr_total_rewards_eur': dr_participation['dr_total_rewards_eur'],
            'user_alerts': user_alerts
        }


