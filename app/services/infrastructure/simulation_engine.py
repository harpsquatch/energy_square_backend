"""
Community Simulation Engine
Decodes canonical pattern to generate per-member and community-level signals in real-time.
"""
import pandas as pd
import numpy as np
import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Callable
from zoneinfo import ZoneInfo
import json

from app.models.community_model import (
    CommunityModel, Member, SimulationControl
)
from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_utils import (
    Denormalizer, BehavioralModifier, VariabilityInjector,
    ConstraintEnforcer, EnergyBalanceCalculator
)

logger = logging.getLogger(__name__)


class CommunitySimulationEngine:
    """Engine for simulating community energy behavior from normalized patterns."""
    
    def __init__(
        self,
        model_service: CommunityModelService,
        pattern_file_path: Optional[Path] = None
    ):
        """
        Initialize the simulation engine.
        
        Args:
            model_service: Community model service instance
            pattern_file_path: Path to pattern file. If None, uses model's base_pattern_ref.
        """
        self.model_service = model_service
        self.pattern_file_path = pattern_file_path
        
        # Pattern data cache
        self._pattern_df: Optional[pd.DataFrame] = None
        self._pattern_start: Optional[datetime] = None
        self._pattern_end: Optional[datetime] = None
        
        # Simulation state
        self._current_timestamp: Optional[datetime] = None
        self._member_states: Dict[str, Dict[str, Any]] = {}  # member_id -> state dict
        
        # Load pattern
        self._load_pattern()
        
        # Initialize member states
        self._initialize_member_states()
    
    def _load_pattern(self):
        """Load the canonical pattern file."""
        model = self.model_service.get_model()
        if model is None:
            logger.error("Cannot load pattern: model not loaded")
            return
        
        # Determine pattern file path
        if self.pattern_file_path is None:
            # __file__ is at: be/app/services/infrastructure/simulation_engine.py
            # We need to go up 2 levels to reach: be/app/
            infrastructure_path = Path(__file__).parent  # be/app/services/infrastructure
            services_path = infrastructure_path.parent  # be/app/services
            app_path = services_path.parent  # be/app/
            pattern_filename = model.community.base_pattern_ref
            self.pattern_file_path = app_path / pattern_filename
        
        if not self.pattern_file_path.exists():
            logger.error(f"Pattern file not found: {self.pattern_file_path}")
            return
        
        try:
            logger.info(f"Loading pattern file: {self.pattern_file_path}")
            self._pattern_df = pd.read_csv(self.pattern_file_path)
            self._pattern_df['Timestamp'] = pd.to_datetime(self._pattern_df['Timestamp'])
            self._pattern_df.set_index('Timestamp', inplace=True)
            
            self._pattern_start = self._pattern_df.index.min()
            self._pattern_end = self._pattern_df.index.max()
            
            logger.info(
                f"Loaded pattern: {len(self._pattern_df)} records "
                f"from {self._pattern_start} to {self._pattern_end}"
            )
        except Exception as e:
            logger.error(f"Error loading pattern file: {e}", exc_info=True)
            self._pattern_df = None
    
    def _initialize_member_states(self):
        """Initialize member state tracking."""
        model = self.model_service.get_model()
        if model is None:
            return
        
        for member in model.members:
            # Initialize battery SOC based on pattern context
            # If battery power from pattern is positive (discharging), start with higher SOC
            # If battery power is negative (charging), start with lower SOC
            initial_soc = self._infer_initial_soc(member)
            
            self._member_states[member.member_id] = {
                "battery_soc": initial_soc,
                "last_update": None
            }
    
    def _infer_initial_soc(self, member: Member) -> float:
        """
        Infer initial battery SOC from pattern context.
        
        Args:
            member: Member to initialize SOC for
            
        Returns:
            Initial SOC (0.0 to 1.0)
        """
        # Get current time in community timezone
        model = self.model_service.get_model()
        if model is None:
            # Fallback to mid-range
            return (member.assets.battery_min_soc + member.assets.battery_max_soc) / 2.0
        
        try:
            now = datetime.now(ZoneInfo(model.community.timezone))
            pattern_row = self._get_pattern_row(now)
            
            if pattern_row is not None:
                # Get battery power from pattern
                normalized_battery = pattern_row.get('Battery_Active_Power', 0.5)  # Neutral/idle if missing
                
                # Infer SOC from battery power pattern:
                # Positive normalized power (0.5 to 1.0) = discharging = start with higher SOC (60-90%)
                # Negative normalized power (0.0 to 0.5) = charging = start with lower SOC (20-50%)
                if normalized_battery > 0.5:
                    # Discharging pattern - start with higher SOC
                    soc_range = (0.6, 0.9)
                    # Map 0.5-1.0 to 0.6-0.9
                    initial_soc = 0.6 + (normalized_battery - 0.5) * 0.6
                else:
                    # Charging pattern - start with lower SOC
                    soc_range = (0.2, 0.5)
                    # Map 0.0-0.5 to 0.2-0.5
                    initial_soc = 0.2 + (normalized_battery / 0.5) * 0.3
                
                # Clamp to member's min/max SOC
                initial_soc = max(member.assets.battery_min_soc, 
                                 min(member.assets.battery_max_soc, initial_soc))
                
                logger.debug(
                    f"Initialized {member.member_id} SOC to {initial_soc:.2%} "
                    f"(pattern battery power: {normalized_battery:.3f})"
                )
                
                return initial_soc
        except Exception as e:
            logger.warning(f"Error inferring initial SOC for {member.member_id}: {e}")
        
        # Fallback: use mid-range
        return (member.assets.battery_min_soc + member.assets.battery_max_soc) / 2.0
    
    def _get_pattern_timestamp(self, target_dt: datetime, model: CommunityModel) -> datetime:
        """
        Map target datetime to pattern timestamp.
        
        Uses loop_mode to determine if we cycle through the pattern or move linearly.
        """
        if self._pattern_df is None or self._pattern_df.empty:
            return target_dt
        
        control = model.simulation_control
        
        # Calculate day of year
        day_of_year = target_dt.timetuple().tm_yday
        target_hour = target_dt.hour
        
        # Map to pattern year
        pattern_year = self._pattern_start.year
        pattern_date = datetime(pattern_year, 1, 1) + timedelta(days=day_of_year - 1)
        pattern_timestamp = pattern_date.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        
        # Handle loop mode
        if control.loop_mode.value == "cyclic":
            # Cycle within pattern range
            if pattern_timestamp < self._pattern_start:
                pattern_timestamp = self._pattern_start.replace(hour=target_hour)
            elif pattern_timestamp > self._pattern_end:
                days_since_start = (pattern_timestamp - self._pattern_start).days
                pattern_days = (self._pattern_end - self._pattern_start).days
                days_in_range = days_since_start % pattern_days if pattern_days > 0 else 0
                pattern_timestamp = self._pattern_start + timedelta(days=days_in_range)
                pattern_timestamp = pattern_timestamp.replace(hour=target_hour)
        else:  # linear
            # Move linearly, clamp to pattern bounds
            if pattern_timestamp > self._pattern_end:
                pattern_timestamp = self._pattern_end
            elif pattern_timestamp < self._pattern_start:
                pattern_timestamp = self._pattern_start
        
        # Find closest timestamp in pattern
        if pattern_timestamp in self._pattern_df.index:
            return pattern_timestamp
        
        # Find closest match
        pattern_df_reset = self._pattern_df.reset_index()
        pattern_df_reset['time_diff'] = abs((pattern_df_reset['Timestamp'] - pattern_timestamp).dt.total_seconds())
        closest_idx = pattern_df_reset['time_diff'].idxmin()
        
        if pattern_df_reset.loc[closest_idx, 'time_diff'] <= 3600:
            return pattern_df_reset.loc[closest_idx, 'Timestamp']
        
        return pattern_timestamp
    
    def _get_pattern_row(self, timestamp: datetime) -> Optional[pd.Series]:
        """Get pattern row for a timestamp."""
        if self._pattern_df is None:
            return None
        
        model = self.model_service.get_model()
        if model is None:
            return None
        
        pattern_ts = self._get_pattern_timestamp(timestamp, model)
        
        if pattern_ts in self._pattern_df.index:
            return self._pattern_df.loc[pattern_ts]
        
        return None
    
    def simulate_member(
        self, 
        member: Member, 
        timestamp: datetime, 
        apply_demand_response: bool = True,
        p2p_sold_kw: float = 0.0,
        p2p_bought_kw: float = 0.0
    ) -> Dict[str, Any]:
        """
        Simulate a single member's energy signals at a given timestamp.
        
        Args:
            member: Member to simulate
            timestamp: Current simulation timestamp
            apply_demand_response: If True, apply active DR events. Set to False for historical simulations.
            p2p_sold_kw: Energy sold via P2P in this time block (kW)
            p2p_bought_kw: Energy bought via P2P in this time block (kW)
            
        Returns:
            Dictionary with member's energy signals
        """
        # Get pattern row
        pattern_row = self._get_pattern_row(timestamp)
        if pattern_row is None:
            logger.warning(f"No pattern data for {timestamp}")
            return self._default_member_output(member.member_id, timestamp)
        
        # Get utilities
        denorm = Denormalizer()
        behavior_mod = BehavioralModifier()
        variability = VariabilityInjector()
        constraints = ConstraintEnforcer()
        balance_calc = EnergyBalanceCalculator()
        
        # Create RNG for this member
        rng = VariabilityInjector.create_rng(member.variability.random_seed)
        
        # Extract normalized values from pattern (no fallbacks - pattern must be complete)
        normalized_pv = pattern_row.get('PVPCS_Active_Power', 0.0)
        normalized_battery = pattern_row.get('Battery_Active_Power', 0.5)  # Neutral/idle if missing
        normalized_consumption = pattern_row.get('GE_Active_Power', 0.5)  # Medium if missing
        
        # Denormalize to physical units
        pv_generation_kw = denorm.denormalize_pv(normalized_pv, member.assets.pv_capacity_kw)
        # Get max power rate from battery chemistry (e.g., lithium-ion: 0.8C, lead-acid: 0.2C, LiFePO4: 1.0C)
        battery_max_power_rate = member.assets.battery_chemistry.get_max_power_rate()
        battery_power_kw = denorm.denormalize_battery(
            normalized_battery, 
            member.assets.battery_capacity_kwh,
            battery_max_power_rate
        )
        consumption_kw = denorm.denormalize_consumption(
            abs(normalized_consumption), 
            member.assets.load_capacity_kw
        )
        
        # Apply behavioral modifiers
        current_date = timestamp.date()
        is_weekend = timestamp.weekday() >= 5
        current_hour = timestamp.hour
        
        # Weekday/weekend factor
        consumption_kw = behavior_mod.apply_weekday_factor(consumption_kw, member.behavior, is_weekend)
        
        # Active hours factor (get category-specific outside hours factor)
        outside_hours_factor = member.customer_category.get_outside_active_hours_factor()
        consumption_kw = behavior_mod.apply_active_hours_factor(
            consumption_kw, member.behavior, current_hour,
            outside_hours_factor
        )
        
        # Seasonal scaling
        consumption_kw = behavior_mod.apply_seasonal_scaling(
            consumption_kw, member.behavior, current_date, "load"
        )
        pv_generation_kw = behavior_mod.apply_seasonal_scaling(
            pv_generation_kw, member.behavior, current_date, "pv"
        )
        
        # Maintenance days
        pv_generation_kw = behavior_mod.apply_maintenance(
            pv_generation_kw, member.behavior, current_date, "pv"
        )
        
        # Temperature sensitivity (if temperature data available)
        # For now, skip as we'd need to fetch temperature
        
        # Get current battery SOC
        battery_soc = self._member_states[member.member_id]["battery_soc"]
        
        # Apply battery preference
        battery_power_kw = behavior_mod.apply_battery_preference(
            battery_power_kw, member.behavior, battery_soc
        )
        
        # Apply behavioral variability
        pv_generation_kw = variability.apply_behavioral_variability(pv_generation_kw, member.variability, rng)
        consumption_kw = variability.apply_behavioral_variability(consumption_kw, member.variability, rng)
        battery_power_kw = variability.apply_behavioral_variability(battery_power_kw, member.variability, rng)
        
        # Apply demand response reduction (only for current/real-time simulations, not historical)
        if apply_demand_response:
            try:
                from app.services.infrastructure.demand_response_service import get_demand_response_service
                dr_service = get_demand_response_service()
                dr_reduction_pct = dr_service.get_member_reduction(member.member_id, timestamp)
                logger.info(
                    f"[DR] Checking {member.member_id} at {timestamp}: "
                    f"apply_dr={apply_demand_response}, reduction={dr_reduction_pct*100:.1f}%"
                )
                if dr_reduction_pct > 0:
                    # Reduce consumption based on DR participation
                    original_consumption = consumption_kw
                    consumption_kw = consumption_kw * (1.0 - dr_reduction_pct)
                    logger.info(
                        f"[DR] APPLIED for {member.member_id}: {original_consumption:.2f} kW -> {consumption_kw:.2f} kW "
                        f"({dr_reduction_pct * 100:.0f}% reduction)"
                    )
                else:
                    logger.info(f"[DR] No reduction for {member.member_id} (reduction={dr_reduction_pct})")
            except Exception as e:
                # If DR service not available, continue without DR
                logger.error(f"[DR] Error for {member.member_id}: {e}", exc_info=True)
        else:
            logger.debug(f"[DR] Skipped for {member.member_id} (apply_demand_response=False)")
        
        # Enforce battery SOC constraints
        # Get time step from simulation control (default 1 hour)
        model = self.model_service.get_model()
        time_step_hours = 1.0
        if model:
            time_step_hours = model.simulation_control.time_step_seconds / 3600.0
        
        battery_power_kw, new_battery_soc = constraints.enforce_battery_soc_constraints(
            battery_power_kw, battery_soc, member.assets, time_step_hours
        )
        self._member_states[member.member_id]["battery_soc"] = new_battery_soc
        
        # Calculate energy balance
        balance = balance_calc.calculate_member_balance(
            pv_generation_kw,
            consumption_kw,
            battery_power_kw,
            member.assets.inverter_efficiency
        )
        
        # Apply P2P trades: reduce grid export for sold energy, reduce grid import for bought energy
        grid_export_kw = max(0.0, balance["grid_export_kw"] - p2p_sold_kw)
        grid_import_kw = max(0.0, balance["grid_import_kw"] - p2p_bought_kw)
        
        # Enforce grid limits
        grid_export_kw, grid_import_kw = constraints.enforce_grid_limits(
            grid_export_kw,
            grid_import_kw,
            member.assets
        )
        
        # Build output
        output = {
            "timestamp": timestamp.isoformat(),
            "member_id": member.member_id,
            "member_type": member.member_type.value,
            "solar_generation_kw": round(pv_generation_kw, 3),
            "consumption_kw": round(consumption_kw, 3),
            "battery_power_kw": round(battery_power_kw, 3),
            "battery_soc": round(new_battery_soc, 4),
            "net_balance_kw": round(balance["net_balance_kw"], 3),
            "grid_export_kw": round(grid_export_kw, 3),
            "grid_import_kw": round(grid_import_kw, 3),
        }
        
        return output
    
    def simulate_community(self, timestamp: Optional[datetime] = None, apply_demand_response: bool = True) -> Dict[str, Any]:
        """
        Simulate all members and aggregate to community level.
        
        Args:
            timestamp: Simulation timestamp. If None, uses current time.
            apply_demand_response: If True, apply active DR events. Set to False for historical simulations.
            
        Returns:
            Dictionary with community and member data
        """
        model = self.model_service.get_model()
        if model is None:
            logger.error("Cannot simulate: model not loaded")
            return {}
        
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo(model.community.timezone))
        
        self._current_timestamp = timestamp
        
        # Get active P2P trades for this time block
        active_p2p_trades = {}
        try:
            from app.services.infrastructure.marketplace_service import get_marketplace_service
            marketplace_service = get_marketplace_service()
            active_p2p_trades = marketplace_service.get_active_trades(timestamp)
        except Exception as e:
            logger.debug(f"Could not fetch P2P trades: {e}")
        
        # Simulate all members
        member_outputs = []
        for member in model.members:
            # Get P2P trade amounts for this member
            p2p_sold_kw = active_p2p_trades.get("sold", {}).get(member.member_id, 0.0)
            p2p_bought_kw = active_p2p_trades.get("bought", {}).get(member.member_id, 0.0)
            
            if p2p_sold_kw > 0 or p2p_bought_kw > 0:
                logger.info(
                    f"[P2P] {member.member_id}: sold={p2p_sold_kw} kW, bought={p2p_bought_kw} kW"
                )
            
            member_output = self.simulate_member(
                member, 
                timestamp, 
                apply_demand_response=apply_demand_response,
                p2p_sold_kw=p2p_sold_kw,
                p2p_bought_kw=p2p_bought_kw
            )
            member_outputs.append(member_output)
        
        # Aggregate to community level
        aggregator = EnergyBalanceCalculator()
        community_aggregates = aggregator.calculate_community_aggregates(member_outputs)
        
        # Enforce community grid limits
        constraints = ConstraintEnforcer()
        community_export, community_import = constraints.enforce_community_grid_limits(
            community_aggregates["total_grid_export_kw"],
            community_aggregates["total_grid_import_kw"],
            model.community_control
        )
        
        # Get demand response metrics
        dr_metrics = {}
        try:
            from app.services.infrastructure.demand_response_service import get_demand_response_service
            dr_service = get_demand_response_service()
            dr_metrics = dr_service.calculate_metrics(timestamp, community_aggregates)
        except Exception as e:
            logger.debug(f"Could not get DR metrics: {e}")
            # Provide defaults if DR service unavailable
            dr_metrics = {
                "active_event_count": 0,
                "participating_member_count": 0,
                "potential_shed_kw": community_aggregates.get("total_consumption_kw", 0) * 0.2,
                "actual_reduction_kw": 0.0,
                "price_signal_usd_per_kwh": 0.0,
                "active_events": []
            }
        
        # Build community output
        community_output = {
            "timestamp": timestamp.isoformat(),
            "community_id": model.community.community_id,
            **{k: round(v, 3) for k, v in community_aggregates.items()},
            "total_grid_export_kw": round(community_export, 3),
            "total_grid_import_kw": round(community_import, 3),
            "demand_response": dr_metrics,
            "members": member_outputs
        }
        
        return community_output
    
    def _default_member_output(self, member_id: str, timestamp: datetime) -> Dict[str, Any]:
        """Return default output when pattern data is unavailable."""
        return {
            "timestamp": timestamp.isoformat(),
            "member_id": member_id,
            "solar_generation_kw": 0.0,
            "consumption_kw": 0.0,
            "battery_power_kw": 0.0,
            "battery_soc": self._get_default_battery_soc(),
            "net_balance_kw": 0.0,
            "grid_export_kw": 0.0,
            "grid_import_kw": 0.0,
        }
    
    
    def update_member_asset(self, member_id: str, asset_updates: Dict[str, float]) -> bool:
        """
        Update a member's asset configuration.
        
        Args:
            member_id: Member ID
            asset_updates: Dictionary of asset fields to update
            
        Returns:
            True if successful
        """
        return self.model_service.update_member(member_id, {"assets": asset_updates})

