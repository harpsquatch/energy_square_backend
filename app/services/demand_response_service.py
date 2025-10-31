"""
Demand Response Service for Energy Square Platform
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import logging

from app.services.community_dashboard_service import DataPresentationService

logger = logging.getLogger(__name__)


class DemandResponseService:
    """Service that computes demand response metrics and recommendations"""

    def __init__(self, data_presentation: DataPresentationService):
        self.data_presentation = data_presentation
        self._programs: List[Dict[str, Any]] = []

    def _safe_float(self, value: Any) -> float:
        try:
            if value is None:
                return 0.0
            v = float(value)
            if v != v:  # NaN
                return 0.0
            if v in (float("inf"), float("-inf")):
                return 0.0
            return v
        except Exception:
            return 0.0

    def _get_latest_pun_price_kwh(self, pun_prices: List[Dict[str, Any]]) -> float:
        try:
            if not pun_prices:
                return 0.0
            for entry in reversed(pun_prices):
                price = entry.get('price_eur_kwh') or entry.get('price_eur_mwh')
                if price is None:
                    continue
                # Convert if only MWh present
                if 'price_eur_mwh' in entry and entry.get('price_eur_kwh') is None:
                    try:
                        return self._safe_float(float(entry['price_eur_mwh']) / 1000.0)
                    except Exception:
                        continue
                try:
                    return self._safe_float(float(price))
                except Exception:
                    continue
            return 0.0
        except Exception:
            return 0.0

    async def get_demand_response_metrics(self) -> Dict[str, Any]:
        """Compute demand response metrics and simple recommendations."""
        try:
            config = await self.data_presentation._get_config()

            # Current conditions
            current_gen = await self.data_presentation.get_current_generation()
            current_cons = await self.data_presentation.get_current_consumption()
            net = current_gen - current_cons

            # Price signal
            pun_prices = self.data_presentation.data.get('market_data', {}).get('pun_prices', [])
            price_signal = self._get_latest_pun_price_kwh(pun_prices)

            # Engagement and shed potential
            engagement = getattr(config, 'demand_response_engagement', 0.75)
            potential_shed_kw = max(0.0, current_cons * 0.10)

            # Simple event trigger
            active_events: List[Dict[str, Any]] = []
            recommendations: List[str] = []
            alerts: List[str] = []

            if price_signal and price_signal > 0.2:  # high price signal
                active_events.append({
                    "id": "peak-price",
                    "title": "Peak Price Reduction",
                    "start_time": datetime.now(),
                    "end_time": datetime.now() + timedelta(hours=2),
                    "target_reduction_kw": round(potential_shed_kw, 2),
                    "reward_per_kwh": round(price_signal * 0.5, 3),
                    "status": "active"
                })
                recommendations.append("Reduce flexible loads during next 2 hours to avoid high prices")
                alerts.append("High price signal detected. Consider reducing non-critical loads.")

            if net < 0:  # deficit
                recommendations.append("Shift non-critical consumption to off-peak hours")
                alerts.append("Grid deficit: shifting flexible loads can reduce import costs.")

            return {
                "engagement": self._safe_float(engagement),
                "potential_shed_kw": self._safe_float(potential_shed_kw),
                "price_signal_eur_kwh": self._safe_float(price_signal),
                "active_events": active_events,
                "recommendations": recommendations,
                "aggregate_generation_kw": self._safe_float(current_gen),
                "aggregate_consumption_kw": self._safe_float(current_cons),
                "net_balance_kw": self._safe_float(net),
                "aggregate_potential_shed_kw": self._safe_float(potential_shed_kw),
                "alerts": alerts
            }
        except Exception as e:
            logger.warning(f"Demand response metrics fallback due to error: {e}")
            return {
                "engagement": 0.75,
                "potential_shed_kw": 0.0,
                "price_signal_eur_kwh": 0.0,
                "active_events": [],
                "recommendations": [],
                "aggregate_generation_kw": 0.0,
                "aggregate_consumption_kw": 0.0,
                "net_balance_kw": 0.0,
                "aggregate_potential_shed_kw": 0.0,
                "alerts": []
            }

    def list_programs(self) -> List[Dict[str, Any]]:
        return self._programs

    def create_program(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now()
        program = {
            "id": payload.get("id") or f"dr-{len(self._programs)+1:03d}",
            "title": payload.get("title", "Demand Response Program"),
            "reason": payload.get("reason", "Manual"),
            "start_time": payload.get("start_time") or now,
            "end_time": payload.get("end_time") or (now + timedelta(hours=2)),
            "target_reduction_kw": float(payload.get("target_reduction_kw", 0)),
            "reward_per_kwh": float(payload.get("reward_per_kwh", 0.1)),
            "status": payload.get("status", "active")
        }
        self._programs.append(program)
        return program


