"""
Community Simulation Utilities
Functions for denormalization, behavioral modifiers, variability injection, and signal processing.
"""
import numpy as np
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from zoneinfo import ZoneInfo

from app.models.community_model import (
    Member, MemberAssets, MemberBehavior, BehavioralVariability,
    SeasonalScalingFactors, CommunityControl
)

logger = logging.getLogger(__name__)


class Denormalizer:
    """Denormalizes pattern values to physical units based on member assets."""
    
    @staticmethod
    def denormalize_pv(normalized_value: float, pv_capacity_kw: float) -> float:
        """
        Denormalize PV generation from [0, 1] to kW.
        
        Args:
            normalized_value: Value in [0, 1] range
            pv_capacity_kw: Maximum PV capacity in kW
            
        Returns:
            PV generation in kW
        """
        return float(np.clip(normalized_value * pv_capacity_kw, 0.0, pv_capacity_kw))
    
    @staticmethod
    def denormalize_battery(normalized_value: float, battery_capacity_kwh: float, battery_max_power_rate: float = 0.8) -> float:
        """
        Denormalize battery power from [0, 1] to kW.
        Note: normalized value 0.5 = neutral (no charge/discharge).
        
        Args:
            normalized_value: Value in [0, 1] range (0.5 = neutral)
            battery_capacity_kwh: Battery capacity in kWh
            
        Returns:
            Battery power in kW (positive = discharge, negative = charge)
        """
        # Normalized 0.5 maps to 0 kW, 0 maps to max charge, 1 maps to max discharge
        max_power_kw = battery_capacity_kwh * battery_max_power_rate
        normalized_offset = normalized_value - 0.5  # Center at 0
        return float(np.clip(normalized_offset * 2.0 * max_power_kw, -max_power_kw, max_power_kw))
    
    @staticmethod
    def denormalize_consumption(normalized_value: float, load_capacity_kw: float) -> float:
        """
        Denormalize consumption from [0, 1] to kW.
        
        Args:
            normalized_value: Value in [0, 1] range
            load_capacity_kw: Maximum load capacity in kW
            
        Returns:
            Consumption in kW
        """
        return float(np.clip(normalized_value * load_capacity_kw, 0.0, load_capacity_kw))
    
    @staticmethod
    def denormalize_voltage(normalized_value: float, min_voltage: float = 400.0, max_voltage: float = 600.0) -> float:
        """Denormalize voltage from [0, 1] to Volts."""
        return float(min_voltage + normalized_value * (max_voltage - min_voltage))
    
    @staticmethod
    def denormalize_frequency(normalized_value: float, min_frequency: float = 55.0, max_frequency: float = 65.0) -> float:
        """Denormalize frequency from [0, 1] to Hertz."""
        return float(min_frequency + normalized_value * (max_frequency - min_frequency))


class BehavioralModifier:
    """Applies behavioral modifiers to member signals."""
    
    @staticmethod
    def apply_weekday_factor(value: float, behavior: MemberBehavior, is_weekend: bool) -> float:
        """Apply weekday/weekend factor."""
        factor = behavior.weekend_factor if is_weekend else behavior.weekday_factor
        return value * factor
    
    @staticmethod
    def apply_active_hours_factor(
        value: float, 
        behavior: MemberBehavior, 
        current_hour: int,
        outside_active_hours_factor: float = 0.25  # Default for safety
    ) -> float:
        """Apply active hours modifier."""
        if not behavior.active_hours or len(behavior.active_hours) != 2:
            return value
        
        start_hour, end_hour = behavior.active_hours
        
        # Check if current hour is within active hours
        if start_hour <= current_hour < end_hour:
            return value  # Full activity
        else:
            return value * outside_active_hours_factor
    
    @staticmethod
    def apply_temperature_sensitivity(
        value: float,
        behavior: MemberBehavior,
        temperature: Optional[float],
        base_temperature: Optional[float] = None,
        temperature_normalization_divisor: float = 10.0
    ) -> float:
        """Apply temperature sensitivity modifier."""
        if temperature is None or behavior.temperature_sensitivity == 0.0:
            return value
        
        if base_temperature is None:
            base_temperature = 20.0  # Default, but should come from model
        
        # Temperature deviation from baseline
        temp_deviation = (temperature - base_temperature) / temperature_normalization_divisor
        
        # Apply sensitivity (positive = consumption increases with temp)
        modifier = 1.0 + behavior.temperature_sensitivity * temp_deviation
        
        return value * modifier
    
    @staticmethod
    def apply_seasonal_scaling(
        value: float,
        behavior: MemberBehavior,
        current_date: date,
        value_type: str = "load"  # "load" or "pv"
    ) -> float:
        """Apply seasonal scaling factors."""
        if behavior.seasonal_scaling_factors is None:
            return value
        
        month = current_date.month
        factors = behavior.seasonal_scaling_factors.get_month_factor(month)
        
        factor = factors.load if value_type == "load" else factors.pv
        return value * factor
    
    @staticmethod
    def apply_maintenance(
        value: float,
        behavior: MemberBehavior,
        current_date: date,
        value_type: str = "pv"  # "pv" for generation, "load" for consumption
    ) -> float:
        """Apply maintenance day modifier (zero generation on maintenance days)."""
        date_str = current_date.strftime("%Y-%m-%d")
        
        if date_str in behavior.maintenance_days:
            if value_type == "pv":
                return 0.0  # No generation during maintenance
            # Consumption continues during maintenance
        
        return value
    
    @staticmethod
    def apply_routine_drift(
        value: float,
        behavior: MemberBehavior,
        base_hour: int,
        current_hour: int,
        routine_drift_hour_normalizer: float = 3.0,
        transition_factor_min: float = 0.8,
        transition_factor_max: float = 1.0
    ) -> float:
        """
        Apply routine drift (timing offset) to value.
        
        NOTE: This function is currently NOT CALLED in the simulation.
        It's kept for future implementation of behavioral timing variability.
        When implementing, pass these parameters from the model or make them member-specific.
        """
        if behavior.routine_drift_hours == 0.0:
            return value
        
        # Calculate hour offset with drift
        hour_diff = current_hour - base_hour
        drift_offset = np.random.normal(0, behavior.routine_drift_hours)
        adjusted_hour = base_hour + drift_offset
        
        # Soft transition effect
        transition_factor = 1.0 - abs(hour_diff - drift_offset) / routine_drift_hour_normalizer
        transition_factor = np.clip(transition_factor, transition_factor_min, transition_factor_max)
        
        return value * transition_factor
    
    @staticmethod
    def apply_pv_self_consumption(
        pv_generation: float,
        consumption: float,
        behavior: MemberBehavior
    ) -> tuple:
        """
        Apply PV self-consumption preference.
        
        Returns:
            (self_consumed_pv, exported_pv)
        """
        if pv_generation == 0 or consumption == 0:
            return (0.0, pv_generation)
        
        # Self-consumption preference determines split
        max_self_consume = min(pv_generation, consumption)
        self_consume = max_self_consume * behavior.pv_self_consumption_preference
        
        exported = pv_generation - self_consume
        
        return (float(self_consume), float(exported))
    
    @staticmethod
    def apply_battery_preference(
        battery_power: float,
        behavior: MemberBehavior,
        battery_soc: float
    ) -> float:
        """Apply battery usage preference based on SOC."""
        if behavior.battery_usage_preference == 0.0:
            return 0.0
        
        # Prefer to use battery when SOC is high, charge when low
        if battery_soc > 0.7 and battery_power > 0:  # High SOC, discharging
            preference_factor = behavior.battery_usage_preference
        elif battery_soc < 0.3 and battery_power < 0:  # Low SOC, charging
            preference_factor = behavior.battery_usage_preference
        else:
            preference_factor = 1.0 - behavior.battery_usage_preference
        
        return battery_power * preference_factor


class VariabilityInjector:
    """Injects stochastic variability into signals for realism."""
    
    @staticmethod
    def apply_behavioral_variability(
        value: float,
        variability_config: BehavioralVariability,
        rng: Optional[np.random.Generator] = None
    ) -> float:
        """
        Apply behavioral variability to a value.
        
        Args:
            value: Base value
            variability_config: Behavioral variability configuration
            rng: Random number generator (for reproducibility)
            
        Returns:
            Value with variability applied
        """
        if variability_config.variability_level == 0.0:
            return value
        
        if rng is None:
            rng = np.random.default_rng(variability_config.random_seed)
        
        # Generate variability (normal distribution, scaled by variability level)
        variability_factor = rng.normal(0, variability_config.variability_level)
        
        # Apply variability multiplicatively (preserves sign for battery)
        if value < 0:  # Battery charging
            return value * (1.0 + variability_factor)
        else:  # Generation or consumption
            return value * (1.0 + abs(variability_factor))
    
    @staticmethod
    def create_rng(seed: int) -> np.random.Generator:
        """Create a reproducible random number generator."""
        return np.random.default_rng(seed)


class ConstraintEnforcer:
    """Enforces physical and operational constraints."""
    
    @staticmethod
    def enforce_battery_soc_constraints(
        battery_power_kw: float,
        battery_soc: float,
        assets: MemberAssets,
        time_step_hours: float = 1.0
    ) -> tuple[float, float]:
        """
        Enforce battery SOC constraints.
        
        Returns:
            (constrained_battery_power_kw, new_battery_soc)
        """
        if assets.battery_capacity_kwh == 0:
            return (0.0, 0.0)
        
        # Calculate new SOC based on power
        energy_change_kwh = -battery_power_kw * time_step_hours  # Negative = charging
        new_soc = battery_soc + (energy_change_kwh / assets.battery_capacity_kwh)
        
        # Enforce limits
        if new_soc < assets.battery_min_soc:
            # Limit to minimum SOC
            max_discharge_energy = (battery_soc - assets.battery_min_soc) * assets.battery_capacity_kwh
            max_discharge_power = max_discharge_energy / time_step_hours
            battery_power_kw = min(battery_power_kw, max_discharge_power)
            new_soc = assets.battery_min_soc
        elif new_soc > assets.battery_max_soc:
            # Limit to maximum SOC
            max_charge_energy = (assets.battery_max_soc - battery_soc) * assets.battery_capacity_kwh
            max_charge_power = max_charge_energy / time_step_hours
            battery_power_kw = max(battery_power_kw, -max_charge_power)
            new_soc = assets.battery_max_soc
        
        return (float(battery_power_kw), float(new_soc))
    
    @staticmethod
    def enforce_grid_limits(
        grid_export_kw: float,
        grid_import_kw: float,
        assets: MemberAssets
    ) -> tuple[float, float]:
        """Enforce grid import/export limits."""
        grid_import_kw = min(grid_import_kw, assets.grid_import_limit_kw)
        grid_export_kw = min(grid_export_kw, assets.grid_export_limit_kw)
        
        return (float(grid_export_kw), float(grid_import_kw))
    
    @staticmethod
    def enforce_community_grid_limits(
        community_export_kw: float,
        community_import_kw: float,
        community_control: CommunityControl
    ) -> tuple[float, float]:
        """Enforce community-level grid limits."""
        community_import_kw = min(community_import_kw, community_control.grid_import_limit_kw)
        community_export_kw = min(community_export_kw, community_control.grid_export_limit_kw)
        
        return (float(community_export_kw), float(community_import_kw))


class EnergyBalanceCalculator:
    """Calculates energy balance for members and community."""
    
    @staticmethod
    def calculate_member_balance(
        pv_generation_kw: float,
        consumption_kw: float,
        battery_power_kw: float,
        inverter_efficiency: float = 1.0
    ) -> Dict[str, float]:
        """
        Calculate energy balance for a member.
        
        Returns:
            Dictionary with net_balance_kw, grid_import_kw, grid_export_kw
        """
        # Net generation (PV after inverter losses)
        net_generation_kw = pv_generation_kw * inverter_efficiency
        
        # Net balance (positive = surplus, negative = deficit)
        net_balance_kw = net_generation_kw - consumption_kw + battery_power_kw
        
        # Grid interaction
        grid_export_kw = max(0.0, net_balance_kw)
        grid_import_kw = max(0.0, -net_balance_kw)
        
        return {
            "net_balance_kw": float(net_balance_kw),
            "grid_export_kw": float(grid_export_kw),
            "grid_import_kw": float(grid_import_kw)
        }
    
    @staticmethod
    def calculate_community_aggregates(
        member_balances: List[Dict[str, float]]
    ) -> Dict[str, float]:
        """Aggregate member balances to community totals including storage metrics."""
        # Use solar_generation_kw (member output key) or pv_generation_kw (backward compat)
        total_generation = sum(
            b.get("solar_generation_kw", b.get("pv_generation_kw", 0)) 
            for b in member_balances
        )
        total_consumption = sum(b.get("consumption_kw", 0) for b in member_balances)
        total_battery_power = sum(b.get("battery_power_kw", 0) for b in member_balances)
        total_net_balance = sum(b.get("net_balance_kw", 0) for b in member_balances)
        total_grid_export = sum(b.get("grid_export_kw", 0) for b in member_balances)
        total_grid_import = sum(b.get("grid_import_kw", 0) for b in member_balances)
        
        # Storage network metrics
        # Collect battery SOC values from members
        battery_socs = [b.get("battery_soc", 0) for b in member_balances if b.get("battery_soc", 0) > 0]
        
        # Average SOC across all batteries
        avg_soc = sum(battery_socs) / len(battery_socs) if battery_socs else 0.0
        
        # Count members with batteries
        members_with_storage = len(battery_socs)
        
        # Charging/discharging status
        batteries_charging = sum(1 for b in member_balances if b.get("battery_power_kw", 0) < -0.1)
        batteries_discharging = sum(1 for b in member_balances if b.get("battery_power_kw", 0) > 0.1)
        batteries_idle = members_with_storage - batteries_charging - batteries_discharging
        
        # Self-sufficiency percentage
        self_sufficiency = (
            (total_generation / total_consumption * 100.0) 
            if total_consumption > 0 else 0.0
        )
        
        return {
            "total_generation_kw": float(total_generation),
            "total_consumption_kw": float(total_consumption),
            "total_battery_power_kw": float(total_battery_power),
            "total_net_balance_kw": float(total_net_balance),
            "total_grid_export_kw": float(total_grid_export),
            "total_grid_import_kw": float(total_grid_import),
            "self_sufficiency_pct": float(self_sufficiency),
            
            # Storage network status
            "storage_avg_soc": float(avg_soc),
            "storage_members_count": int(members_with_storage),
            "storage_charging_count": int(batteries_charging),
            "storage_discharging_count": int(batteries_discharging),
            "storage_idle_count": int(batteries_idle),
        }

