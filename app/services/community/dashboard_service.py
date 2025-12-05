"""
Community Dashboard Service

Uses the community simulation engine to generate dashboard data from normalized patterns.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine

logger = logging.getLogger(__name__)


class CommunityDashboardService:
    """Service to generate community dashboard data using the simulation engine."""
    
    def __init__(self):
        """Initialize the service and setup simulation engine."""
        # Initialize model service
        self.model_service = CommunityModelService(watch_for_changes=True)
        
        # Try to use background service, fallback to direct engine
        self.background_service = None
        self.simulation_engine = None
        self._use_background = False
        
        try:
            from app.services.infrastructure.background_service import get_background_service
            self.background_service = get_background_service()
            # Don't access simulation_engine directly - background service uses lazy initialization
            # We'll access it through background_service methods when needed
            self._use_background = True
            logger.info("CommunityDashboardService initialized with background simulation service")
        except Exception as e:
            logger.warning(f"Background service not available, using direct engine: {e}")
            self.simulation_engine = CommunitySimulationEngine(
                model_service=self.model_service
            )
            self._use_background = False
            logger.info("CommunityDashboardService initialized with simulation engine")
    
    def get_data_at_timestamp(self, target_dt: datetime) -> Optional[Dict[str, Any]]:
        """Get community data at a specific timestamp."""
        try:
            # Use cached data from background service if available
            if self._use_background and self.background_service:
                result = self.background_service.get_community_data(target_dt)
            else:
                # Fallback to direct simulation - ensure engine is initialized
                if self.simulation_engine is None:
                    self.simulation_engine = CommunitySimulationEngine(model_service=self.model_service)
                result = self.simulation_engine.simulate_community(target_dt)
            
            if result:
                return self._convert_to_dashboard_format(result)
            return None
        except Exception as e:
            logger.error(f"Error getting data at timestamp: {e}", exc_info=True)
            return None
    
    def _convert_to_dashboard_format(self, simulation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Convert simulation result to dashboard format."""
        if not simulation_result:
            return None
        
        # Extract community aggregates
        total_generation = simulation_result.get("total_generation_kw", 0.0)
        total_consumption = simulation_result.get("total_consumption_kw", 0.0)
        total_net_balance = simulation_result.get("total_net_balance_kw", 0.0)
        total_grid_export = simulation_result.get("total_grid_export_kw", 0.0)
        total_grid_import = simulation_result.get("total_grid_import_kw", 0.0)
        
        # Calculate solar generation from members
        members = simulation_result.get("members", [])
        solar_generation = sum(m.get("solar_generation_kw", 0.0) for m in members)
        fuel_cell_generation = 0.0  # Fuel cell generation not supported in current model
        
        # Get model for all configuration
        model = self.model_service.get_model()
        if not model:
            logger.warning("Model not available, cannot get configuration")
            return self._default_community_data()
        
        cc = model.community_control
        
        # Get battery stats from simulation (prefer aggregated values if available)
        # Default SOC if not available from simulation (midpoint of typical Li-ion range: 10%-95%)
        default_soc = 0.525  # (0.10 + 0.95) / 2.0
        
        # Use aggregated storage metrics from simulation if available
        storage_avg_soc = simulation_result.get("storage_avg_soc", None)
        storage_members_count = simulation_result.get("storage_members_count", 0)
        storage_charging_count = simulation_result.get("storage_charging_count", 0)
        storage_discharging_count = simulation_result.get("storage_discharging_count", 0)
        storage_idle_count = simulation_result.get("storage_idle_count", 0)
        
        # Calculate storage metrics from model configuration
        total_battery_capacity = sum(
            m.assets.battery_capacity_kwh 
            for m in model.members 
            if m.assets.battery_capacity_kwh > 0
        )
        
        # Use simulated average SOC if available, otherwise calculate from members
        if storage_avg_soc is not None:
            avg_soc = storage_avg_soc
        else:
            battery_socs = [m.get("battery_soc", default_soc) for m in members if m.get("battery_soc", 0) > 0]
            avg_soc = sum(battery_socs) / len(battery_socs) if battery_socs else default_soc
        
        available_energy = total_battery_capacity * avg_soc
        
        # Battery flow status (charging vs discharging)
        total_battery_power = simulation_result.get("total_battery_power_kw", 0.0)
        battery_status = "idle"
        if total_battery_power < -0.1:
            battery_status = "charging"
        elif total_battery_power > 0.1:
            battery_status = "discharging"
        
        # Grid metrics - nominal values from config
        nominal_voltage = cc.grid_voltage_v
        nominal_frequency = cc.grid_frequency_hz
        
        # Calculate actual grid metrics from simulation state
        # Grid voltage/frequency would come from sensors in real system
        # For simulation, use nominal values with small variations based on load
        load_factor = min(1.0, total_consumption / max(total_generation, 1.0))
        
        # Simulate voltage drop under load (0.5% per 10% load)
        grid_voltage = nominal_voltage * (1.0 - (load_factor * 0.005))
        
        # Simulate frequency variation based on power balance
        power_balance = abs(total_generation - total_consumption)
        balance_factor = power_balance / max(total_consumption, 1.0)
        grid_frequency = nominal_frequency * (1.0 - (balance_factor * 0.001))
        
        # Calculate grid stability index (0-100) based on:
        # 1. Voltage stability (within ±5% = good)
        voltage_deviation = abs(grid_voltage - nominal_voltage) / nominal_voltage
        voltage_score = max(0, 100 - (voltage_deviation / 0.05) * 30)  # 30 points for voltage
        
        # 2. Frequency stability (within ±0.5Hz = good)
        frequency_deviation = abs(grid_frequency - nominal_frequency)
        frequency_score = max(0, 100 - (frequency_deviation / 0.5) * 30)  # 30 points for frequency
        
        # 3. Power balance (generation ≈ consumption = good)
        balance_score = max(0, 100 - (balance_factor * 40))  # 40 points for balance
        
        # Weighted stability index
        stability_index = (voltage_score * 0.3 + frequency_score * 0.3 + balance_score * 0.4)
        stability_index = max(0, min(100, stability_index))
        
        # Renewable percentage
        renewable_pct = (solar_generation / total_generation * 100.0) if total_generation > 0 else 0.0
        
        # Grid load percentage - calculate reference from total community capacity
        total_load_capacity = sum(m.assets.load_capacity_kw for m in model.members)
        grid_load_pct = (total_consumption / total_load_capacity * 100.0) if total_load_capacity > 0 else 0.0
        grid_load_pct = min(100.0, grid_load_pct)
        
        # Convert timestamp to ISO string if it's a datetime
        timestamp = simulation_result.get("timestamp")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        
        return {
            'timestamp': timestamp,
            'total_generation_kw': round(total_generation, 2),
            'solar_generation_kw': round(solar_generation, 2),
            'fuel_cell_generation_kw': round(fuel_cell_generation, 2),
            'total_consumption_kw': round(total_consumption, 2),
            'net_balance_kw': round(total_net_balance, 2),
            'grid_import_kw': round(total_grid_import, 2),
            'grid_export_kw': round(total_grid_export, 2),
            
            # Storage network metrics
            'storage_network_capacity_kwh': round(total_battery_capacity, 2),
            'current_soc_pct': round(avg_soc * 100.0, 1),
            'storage_available_energy_kwh': round(available_energy, 2),
            'storage_battery_power_kw': round(total_battery_power, 2),
            'storage_status': battery_status,
            'storage_members_count': storage_members_count,
            'storage_charging_count': storage_charging_count,
            'storage_discharging_count': storage_discharging_count,
            'storage_idle_count': storage_idle_count,
            
            # Grid metrics
            'grid_voltage_v': round(grid_voltage, 2),
            'grid_frequency_hz': round(grid_frequency, 2),
            'grid_stability_index': round(stability_index, 2),
            'renewable_pct': round(renewable_pct, 1),
            'grid_load_pct': round(grid_load_pct, 1),
            
            # Market rates
            'import_rate_usd_per_kwh': model.community_control.import_rate_usd_per_kwh,
            'export_rate_usd_per_kwh': model.community_control.export_rate_usd_per_kwh,
            
            # Outages and carbon
            'outage_zones_list': '',
            'outage_zones_count': 0,
            'carbon_offset_kg': round(total_generation * model.community_control.carbon_offset_factor_kg_per_kwh, 2),
            'cumulative_carbon_offset_kg': 0.0,
            
            # Demand Response metrics (directly from simulation)
            'demand_response': simulation_result.get('demand_response', {
                "active_event_count": 0,
                "participating_member_count": 0,
                "aggregate_generation_kw": total_generation,
                "aggregate_consumption_kw": total_consumption,
                "net_balance_kw": total_net_balance,
                "potential_shed_kw": total_consumption * 0.2,
                "actual_reduction_kw": 0.0,
                "price_signal_usd_per_kwh": 0.0,
                "active_events": []
            }),
        }
    
    async def get_community_dashboard_data(
        self, 
        include_trends: bool = False, 
        trends_days: int = 30
    ) -> Dict[str, Any]:
        """
        Get complete community dashboard data.
        
        Returns data matching the frontend's expected structure.
        """
        model = self.model_service.get_model()
        if model is None:
            logger.warning("Model not loaded, returning defaults")
            return self._default_community_data()
        
        now = datetime.now(ZoneInfo(model.community.timezone))
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get current data (from simulation engine)
        current_data = self.get_data_at_timestamp(now)
        
        if not current_data:
            logger.warning("No current data found, returning defaults")
            return self._default_community_data()
        
        # Get simulation result for member details
        try:
            if self._use_background and self.background_service:
                simulation_result = self.background_service.get_community_data(now)
            else:
                if self.simulation_engine is None:
                    self.simulation_engine = CommunitySimulationEngine(model_service=self.model_service)
                simulation_result = self.simulation_engine.simulate_community(now)
            members_list = simulation_result.get("members", []) if simulation_result else []
        except Exception as e:
            logger.error(f"Error simulating community at current time: {e}", exc_info=True)
            members_list = []
            simulation_result = {}
        
        # Get 24h totals - ONLY use background service cached data, don't calculate synchronously
        period_24h = {
            'generation_kwh': 0.0,
            'consumption_kwh': 0.0,
            'export_kwh': 0.0,
            'import_kwh': 0.0,
            'carbon_offset_kg': 0.0,
        }
        
        # Only try to get 24h totals from background service if available (cached data)
        # Don't calculate synchronously to avoid hanging
        if self._use_background and self.background_service:
            try:
                # Try to get hourly history from background service
                history = self.background_service.get_hourly_history(hours=24)
                if history:
                    for entry in history:
                        data = entry.get('data', {})
                        interval_hours = 1.0
                        period_24h['generation_kwh'] += data.get('total_generation_kw', 0) * interval_hours
                        period_24h['consumption_kwh'] += data.get('total_consumption_kw', 0) * interval_hours
                        period_24h['export_kwh'] += data.get('total_grid_export_kw', 0) * interval_hours
                        period_24h['import_kwh'] += data.get('total_grid_import_kw', 0) * interval_hours
                        if model:
                            period_24h['carbon_offset_kg'] += data.get('total_generation_kw', 0) * model.community_control.carbon_offset_factor_kg_per_kwh * interval_hours
            except Exception as e:
                logger.debug(f"Could not get 24h totals from background service: {e}")
                # Continue with zeros - background service will populate this over time
        
        # Build response matching schema
        response = {
            "total_energy_flow": {
                "generation": {
                    "live": current_data.get('total_generation_kw', 0),
                    "history_24h": round(period_24h.get('generation_kwh', 0), 2),
                },
                "consumption": {
                    "live": current_data.get('total_consumption_kw', 0),
                    "history_24h": round(period_24h.get('consumption_kwh', 0), 2),
                },
                "net": current_data.get('net_balance_kw', 0),
                "grid_export_kw": current_data.get('grid_export_kw', 0),
                "grid_import_kw": current_data.get('grid_import_kw', 0),
                "source_breakdown": {
                    "solar": current_data.get('solar_generation_kw', 0),
                    "fuel_cell": current_data.get('fuel_cell_generation_kw', 0),
                    "grid": current_data.get('grid_import_kw', 0),
                }
            },
            
            "storage_network": {
                "total_capacity": current_data.get('storage_network_capacity_kwh', 0),
                "aggregate_soc": current_data.get('current_soc_pct', 0),
                "available_energy": current_data.get('storage_available_energy_kwh', 0),
                "battery_power_kw": current_data.get('storage_battery_power_kw', 0),
                "status": current_data.get('storage_status', 'idle'),
                "members_with_storage": current_data.get('storage_members_count', 0),
                "charging_count": current_data.get('storage_charging_count', 0),
                "discharging_count": current_data.get('storage_discharging_count', 0),
                "idle_count": current_data.get('storage_idle_count', 0),
                "critical_alerts": []
            },
            
            "grid_interaction": {
                "stability_index": current_data.get('grid_stability_index', 0),
                "frequency_hz": current_data.get('grid_frequency_hz', 0),
                "voltage_v": current_data.get('grid_voltage_v', 0),
                "import_rate": current_data.get('import_rate_usd_per_kwh', model.community_control.import_rate_usd_per_kwh),
                "export_rate": current_data.get('export_rate_usd_per_kwh', model.community_control.export_rate_usd_per_kwh),
                "renewable_pct": current_data.get('renewable_pct', 0),
                "grid_load_pct": current_data.get('grid_load_pct', 0),
                "outage_zones": current_data.get('outage_zones_list', '').split(',') if current_data.get('outage_zones_list') and current_data.get('outage_zones_list') != '' else [],
                "outage_zones_count": int(current_data.get('outage_zones_count', 0)),
            },
            
            "participation_summary": {
                "active_members": len([m for m in model.members]) if model else 0,
                "contribution_tiers": None,  # Will be implemented with leaderboards based on actual simulation performance
                "demand_response_engagement": None,
            },
            
            "carbon_metrics": {
                "today_offset_kg": round(period_24h.get('carbon_offset_kg', 0), 2),
                "cumulative_offset_kg": round(current_data.get('cumulative_carbon_offset_kg', 0), 2),
                "vs_fossil_grid_reduction_pct": round(
                    (period_24h.get('carbon_offset_kg', 0) / max(period_24h.get('consumption_kwh', 1), 1)) 
                    * model.community_control.carbon_offset_factor_kg_per_kwh * 100.0, 
                    1
                ) if period_24h.get('consumption_kwh', 0) > 0 else 0.0,
                "regional_rank": 0,
            },
            
            "marketplace_activity": await self._get_marketplace_stats_from_api(),
            
            "p2p_transaction_history": await self._get_p2p_transaction_history(),
            
            "alerts_system_notices": [],
            
            "leaderboards": {
                "top_producers": [],
                "most_efficient": [],
                "carbon_offsetters": [],
            }
        }
        
        # Optionally include energy trends - ONLY use background service cached data
        # Don't calculate trends synchronously to avoid hanging
        if include_trends:
            try:
                # Only get trends if background service has cached data
                if self._use_background and self.background_service:
                    # Use cached hourly history from background service
                    history = self.background_service.get_hourly_history(hours=min(trends_days * 24, 168))  # Max 7 days
                    if history:
                        response["energy_trends"] = [
                            {
                                "date": entry.get('timestamp', ''),
                                "produced": round(entry.get('data', {}).get('total_generation_kw', 0), 2),
                                "consumed": round(entry.get('data', {}).get('total_consumption_kw', 0), 2),
                                "sold": round(entry.get('data', {}).get('total_grid_export_kw', 0), 2),
                                "bought": round(entry.get('data', {}).get('total_grid_import_kw', 0), 2),
                                "carbon_offset": round(
                                    entry.get('data', {}).get('total_generation_kw', 0) * 
                                    (model.community_control.carbon_offset_factor_kg_per_kwh if model else 0.5), 
                                    2
                                ),
                                "efficiency": 100.0 if entry.get('data', {}).get('total_consumption_kw', 0) > 0 else 0.0,
                            }
                            for entry in history
                        ]
                    else:
                        # No cached data yet - return empty array, background service will populate
                        response["energy_trends"] = []
                        logger.debug("No cached trends data available from background service yet")
                else:
                    # No background service - return empty array rather than calculating synchronously
                    response["energy_trends"] = []
                    logger.debug("Trends requested but background service not available - returning empty array")
            except Exception as e:
                logger.error(f"Failed to get energy trends from background service: {e}", exc_info=True)
                response["energy_trends"] = []  # Return empty array on error
        
        return response
    
    async def get_energy_trends(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get energy trends over time for charts."""
        model = self.model_service.get_model()
        if model is None:
            return []
        
        now = datetime.now(ZoneInfo(model.community.timezone))
        
        try:
            # Limit days to prevent hanging (max 30 days)
            days = min(days, 30)
            
            if days == 1:
                start_dt = now - timedelta(hours=24)
                return self._get_hourly_trends(start_dt, now)
            else:
                start_dt = now - timedelta(days=days)
                return self._get_daily_trends(start_dt, now)
        except Exception as e:
            logger.error(f"Error generating energy trends: {e}", exc_info=True)
            return []
    
    def _get_hourly_trends(self, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        """Get hourly aggregated energy trends."""
        trends = []
        try:
            current_hour = start_dt.replace(minute=0, second=0, microsecond=0)
            
            # Process hourly data points (max 24 hours for performance)
            max_hours = 24
            iteration = 0
            
            while current_hour <= end_dt and iteration < max_hours:
                try:
                    hour_end = current_hour + timedelta(hours=1)
                    totals = self._get_period_totals(current_hour, min(hour_end, end_dt))
                    
                    trends.append({
                        "date": current_hour.isoformat(),
                        "produced": round(totals.get('generation_kwh', 0), 2),
                        "consumed": round(totals.get('consumption_kwh', 0), 2),
                        "sold": round(totals.get('export_kwh', 0), 2),
                        "bought": round(totals.get('import_kwh', 0), 2),
                        "carbon_offset": round(totals.get('carbon_offset_kg', 0), 2),
                        "efficiency": 100.0 if totals.get('consumption_kwh', 0) > 0 else 0.0,
                    })
                    
                    current_hour = hour_end
                    iteration += 1
                except Exception as e:
                    logger.error(f"Error processing hour {current_hour}: {e}", exc_info=True)
                    # Add empty data point and continue
                    trends.append({
                        "date": current_hour.isoformat(),
                        "produced": 0.0,
                        "consumed": 0.0,
                        "sold": 0.0,
                        "bought": 0.0,
                        "carbon_offset": 0.0,
                        "efficiency": 0.0,
                    })
                    current_hour += timedelta(hours=1)
                    iteration += 1
        except Exception as e:
            logger.error(f"Error in _get_hourly_trends: {e}", exc_info=True)
        
        return trends
    
    def _get_daily_trends(self, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        """Get daily aggregated energy trends."""
        trends = []
        current_day = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Limit to max 30 days for performance
        max_days = 30
        iteration = 0
        
        try:
            while current_day <= end_dt and iteration < max_days:
                try:
                    day_end = current_day + timedelta(days=1)
                    totals = self._get_period_totals(current_day, min(day_end, end_dt))
                    
                    trends.append({
                        "date": current_day.isoformat(),
                        "produced": round(totals.get('generation_kwh', 0), 2),
                        "consumed": round(totals.get('consumption_kwh', 0), 2),
                        "sold": round(totals.get('export_kwh', 0), 2),
                        "bought": round(totals.get('import_kwh', 0), 2),
                        "carbon_offset": round(totals.get('carbon_offset_kg', 0), 2),
                        "efficiency": 100.0 if totals.get('consumption_kwh', 0) > 0 else 0.0,
                    })
                    
                    current_day = day_end
                    iteration += 1
                except Exception as e:
                    logger.error(f"Error processing day {current_day}: {e}", exc_info=True)
                    # Add empty data point and continue
                    trends.append({
                        "date": current_day.isoformat(),
                        "produced": 0.0,
                        "consumed": 0.0,
                        "sold": 0.0,
                        "bought": 0.0,
                        "carbon_offset": 0.0,
                        "efficiency": 0.0,
                    })
                    current_day += timedelta(days=1)
                    iteration += 1
        except Exception as e:
            logger.error(f"Error in _get_daily_trends: {e}", exc_info=True)
        
        return trends
    
    def _get_period_totals(self, start_dt: datetime, end_dt: datetime) -> Dict[str, float]:
        """Get aggregated totals for a time period."""
        totals = {
            'generation_kwh': 0.0,
            'consumption_kwh': 0.0,
            'export_kwh': 0.0,
            'import_kwh': 0.0,
            'carbon_offset_kg': 0.0,
        }
        
        # Sample at hourly intervals
        current_hour = start_dt.replace(minute=0, second=0, microsecond=0)
        
        # Limit to max hours to prevent hanging (max 48 hours = 2 days)
        max_hours = 48
        iteration = 0
        
        try:
            while current_hour < end_dt and iteration < max_hours:
                try:
                    # Use background service if available, otherwise direct simulation
                    if self._use_background and self.background_service:
                        result = self.background_service.get_community_data(current_hour)
                    else:
                        if self.simulation_engine is None:
                            self.simulation_engine = CommunitySimulationEngine(model_service=self.model_service)
                    result = self.simulation_engine.simulate_community(current_hour)
                    
                    if result:
                        interval_hours = 1.0
                        totals['generation_kwh'] += result.get('total_generation_kw', 0) * interval_hours
                        totals['consumption_kwh'] += result.get('total_consumption_kw', 0) * interval_hours
                        totals['export_kwh'] += result.get('total_grid_export_kw', 0) * interval_hours
                        totals['import_kwh'] += result.get('total_grid_import_kw', 0) * interval_hours
                        if model:
                            totals['carbon_offset_kg'] += result.get('total_generation_kw', 0) * model.community_control.carbon_offset_factor_kg_per_kwh * interval_hours
                except Exception as e:
                    logger.warning(f"Error simulating at {current_hour}: {e}")
                    # Continue with next hour
                
                current_hour += timedelta(hours=1)
                iteration += 1
        except Exception as e:
            logger.error(f"Error in _get_period_totals: {e}", exc_info=True)
        
        return totals
    
    def _default_community_data(self) -> Dict[str, Any]:
        """Return default data structure when no data is available."""
        return {
            "total_energy_flow": {
                "generation": {"live": 0.0, "history_24h": 0.0},
                "consumption": {"live": 0.0, "history_24h": 0.0},
                "net": 0.0,
                "source_breakdown": {"solar": 0.0, "fuel_cell": 0.0, "grid": 0.0}
            },
            "storage_network": {
                "total_capacity": 0.0,
                "aggregate_soc": 0.0,
                "available_energy": 0.0,
                "battery_power_kw": 0.0,
                "status": "idle",
                "members_with_storage": 0,
                "charging_count": 0,
                "discharging_count": 0,
                "idle_count": 0,
                "critical_alerts": []
            },
            "grid_interaction": {
                "stability_index": 0.0,
                "frequency_hz": 0.0,
                "voltage_v": 0.0,
                "import_rate": model.community_control.import_rate_usd_per_kwh,
                "export_rate": model.community_control.export_rate_usd_per_kwh,
                "renewable_pct": 0.0,
                "grid_load_pct": 0.0,
                "outage_zones": [],
                "outage_zones_count": 0,
            },
            "participation_summary": {
                "active_members": 0,
                "contribution_tiers": None,
                "demand_response_engagement": None,
            },
            "carbon_metrics": {
                "today_offset_kg": 0.0,
                "cumulative_offset_kg": 0.0,
                "vs_fossil_grid_reduction_pct": 0.0,
                "regional_rank": 0,
            },
            "marketplace_activity": {
                "volume_traded_kwh": 0.0,
                "volume_traded_currency": 0.0,
                "number_of_trades": 0,
                "price_fluctuation": 0.0,
                "top_traders": [],
                "price_range": {
                    "min": 0.0,
                    "max": 0.0,
                    "average": 0.0,
                    "current": 0.0
                }
            },
            "alerts_system_notices": [],
            "leaderboards": {
                "top_producers": [],
                "most_efficient": [],
                "carbon_offsetters": [],
            }
        }
    
    async def _get_marketplace_stats_from_api(self) -> Dict[str, Any]:
        """Get marketplace stats by directly querying MongoDB p2p_transactions collection.
        
        No service layer, no caching, just direct MongoDB query.
        """
        try:
            from app.db.database import get_database, Collections
            
            logger.info("[Community Dashboard] Starting MongoDB query for marketplace stats...")
            
            # Direct MongoDB query - no service layer
            db = await get_database()
            collection = db[Collections.P2P_TRANSACTIONS]
            
            logger.info(f"[Community Dashboard] Collection name: {Collections.P2P_TRANSACTIONS}")
            
            # Get ALL transactions from MongoDB
            cursor = collection.find({})
            all_trades = []
            async for doc in cursor:
                all_trades.append(doc)
                # Debug: log first transaction structure
                if len(all_trades) == 1:
                    logger.info(f"[Community Dashboard] First transaction sample keys: {list(doc.keys())}")
                    logger.info(f"[Community Dashboard] First transaction status: {doc.get('status')}")
                    logger.info(f"[Community Dashboard] First transaction energy_kwh: {doc.get('energy_kwh')}")
                    logger.info(f"[Community Dashboard] First transaction gross_amount: {doc.get('gross_amount')}")
            
            logger.info(f"[Community Dashboard] Direct MongoDB query: Found {len(all_trades)} total transactions")
            
            # Filter executed trades only
            executed_trades = [t for t in all_trades if t.get("status") == "executed"]
            
            logger.info(f"[Community Dashboard] Executed trades: {len(executed_trades)}")
            
            # Debug: log all statuses found
            if all_trades:
                statuses = [t.get("status") for t in all_trades]
                logger.info(f"[Community Dashboard] All statuses found: {set(statuses)}")
            
            # Debug: log first executed trade details
            if executed_trades:
                first_trade = executed_trades[0]
                logger.info(
                    f"[Community Dashboard] First executed trade: "
                    f"energy_kwh={first_trade.get('energy_kwh')} (type: {type(first_trade.get('energy_kwh'))}), "
                    f"gross_amount={first_trade.get('gross_amount')} (type: {type(first_trade.get('gross_amount'))}), "
                    f"price_per_kwh={first_trade.get('price_per_kwh')} (type: {type(first_trade.get('price_per_kwh'))}), "
                    f"status={first_trade.get('status')}"
                )
            else:
                logger.warning("[Community Dashboard] No executed trades found! All trades:")
                for i, trade in enumerate(all_trades[:5]):  # Log first 5
                    logger.warning(f"[Community Dashboard] Trade {i}: status={trade.get('status')}, energy_kwh={trade.get('energy_kwh')}")
            
            # Calculate statistics
            total_energy_traded = sum(float(t.get("energy_kwh", 0)) for t in executed_trades)
            total_value = sum(float(t.get("gross_amount", 0)) for t in executed_trades)
            
            logger.info(
                f"[Community Dashboard] Stats: {len(executed_trades)} trades, "
                f"{total_energy_traded:.2f} kWh, ${total_value:.2f}"
            )
            
            # Calculate price range from executed trades
            prices = [float(t.get("price_per_kwh", 0)) for t in executed_trades if float(t.get("price_per_kwh", 0)) > 0]
            min_price = min(prices) if prices else 0.0
            max_price = max(prices) if prices else 0.0
            avg_price = sum(prices) / len(prices) if prices else 0.0
            
            # Calculate price fluctuation
            if prices and len(prices) > 1:
                import statistics
                price_std = statistics.stdev(prices) if len(prices) > 1 else 0.0
                price_fluctuation = (price_std / avg_price * 100) if avg_price > 0 else 0.0
            else:
                price_fluctuation = 0.0
            
            # Calculate top traders
            trader_volumes: Dict[str, float] = {}
            trader_names: Dict[str, str] = {}
            
            model = self.model_service.get_model()
            if model:
                for member in model.members:
                    trader_names[member.member_id] = member.name
            
            for trade in executed_trades:
                seller_id = trade.get("seller_id")
                buyer_id = trade.get("buyer_id")
                energy = float(trade.get("energy_kwh", 0))
                
                if seller_id:
                    trader_volumes[seller_id] = trader_volumes.get(seller_id, 0) + energy
                if buyer_id:
                    trader_volumes[buyer_id] = trader_volumes.get(buyer_id, 0) + energy
            
            sorted_traders = sorted(trader_volumes.items(), key=lambda x: x[1], reverse=True)
            top_traders = [
                {
                    "name": trader_names.get(trader_id, trader_id),
                    "volume": round(volume, 2),
                    "rank": idx + 1
                }
                for idx, (trader_id, volume) in enumerate(sorted_traders[:5])
            ]
            
            result = {
                "volume_traded_kwh": round(total_energy_traded, 2),
                "volume_traded_currency": round(total_value, 2),
                "number_of_trades": len(executed_trades),
                "price_fluctuation": round(price_fluctuation, 2),
                "top_traders": top_traders,
                "price_range": {
                    "min": round(min_price, 3),
                    "max": round(max_price, 3),
                    "average": round(avg_price, 3),
                    "current": round(avg_price, 3)
                }
            }
    
    async def _get_p2p_transaction_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get P2P transaction history from MongoDB.
        
        Args:
            limit: Maximum number of transactions to return (default: 50)
            
        Returns:
            List of transaction dictionaries sorted by most recent first
        """
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.P2P_TRANSACTIONS]
            
            # Get member names for display
            model = self.model_service.get_model()
            member_names = {}
            if model:
                for member in model.members:
                    member_names[member.member_id] = member.name
            
            # Query MongoDB for executed transactions, sorted by most recent first
            cursor = collection.find(
                {"status": "executed"}
            ).sort("executed_at", -1).limit(limit)
            
            transactions = []
            async for doc in cursor:
                # Convert MongoDB document to API format
                transaction = {
                    "transaction_id": doc.get("transaction_id", ""),
                    "seller_id": doc.get("seller_id", ""),
                    "seller_name": member_names.get(doc.get("seller_id", ""), doc.get("seller_id", "")),
                    "buyer_id": doc.get("buyer_id", ""),
                    "buyer_name": member_names.get(doc.get("buyer_id", ""), doc.get("buyer_id", "")),
                    "energy_kwh": float(doc.get("energy_kwh", 0)),
                    "price_per_kwh": float(doc.get("price_per_kwh", 0)),
                    "gross_amount": float(doc.get("gross_amount", 0)),
                    "service_fee": float(doc.get("service_fee", 0)),
                    "seller_amount": float(doc.get("seller_amount", 0)),
                    "buyer_amount": float(doc.get("buyer_amount", 0)),
                    "time_block": doc.get("time_block").isoformat() if doc.get("time_block") else None,
                    "executed_at": doc.get("executed_at").isoformat() if doc.get("executed_at") else None,
                    "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                    "transaction_hash": doc.get("transaction_hash", ""),
                    "status": doc.get("status", "executed")
                }
                transactions.append(transaction)
            
            logger.info(f"[Community Dashboard] Retrieved {len(transactions)} P2P transactions from MongoDB")
            
            return transactions
            
        except Exception as e:
            logger.error(f"[Community Dashboard] Error getting P2P transaction history: {e}", exc_info=True)
            return []
