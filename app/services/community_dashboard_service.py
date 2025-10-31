"""
Data Presentation Service for Energy Square Platform

This module provides data formatting and presentation services
for the web application frontend.
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging
from pathlib import Path
from app.services.community_config import get_community_config, get_scaling_factors, get_community_metrics
from app.services.system_notice_service import SystemNoticeService
from app.services.user_device_service import UserDeviceService

logger = logging.getLogger(__name__)


class DataPresentationService:
    """Service to prepare data for frontend consumption"""
    
    def __init__(self, data_path: str = "artifacts/transformed_data.json"):
        self.data_path = Path(data_path)
        self.data = self._load_data()
        self._config = None
        self._scaling_factors = None
        self._community_metrics = None
        self.notice_service = SystemNoticeService()
        self.device_service = UserDeviceService()
    
    async def _get_config(self):
        """Get community configuration (cached)"""
        if self._config is None:
            self._config = await get_community_config()
        return self._config
    
    async def _get_scaling_factors(self):
        """Get scaling factors (cached)"""
        if self._scaling_factors is None:
            self._scaling_factors = await get_scaling_factors()
        return self._scaling_factors
    
    async def _get_community_metrics(self):
        """Get community metrics (cached)"""
        if self._community_metrics is None:
            self._community_metrics = await get_community_metrics()
        return self._community_metrics
    
    def _load_data(self) -> Dict[str, Any]:
        """Load transformed data"""
        try:
            abs_path = self.data_path.resolve()
            logger.info(f"Loading data from: {abs_path}")

            if not abs_path.exists():
                logger.warning(f"Data file not found: {abs_path}")
                return {}

            with open(abs_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Successfully loaded data with {len(data)} top-level keys")
                return data
        except Exception as e:
            logger.error(f"Error loading data from {self.data_path}: {e}")
            return {}
    
    
    async def get_community_dashboard_data(self) -> Dict[str, Any]:
        """Get data formatted for the community dashboard"""
        try:
            logger.info("Starting community dashboard data generation")
            
            # Get individual service data
            current_generation = await self.get_current_generation()
            current_consumption = await self.get_current_consumption()
            net_balance = self.get_net_balance(current_generation, current_consumption)
            grid_export = self.get_grid_export(current_generation, current_consumption)
            source_breakdown = self.get_energy_source_breakdown(current_generation, current_consumption)
            energy_flow_24h = await self.get_24h_energy_flow()
            
            # Get config for calculations
            config = await self._get_config()
            
            # Get historical data for 24h metrics
            market_data = self.data.get('market_data', {})
            analytics = self.data.get('analytics', {})
            demand_data = market_data.get('demand_data', [])
            pun_prices = market_data.get('pun_prices', [])
            
            # Calculate historical totals
            total_demand = await self._calculate_total_demand_24h(demand_data)
            total_production = self._calculate_total_production_24h(analytics)
            
            # Compute grid interaction metrics via dedicated method
            grid_metrics = await self._get_grid_interaction_metrics(
                generation_kw=current_generation,
                consumption_kw=current_consumption,
                pun_prices=pun_prices,
                demand_points=len(demand_data)
            )

            # Compute carbon metrics via dedicated method
            carbon_metrics = await self.get_carbon_metrics()

            # Aggregate community metrics from individual users (bottom-up)
            community_device_metrics = await self.device_service.aggregate_community_metrics()
            active_members = community_device_metrics.get("user_count", config.total_population)
            
            # Storage network from aggregated battery data
            storage_network = {
                "total_capacity": community_device_metrics.get("total_battery_capacity_kwh", 0) * 1000,  # Convert to Wh for consistency
                "aggregate_soc": community_device_metrics.get("average_battery_soc_pct", 0),
                "distribution": {
                    "north": 0,  # Could be calculated from user locations if needed
                    "south": 0,
                    "center": 0
                },
                "critical_alerts": []
            }

            return {
                "total_energy_flow": {
                    "generation": {
                        "live": current_generation,
                        "history_24h": total_production
                    },
                    "consumption": {
                        "live": current_consumption,
                        "history_24h": total_demand
                    },
                    "net": net_balance,
                    "source_breakdown": source_breakdown
                },
                "storage_network": storage_network,
                "grid_interaction": grid_metrics,
                "participation_summary": {
                    "active_members": active_members,
                    "contribution_tiers": {
                        "gold": config.contribution_tier_gold,
                        "silver": config.contribution_tier_silver,
                        "bronze": config.contribution_tier_bronze
                    },
                    "demand_response_engagement": 0.78
                },
                "carbon_metrics": carbon_metrics,
                "marketplace_activity": {
                    "volume_traded_kwh": total_production * config.trading_volume_percentage,
                    "volume_traded_currency": total_production * config.trading_volume_percentage * config.average_energy_price,
                    "number_of_trades": 45,
                    "price_fluctuation": config.price_fluctuation_range,
                    "top_traders": await self._get_top_traders()
                },
                "alerts_system_notices": await self._get_system_notices(),
                "leaderboards": await self._get_leaderboards()
            }
            
        except Exception as e:
            logger.error(f"Error getting community dashboard data: {e}", exc_info=True)
            return {}
    
    
    
    async def _get_top_traders(self) -> List[Dict[str, Any]]:
        """Get top traders data"""
        config = await self._get_config()
        return [
            {"name": "Energy Trader A", "volume": config.mock_trader_volume, "rank": 1},
            {"name": "Solar Farm B", "volume": config.mock_trader_volume * 0.8, "rank": 2},
            {"name": "Green Energy Co", "volume": config.mock_trader_volume * 0.63, "rank": 3}
        ]
    
    async def _get_system_notices(self) -> List[Dict[str, Any]]:
        """Get community-level system notices."""
        try:
            return await self.notice_service.list_community_alerts(limit=10)
        except Exception as e:
            logger.warning(f"System notices unavailable: {e}")
            return []
    
    def _safe_float(self, value):
        """Convert value to a JSON-safe float"""
        if value is None:
            return 0.0
        if isinstance(value, float):
            if value != value:  # NaN check
                return 0.0
            if value == float('inf') or value == float('-inf'):
                return 0.0
        return float(value)
    
    def _get_latest_pun_price_kwh(self, pun_prices: List[Dict[str, Any]]) -> float:
        """Get the most recent non-null PUN price in €/kWh from transformed data"""
        try:
            if not pun_prices:
                return 0.0
            # Iterate from the end to find a valid price
            for entry in reversed(pun_prices):
                price = entry.get('price_eur_kwh') or entry.get('price_eur_mwh')
                if price is None:
                    continue
                # Convert MWh to kWh if needed
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

    async def get_grid_telemetry(self) -> Dict[str, Any]:
        """Derive grid telemetry from current metrics and config."""
        try:
            config = await self._get_config()
            # Current conditions
            current_gen = await self.get_current_generation()
            current_cons = await self.get_current_consumption()
            stability = 1.0 - abs(current_gen - current_cons) / max(current_cons, 1.0)
            stability = max(0.0, min(1.0, stability))

            # Frequency baseline from config or default 50.0 Hz; +/- 0.2 Hz scaled by stability
            baseline_hz = getattr(config, 'telemetry_baseline_hz', 50.0)
            frequency_hz = baseline_hz + (0.2 * (0.5 - stability))

            # Voltage baseline from config or default 230 V; +/- 5 V scaled by stability
            baseline_v = getattr(config, 'telemetry_nominal_v', 230.0)
            voltage_v = baseline_v + (5.0 * (0.5 - stability))

            # Load percentage: consumed vs (consumed+headroom). Use historical proxy
            # Use average of last 24h consumed as proxy for denominator
            last24 = await self.get_24h_energy_flow()
            avg_consumed = sum([p.get('consumed', 0) for p in last24]) / len(last24) if last24 else max(current_cons, 1.0)
            load_pct = max(0.0, min(100.0, (current_cons / max(avg_consumed, 1.0)) * 100))

            # Renewable percentage from source breakdown (solar share)
            source = self.get_energy_source_breakdown(current_gen, current_cons)
            renewable_pct = max(0.0, min(100.0, source.get('solar', 0.0)))

            return {
                'frequency_hz': round(self._safe_float(frequency_hz), 2),
                'voltage_v': round(self._safe_float(voltage_v), 1),
                'load_pct': round(self._safe_float(load_pct), 0),
                'renewable_pct': round(self._safe_float(renewable_pct), 0),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"Grid telemetry fallback due to error: {e}")
            return {
                'frequency_hz': 50.0,
                'voltage_v': 230.0,
                'load_pct': 0.0,
                'renewable_pct': 0.0,
                'timestamp': datetime.now().isoformat()
            }

    async def get_carbon_metrics(self) -> Dict[str, Any]:
        """Estimate carbon metrics from recent energy flow and config.

        - total_offset_kg: sum of produced energy (kWh) × emission factor
        - baseline_comparison: proxy reduction vs fossil grid using renewable share
        - regional_rank: configurable fallback
        """
        try:
            config = await self._get_config()
            emission_factor = getattr(config, 'emission_factor_kg_per_kwh', 0.35)  # kg CO2 per kWh

            # Use last 24h energy flow for today's offset
            flow = await self.get_24h_energy_flow()
            total_produced_kwh = sum([p.get('produced', 0) for p in flow])
            total_consumed_kwh = sum([p.get('consumed', 0) for p in flow])

            total_offset_kg = self._safe_float(total_produced_kwh * emission_factor)

            # Baseline comparison: renewable share over total consumption as reduction proxy
            renewable_share = 0.0
            if total_consumed_kwh > 0:
                renewable_share = max(0.0, min(1.0, total_produced_kwh / total_consumed_kwh))

            baseline_comparison = self._safe_float(renewable_share)  # 0..1; FE multiplies by 100

            regional_rank = getattr(config, 'regional_rank', 3)

            # Cumulative offset over last 30 days using trends
            trends_30d = await self.get_energy_trends(30)
            produced_30d_kwh = sum([t.get('produced', 0) for t in trends_30d])
            cumulative_offset_kg = self._safe_float(produced_30d_kwh * emission_factor)

            return {
                'total_offset_kg': round(total_offset_kg, 2),
                'baseline_comparison': baseline_comparison,
                'regional_rank': int(regional_rank),
                'cumulative_offset_kg': round(cumulative_offset_kg, 2)
            }
        except Exception as e:
            logger.warning(f"Carbon metrics fallback due to error: {e}")
            return {
                'total_offset_kg': 0.0,
                'baseline_comparison': 0.0,
                'regional_rank': 0,
                'cumulative_offset_kg': 0.0
            }

    async def _get_grid_interaction_metrics(
        self,
        generation_kw: float,
        consumption_kw: float,
        pun_prices: List[Dict[str, Any]],
        demand_points: int
    ) -> Dict[str, Any]:
        """Compute grid interaction metrics: stability index and import/export rates.

        - Stability index: 1 - |net| / max(consumption, 1). Clamped [0,1].
        - Import/Export rate: latest PUN price (€/kWh). Export discounted by 5%.
        """
        try:
            net_kw = generation_kw - consumption_kw
            denom = max(consumption_kw, 1.0)
            stability = 1.0 - abs(net_kw) / denom
            stability = max(0.0, min(1.0, stability))

            latest_price = self._get_latest_pun_price_kwh(pun_prices)
            # If no price found, fall back to 0
            import_rate = latest_price if net_kw < 0 else 0.0
            export_rate = round(latest_price * 0.95, 2) if net_kw > 0 else 0.0

            return {
                "stability_index": self._safe_float(stability),
                "import_rate": self._safe_float(import_rate),
                "export_rate": self._safe_float(export_rate),
                "outage_zones": []
            }
        except Exception as e:
            logger.warning(f"Grid interaction metrics fallback due to error: {e}")
            return {
                "stability_index": 0.9,
                "import_rate": 0.0,
                "export_rate": 0.0,
                "outage_zones": []
            }

    
    async def get_energy_trends(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get energy trends over time based on real data patterns"""
        try:
            logger.info(f"Generating energy trends for {days} days")
            
            # For now, return 24h data. Can be extended to support more days
            if days <= 1:
                return await self.get_24h_energy_flow()
            
            # Generate hourly data for the requested number of days
            trends_data = []
            current_time = datetime.now()
            total_hours = days * 24
            
            for i in range(total_hours):
                # Calculate time for this data point
                data_time = current_time - timedelta(hours=total_hours-i)
                hour = data_time.hour
                
                # Get solar data for this hour
                solar_data = self.data.get('solar_data', {})
                plant_1_data = solar_data.get('plant_1', {}).get('hourly', [])
                plant_2_data = solar_data.get('plant_2', {}).get('hourly', [])
                
                # Calculate generation for this hour using real data only
                generation = self._calculate_real_generation(hour, plant_1_data, plant_2_data)
                
                # Get demand data for this hour using real data only
                demand_data = self.data.get('market_data', {}).get('demand_data', [])
                consumption = await self._calculate_real_consumption(hour, demand_data)
                
                # Calculate net values
                net = generation - consumption
                sold = max(0, net)  # Surplus sold to grid
                bought = max(0, -net)  # Deficit bought from grid
                
                trends_data.append({
                    "date": data_time.isoformat(),
                    "produced": round(generation, 2),
                    "consumed": round(consumption, 2),
                    "sold": round(sold, 2),
                    "bought": round(bought, 2),
                    "carbon_offset": 0,  # No carbon data available
                    "efficiency": self._calculate_efficiency(generation, consumption)
                })
            
            logger.info(f"Generated {len(trends_data)} energy trend data points for {days} days")
            return trends_data
            
        except Exception as e:
            logger.error(f"Error getting energy trends: {e}", exc_info=True)
            return []

    async def get_demand_response_metrics(self) -> Dict[str, Any]:
        """Compute demand response metrics and simple recommendations.

        Heuristics:
        - Engagement from config (demand_response_engagement if present) or 0.75 default
        - Potential shed proportional to current consumption (10%)
        - Price signal from latest PUN price
        - Create an event if price is in top quantile or deficit is large
        """
        try:
            config = await self._get_config()
            # Current conditions
            current_gen = await self.get_current_generation()
            current_cons = await self.get_current_consumption()
            net = current_gen - current_cons

            # Price signal
            pun_prices = self.data.get('market_data', {}).get('pun_prices', [])
            price_signal = self._get_latest_pun_price_kwh(pun_prices)

            # Engagement and shed potential
            engagement = getattr(config, 'demand_response_engagement', 0.75)
            potential_shed_kw = max(0.0, current_cons * 0.10)

            # Simple event trigger
            active_events: List[Dict[str, Any]] = []
            recommendations: List[str] = []

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

            if net < 0:  # deficit
                recommendations.append("Shift non-critical consumption to off-peak hours")

            return {
                "engagement": self._safe_float(engagement),
                "potential_shed_kw": self._safe_float(potential_shed_kw),
                "price_signal_eur_kwh": self._safe_float(price_signal),
                "active_events": active_events,
                "recommendations": recommendations
            }
        except Exception as e:
            logger.warning(f"Demand response metrics fallback due to error: {e}")
            return {
                "engagement": 0.75,
                "potential_shed_kw": 0.0,
                "price_signal_eur_kwh": 0.0,
                "active_events": [],
                "recommendations": []
            }
    
    def _calculate_real_generation(self, hour: int, plant_1_data: List[Dict], plant_2_data: List[Dict]) -> float:
        """Calculate generation using only real solar data"""
        if not plant_1_data or not plant_2_data:
            return 0.0
        
        plant_1_hour_data = [d for d in plant_1_data if d.get('hour') == hour]
        plant_2_hour_data = [d for d in plant_2_data if d.get('hour') == hour]
        
        plant_1_avg = 0
        plant_2_avg = 0
        
        if plant_1_hour_data:
            plant_1_powers = [d.get('AC_POWER', 0) for d in plant_1_hour_data if d.get('AC_POWER', 0) > 0]
            plant_1_avg = sum(plant_1_powers) / len(plant_1_powers) if plant_1_powers else 0
        
        if plant_2_hour_data:
            plant_2_powers = [d.get('AC_POWER', 0) for d in plant_2_hour_data if d.get('AC_POWER', 0) > 0]
            plant_2_avg = sum(plant_2_powers) / len(plant_2_powers) if plant_2_powers else 0
        
        # Use real data without artificial scaling
        total_real_generation = plant_1_avg + plant_2_avg
        return self._safe_float(total_real_generation)
    
    async def _calculate_real_consumption(self, hour: int, demand_data: List[Dict]) -> float:
        """Calculate consumption using only real demand data with interpolation"""
        if not demand_data:
            return 0.0
        
        current_hour_data = [d for d in demand_data if d.get('hour') == hour]
        
        if not current_hour_data:
            # Try to interpolate from nearby hours
            return await self._interpolate_consumption(hour, demand_data)
        
        total_demand_mw = 0
        valid_periods = 0
        
        for period_data in current_hour_data:
            regional_demand = 0
            for region in ['Calabria', 'Sardegna', 'Sicilia', 'North', 'Central-northern Italy', 'Centeral-southern Italy', 'Southern-Italy']:
                value = period_data.get(region, 0)
                if value is not None and not (isinstance(value, float) and (value != value)):
                    regional_demand += float(value)
            
            if regional_demand > 0:
                total_demand_mw += regional_demand
                valid_periods += 1
        
        if valid_periods > 0:
            avg_demand_mw = total_demand_mw / valid_periods
            # Scale to community level using configurable fallback scaling
            config = await self._get_config()
            return self._safe_float(avg_demand_mw * 1000 * config.fallback_regional_scaling)
        
        return 0.0
    
    async def _interpolate_consumption(self, target_hour: int, demand_data: List[Dict]) -> float:
        """Interpolate consumption from nearby hours when exact hour data is missing"""
        # Find the closest hours with data
        available_hours = sorted([d.get('hour', 0) for d in demand_data if d.get('hour') is not None])
        
        if not available_hours:
            return 0.0
        
        # Find the two closest hours for interpolation
        before_hour = None
        after_hour = None
        
        for h in available_hours:
            if h < target_hour:
                before_hour = h
            elif h > target_hour and after_hour is None:
                after_hour = h
                break
        
        # If we only have data from one side, use that
        if before_hour is None and after_hour is not None:
            return await self._get_hour_consumption(after_hour, demand_data)
        elif before_hour is not None and after_hour is None:
            return await self._get_hour_consumption(before_hour, demand_data)
        elif before_hour is None and after_hour is None:
            return 0.0
        
        # Interpolate between the two hours
        before_consumption = await self._get_hour_consumption(before_hour, demand_data)
        after_consumption = await self._get_hour_consumption(after_hour, demand_data)
        
        # Linear interpolation
        if after_hour == before_hour:
            return before_consumption
        
        weight = (target_hour - before_hour) / (after_hour - before_hour)
        interpolated = before_consumption + weight * (after_consumption - before_consumption)
        
        return self._safe_float(interpolated)
    
    async def _get_hour_consumption(self, hour: int, demand_data: List[Dict]) -> float:
        """Get consumption for a specific hour"""
        hour_data = [d for d in demand_data if d.get('hour') == hour]
        
        if not hour_data:
            return 0.0
        
        total_demand_mw = 0
        valid_periods = 0
        
        for period_data in hour_data:
            regional_demand = 0
            for region in ['Calabria', 'Sardegna', 'Sicilia', 'North', 'Central-northern Italy', 'Centeral-southern Italy', 'Southern-Italy']:
                value = period_data.get(region, 0)
                if value is not None and not (isinstance(value, float) and (value != value)):
                    regional_demand += float(value)
            
            if regional_demand > 0:
                total_demand_mw += regional_demand
                valid_periods += 1
        
        if valid_periods > 0:
            avg_demand_mw = total_demand_mw / valid_periods
            config = await self._get_config()
            return self._safe_float(avg_demand_mw * 1000 * config.regional_to_community_scaling)
        
        return 0.0
    
    def _calculate_efficiency(self, generation: float, consumption: float) -> float:
        """Calculate efficiency based on real data"""
        if consumption <= 0:
            return 0.0
        
        efficiency = generation / consumption
        # Cap efficiency at 1.0 (100%)
        return self._safe_float(min(1.0, efficiency))
    
    def test_community_data(self) -> Dict[str, Any]:
        """Test community dashboard data generation"""
        try:
            logger.info("Testing community dashboard data generation")
            
            # Test data loading
            logger.info("Testing data loading...")
            test_data = self.data
            logger.info(f"Data loaded successfully: {len(test_data)} top-level keys")
            
            # Test market data access
            logger.info("Testing market data access...")
            market_data = test_data.get('market_data', {})
            logger.info(f"Market data keys: {list(market_data.keys())}")
            
            # Test analytics access
            logger.info("Testing analytics access...")
            analytics = test_data.get('analytics', {})
            logger.info(f"Analytics keys: {list(analytics.keys())}")
            
            # Test specific data access
            pun_prices = market_data.get('pun_prices', [])
            demand_data = market_data.get('demand_data', [])
            logger.info(f"PUN prices count: {len(pun_prices)}")
            logger.info(f"Demand data count: {len(demand_data)}")
            
            return {
                "status": "success",
                "message": "Community dashboard test passed",
                "data_keys": list(test_data.keys()),
                "market_data_keys": list(market_data.keys()),
                "analytics_keys": list(analytics.keys()),
                "pun_prices_count": len(pun_prices),
                "demand_data_count": len(demand_data)
            }
            
        except Exception as e:
            logger.error(f"Community dashboard test failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Community dashboard test failed: {str(e)}",
                "error_type": type(e).__name__
            }
    
    async def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information including community configuration"""
        config = await self._get_config()
        return {
            "status": "ok",
            "message": "Analytics router is working",
            "data_transformer_available": True,
            "data_presentation_available": True,
            "timestamp": datetime.now().isoformat(),
            "community_config": {
                "total_households": config.total_households,
                "total_solar_capacity": config.total_solar_capacity,
                "total_community_consumption": config.total_community_consumption,
                "regional_to_community_scaling": config.regional_to_community_scaling,
                "demand_scaling_factor": config.demand_scaling_factor,
                "trading_volume_percentage": config.trading_volume_percentage
            }
        }
    
    
    async def _get_leaderboards(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get leaderboards data"""
        config = await self._get_config()
        return {
            "top_producers": [
                {"name": "Solar Farm Alpha", "production": config.mock_solar_farm_production, "rank": 1},
                {"name": "Green Energy Co", "production": config.mock_solar_farm_production * 0.84, "rank": 2},
                {"name": "Eco Power Ltd", "production": config.mock_solar_farm_production * 0.72, "rank": 3}
            ],
            "most_efficient": [
                {"name": "Efficiency Master", "efficiency": config.mock_efficiency_high, "rank": 1},
                {"name": "Solar Expert", "efficiency": config.mock_efficiency_medium, "rank": 2},
                {"name": "Green Tech", "efficiency": 0.89, "rank": 3}
            ],
            "carbon_offsetters": [
                {"name": "Eco Warrior", "offset": config.mock_carbon_offset, "rank": 1},
                {"name": "Green Champion", "offset": config.mock_carbon_offset * 0.9, "rank": 2},
                {"name": "Climate Hero", "offset": config.mock_carbon_offset * 0.8, "rank": 3}
            ]
        }

    # ============================================================================
    # INDIVIDUAL SERVICE METHODS
    # ============================================================================

    async def get_current_generation(self) -> float:
        """Get current solar generation in kW"""
        try:
            logger.info("Calculating current generation")
            current_hour = datetime.now().hour
            
            # Get real solar data
            solar_data = self.data.get('solar_data', {})
            plant_1_data = solar_data.get('plant_1', {}).get('hourly', [])
            plant_2_data = solar_data.get('plant_2', {}).get('hourly', [])
            
            if not plant_1_data or not plant_2_data:
                logger.warning("No solar data available")
                return 0.0
            
            # Filter data for the current hour
            plant_1_hour_data = [d for d in plant_1_data if d.get('hour') == current_hour]
            plant_2_hour_data = [d for d in plant_2_data if d.get('hour') == current_hour]
            
            # Calculate average AC_POWER for this hour from real data
            plant_1_avg = 0
            plant_2_avg = 0
            
            if plant_1_hour_data:
                plant_1_powers = [d.get('AC_POWER', 0) for d in plant_1_hour_data if d.get('AC_POWER', 0) > 0]
                plant_1_avg = sum(plant_1_powers) / len(plant_1_powers) if plant_1_powers else 0
            
            if plant_2_hour_data:
                plant_2_powers = [d.get('AC_POWER', 0) for d in plant_2_hour_data if d.get('AC_POWER', 0) > 0]
                plant_2_avg = sum(plant_2_powers) / len(plant_2_powers) if plant_2_powers else 0
            
            # Use real solar patterns without artificial scaling
            total_real_generation = plant_1_avg + plant_2_avg
            live_generation = self._safe_float(total_real_generation)
            
            logger.info(f"Current generation - Plant 1: {plant_1_avg:.2f} kW, Plant 2: {plant_2_avg:.2f} kW, Total: {live_generation:.2f} kW")
            return live_generation
            
        except Exception as e:
            logger.error(f"Error calculating current generation: {e}")
            return 0.0

    async def get_current_consumption(self) -> float:
        """Get current community consumption in kW"""
        try:
            logger.info("Calculating current consumption")
            current_hour = datetime.now().hour
            
            # Get demand data
            market_data = self.data.get('market_data', {})
            demand_data = market_data.get('demand_data', [])
            
            if not demand_data:
                logger.warning("No demand data available")
                return 0.0
            
            # Find demand data for the current hour
            current_hour_data = [d for d in demand_data if d.get('hour') == current_hour]
            
            if not current_hour_data:
                # Try to interpolate from nearby hours
                return await self._interpolate_consumption(current_hour, demand_data)
            
            # Calculate average demand for this hour across all periods
            total_demand_mw = 0
            valid_periods = 0
            
            for period_data in current_hour_data:
                # Sum up regional demand (in MW)
                regional_demand = 0
                for region in ['Calabria', 'Sardegna', 'Sicilia', 'North', 'Central-northern Italy', 'Centeral-southern Italy', 'Southern-Italy']:
                    value = period_data.get(region, 0)
                    if value is not None and not (isinstance(value, float) and (value != value)):  # Check for NaN
                        regional_demand += float(value)
                
                if regional_demand > 0:
                    total_demand_mw += regional_demand
                    valid_periods += 1
            
            if valid_periods > 0:
                avg_demand_mw = total_demand_mw / valid_periods
                # Use configuration-based scaling instead of hardcoded values
                config = await self._get_config()
                live_consumption = self._safe_float(avg_demand_mw * 1000 * config.regional_to_community_scaling)
                
                logger.info(f"Current consumption - Regional demand: {avg_demand_mw:.2f} MW, Community consumption: {live_consumption:.2f} kW (scaling: {config.regional_to_community_scaling})")
                return live_consumption
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error calculating current consumption: {e}")
            return 0.0

    def get_net_balance(self, generation: float, consumption: float) -> float:
        """Calculate net energy balance (generation - consumption)"""
        try:
            net_balance = generation - consumption
            logger.info(f"Net balance: {generation:.2f} kW - {consumption:.2f} kW = {net_balance:.2f} kW")
            return self._safe_float(net_balance)
        except Exception as e:
            logger.error(f"Error calculating net balance: {e}")
            return 0.0

    def get_grid_export(self, generation: float, consumption: float) -> float:
        """Calculate grid export (surplus energy sold to grid)"""
        try:
            grid_export = max(0, generation - consumption)  # Only positive surplus
            logger.info(f"Grid export: {grid_export:.2f} kW")
            return self._safe_float(grid_export)
        except Exception as e:
            logger.error(f"Error calculating grid export: {e}")
            return 0.0

    def get_energy_source_breakdown(self, generation: float, consumption: float) -> Dict[str, float]:
        """Get energy source breakdown percentages (community-level: solar + grid only)"""
        try:
            total_power = max(generation, consumption)  # Use the larger value as total
            
            if total_power <= 0:
                return {
                    "solar": 0.0,
                    "grid": 0.0
                }
            
            solar_percentage = (generation / total_power) * 100
            grid_percentage = max(0, (consumption - generation) / total_power) * 100 if consumption > generation else 0
            
            breakdown = {
                "solar": self._safe_float(solar_percentage),
                "grid": self._safe_float(grid_percentage)
            }
            
            logger.info(f"Source breakdown - Solar: {solar_percentage:.1f}%, Grid: {grid_percentage:.1f}%")
            return breakdown
            
        except Exception as e:
            logger.error(f"Error calculating energy source breakdown: {e}")
            return {"solar": 0.0, "grid": 0.0}

    async def get_24h_energy_flow(self) -> List[Dict[str, Any]]:
        """Get 24-hour energy flow data for charts"""
        try:
            logger.info("Generating 24h energy flow data")
            
            # Generate hourly data for the last 24 hours
            trends_data = []
            current_time = datetime.now()
            
            for i in range(24):  # Last 24 hours
                # Calculate time for this data point
                data_time = current_time - timedelta(hours=24-i)
                hour = data_time.hour
                
                # Get solar data for this hour
                solar_data = self.data.get('solar_data', {})
                plant_1_data = solar_data.get('plant_1', {}).get('hourly', [])
                plant_2_data = solar_data.get('plant_2', {}).get('hourly', [])
                
                # Calculate generation for this hour using real data only
                generation = self._calculate_real_generation(hour, plant_1_data, plant_2_data)
                
                # Get demand data for this hour using real data only
                demand_data = self.data.get('market_data', {}).get('demand_data', [])
                consumption = await self._calculate_real_consumption(hour, demand_data)
                
                # Calculate net values
                net = generation - consumption
                sold = max(0, net)  # Surplus sold to grid
                bought = max(0, -net)  # Deficit bought from grid
                
                trends_data.append({
                    "date": data_time.isoformat(),
                    "produced": round(generation, 2),
                    "consumed": round(consumption, 2),
                    "sold": round(sold, 2),
                    "bought": round(bought, 2),
                    "carbon_offset": 0,  # No carbon data available
                    "efficiency": self._calculate_efficiency(generation, consumption)
                })
            
            logger.info(f"Generated {len(trends_data)} 24h energy flow data points")
            return trends_data
            
        except Exception as e:
            logger.error(f"Error generating 24h energy flow: {e}")
            return []

    async def _calculate_total_demand_24h(self, demand_data: List[Dict]) -> float:
        """Calculate total demand for 24h history"""
        try:
            if not demand_data:
                return 0.0
            
            # Filter out NaN/None values and convert to float
            demand_values = []
            for d in demand_data:
                value = d.get('Total Italy', 0)
                if value is not None and not (isinstance(value, float) and (value != value)):  # Check for NaN
                    demand_values.append(float(value))
            
            if demand_values:
                config = await self._get_config()
                total_demand = sum(demand_values) * config.demand_scaling_factor
                logger.info(f"Calculated 24h total demand from {len(demand_values)} valid values: {total_demand:.2f} (scaling: {config.demand_scaling_factor})")
                return self._safe_float(total_demand)
            else:
                logger.warning("No valid demand values found for 24h calculation")
                return 0.0
                
        except Exception as e:
            logger.warning(f"Error calculating 24h total demand: {e}")
            return 0.0

    def _calculate_total_production_24h(self, analytics: Dict) -> float:
        """Calculate total production for 24h history"""
        try:
            plant_1_stats = analytics.get('plant_1_stats', {})
            plant_2_stats = analytics.get('plant_2_stats', {})
            total_production = plant_1_stats.get('total_production_kwh', 0) + plant_2_stats.get('total_production_kwh', 0)
            
            logger.info(f"Calculated 24h total production: {total_production:.2f} kWh")
            return self._safe_float(total_production)
            
        except Exception as e:
            logger.warning(f"Error calculating 24h total production: {e}")
            return 0.0
