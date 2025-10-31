"""
Marketplace Service for P2P energy trading
"""
from typing import Dict, Any, List
from app.services.community_config import get_community_config
from app.services.community_dashboard_service import DataPresentationService
from app.db.database import get_database
import logging

logger = logging.getLogger(__name__)


class MarketplaceService:
    def __init__(self, data_presentation: DataPresentationService):
        self.data_presentation = data_presentation

    async def get_user_credits(self, user_id: str) -> Dict[str, float]:
        """Get user's energy credits (today and total).
        MVP: Compute from user's net production today and historical.
        """
        try:
            config = await get_community_config()
            households = max(1, int(getattr(config, 'total_households', 1)))

            # Today's net production (kWh)
            flow_24h = await self.data_presentation.get_24h_energy_flow()
            produced_today = sum([p.get('produced', 0) for p in flow_24h])
            consumed_today = sum([p.get('consumed', 0) for p in flow_24h])
            net_today = (produced_today - consumed_today) / households

            # Credits earned today = net production (only if positive)
            credits_today = max(0.0, net_today * 0.9)  # 90% conversion, assume 10% grid losses

            # Total credits: estimate from 30d trends
            trends_30d = await self.data_presentation.get_energy_trends(30)
            produced_30d = sum([t.get('produced', 0) for t in trends_30d])
            consumed_30d = sum([t.get('consumed', 0) for t in trends_30d])
            net_30d = (produced_30d - consumed_30d) / households
            total_credits = max(0.0, net_30d * 0.85)  # Cumulative estimate

            return {
                'credits_today': round(credits_today, 2),
                'total_credits': round(total_credits, 2)
            }
        except Exception as e:
            logger.warning(f"Error computing user credits: {e}")
            return {'credits_today': 0.0, 'total_credits': 0.0}

    async def get_current_market_rates(self) -> Dict[str, Any]:
        """Get current P2P market rates from community config and PUN prices.
        Current rate = latest PUN price adjusted by community trading percentage.
        """
        try:
            config = await get_community_config()
            market_data = self.data_presentation.data.get('market_data', {})
            pun_prices = market_data.get('pun_prices', [])

            latest_price = self.data_presentation._get_latest_pun_price_kwh(pun_prices)

            # P2P rate is PUN price with community discount/premium
            avg_price = float(getattr(config, 'average_energy_price', 0.30))
            current_rate = latest_price if latest_price > 0 else avg_price

            # Price range from config
            fluctuation = float(getattr(config, 'price_fluctuation_range', 0.10))
            min_rate = current_rate * (1 - fluctuation)
            max_rate = current_rate * (1 + fluctuation)

            return {
                'current_rate_eur_kwh': round(current_rate, 3),
                'min_rate_eur_kwh': round(min_rate, 3),
                'max_rate_eur_kwh': round(max_rate, 3),
                'avg_rate_24h_eur_kwh': round(avg_price, 3)
            }
        except Exception as e:
            logger.warning(f"Error getting market rates: {e}")
            return {
                'current_rate_eur_kwh': 0.30,
                'min_rate_eur_kwh': 0.25,
                'max_rate_eur_kwh': 0.35,
                'avg_rate_24h_eur_kwh': 0.30
            }

    async def get_user_transactions(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent P2P transactions for a user from MongoDB.
        Falls back to empty list if collection doesn't exist or no data.
        """
        try:
            db = await get_database()
            cursor = db["marketplace_transactions"].find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit)

            transactions = []
            async for doc in cursor:
                transactions.append({
                    "id": doc.get("id", ""),
                    "type": doc.get("type", "buy"),
                    "amount_kwh": doc.get("amount_kwh", 0.0),
                    "price_per_kwh": doc.get("price_per_kwh", 0.0),
                    "total_eur": doc.get("total_eur", 0.0),
                    "counterparty_id": doc.get("counterparty_id", ""),
                    "timestamp": doc.get("timestamp", "")
                })

            return transactions
        except Exception as e:
            logger.warning(f"Error getting user transactions: {e}")
            return []

