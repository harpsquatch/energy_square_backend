"""
Feature Engineering Module
Calculates derived metrics and features from transformed data.
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class FeatureEngineering:
    """Engineer features and derived metrics from transformed data."""
    
    def __init__(self, emission_factor: float = 0.5, nominal_frequency: float = 60.0, nominal_voltage: float = 240.0):
        """
        Initialize feature engineering service.
        
        Args:
            emission_factor: Carbon emission factor (kg CO2 per kWh)
            nominal_frequency: Nominal grid frequency (Hz)
            nominal_voltage: Nominal grid voltage (V)
        """
        self.emission_factor = emission_factor
        self.nominal_frequency = nominal_frequency
        self.nominal_voltage = nominal_voltage
    
    def calculate_power_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate power generation and consumption metrics.
        
        Args:
            df: DataFrame with raw power columns
            
        Returns:
            DataFrame with calculated power metrics
        """
        if df.empty:
            return df
        
        # Power metrics (kW) - clamp solar to non-negative values to prevent invalid data
        df['solar_generation_kw'] = df['PVPCS_Active_Power'].fillna(0).clip(lower=0)
        df['fuel_cell_generation_kw'] = df['FC_Active_Power'].fillna(0).clip(lower=0)
        df['battery_power_kw'] = df['Battery_Active_Power'].fillna(0)
        
        # Consumption: GE_Active_Power can be negative (export). 
        # If negative, community is exporting (net export scenario). Consumption should be estimated from generation - battery flow
        # For now, take positive GE_Active_Power as direct consumption, negative values mean net export
        # Add fallback: if GE_Active_Power is negative/zero, estimate consumption from generation patterns
        df['total_consumption_kw'] = df['GE_Active_Power'].apply(
            lambda x: max(0, x) if pd.notna(x) and x > 0 else 0
        )
        
        # Validation: Flag periods with zero consumption when generation is significant (potential data issue)
        # This helps identify months like May-July 2023 with suspicious zero consumption
        has_generation = (df['solar_generation_kw'] > 0) | (df['fuel_cell_generation_kw'] > 0)
        zero_consumption = df['total_consumption_kw'] == 0
        suspicious_periods = has_generation & zero_consumption
        if suspicious_periods.any():
            logger.warning(f"Found {suspicious_periods.sum()} periods with generation but zero consumption (potential data issue)")
        
        # Total generation
        df['total_generation_kw'] = df['solar_generation_kw'] + df['fuel_cell_generation_kw']
        
        # Net balance
        df['net_balance_kw'] = df['total_generation_kw'] - df['total_consumption_kw'] + df['battery_power_kw']
        
        return df
    
    def calculate_energy_metrics(self, df: pd.DataFrame, interval_hours: float = 1.0) -> pd.DataFrame:
        """
        Calculate energy metrics from power metrics.
        
        Args:
            df: DataFrame with power metrics
            interval_hours: Time interval in hours (default: 1 hour = 1.0)
            
        Returns:
            DataFrame with energy metrics
        """
        if df.empty:
            return df
        
        # Energy calculations (kWh)
        df['solar_generation_kwh'] = df['solar_generation_kw'] * interval_hours
        df['fuel_cell_generation_kwh'] = df['fuel_cell_generation_kw'] * interval_hours
        df['total_consumption_kwh'] = df['total_consumption_kw'] * interval_hours
        df['battery_energy_kwh'] = df['battery_power_kw'] * interval_hours
        df['net_balance_kwh'] = df['net_balance_kw'] * interval_hours
        
        return df
    
    def calculate_grid_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate grid-related metrics.
        
        Args:
            df: DataFrame with voltage and frequency data
            
        Returns:
            DataFrame with grid metrics
        """
        if df.empty:
            return df
        
        # Grid metrics (from original Mesa data)
        df['grid_voltage_v'] = df['MG-LV-MSB_AC_Voltage'].fillna(0)
        df['grid_frequency_hz'] = df['MG-LV-MSB_Frequency'].fillna(0)
        
        # Grid import/export
        df['grid_export_kw'] = df['net_balance_kw'].apply(lambda x: max(0, x))
        df['grid_import_kw'] = df['net_balance_kw'].apply(lambda x: max(0, -x))
        
        return df
    
    def calculate_stability_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate grid stability index.
        
        Args:
            df: DataFrame with grid frequency and voltage
            
        Returns:
            DataFrame with stability metrics
        """
        if df.empty:
            return df
        
        # Calculate stability index (based on frequency and voltage stability)
        frequency_deviation = abs(df['grid_frequency_hz'] - self.nominal_frequency)
        voltage_deviation = abs(df['grid_voltage_v'] - self.nominal_voltage)
        
        # Normalize deviations (frequency tolerance ±0.5 Hz, voltage tolerance ±10 V)
        freq_stability = np.clip(1 - (frequency_deviation / 0.5), 0, 1)
        voltage_stability = np.clip(1 - (voltage_deviation / 10.0), 0, 1)
        
        # Overall stability index (weighted average)
        df['grid_stability_index'] = (freq_stability * 0.6 + voltage_stability * 0.4)
        
        return df
    
    def calculate_renewable_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate renewable energy percentage and grid load.
        
        Args:
            df: DataFrame with generation and consumption data
            
        Returns:
            DataFrame with renewable metrics
        """
        if df.empty:
            return df
        
        # Renewable percentage (solar / total supply)
        total_supply = df['total_generation_kw'] + df['grid_import_kw']
        df['renewable_pct'] = (df['solar_generation_kw'] / total_supply.replace(0, np.nan) * 100).fillna(0)
        
        # Grid load percentage (consumption / estimated capacity)
        estimated_capacity = df['total_generation_kw'].max() * 1.2
        df['grid_load_pct'] = (df['total_consumption_kw'] / estimated_capacity * 100).fillna(0)
        
        return df
    
    def calculate_carbon_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate carbon offset metrics.
        
        NOTE: This uses a simplified placeholder model (fixed 0.5 kg CO2/kWh emission factor).
        In production, this should be replaced with:
        - Dynamic grid mix factors (varying by time of day)
        - Seasonal adjustments
        - Regional grid emission factors
        - Real-time grid carbon intensity data
        
        Args:
            df: DataFrame with generation data
            
        Returns:
            DataFrame with carbon metrics
        """
        if df.empty:
            return df
        
        # Carbon offset (PLACEHOLDER MODEL: fixed emission factor of 0.5 kg CO2/kWh)
        # This represents an average grid mix emission factor but is not dynamic
        df['carbon_offset_kg'] = df['solar_generation_kwh'] * self.emission_factor
        
        # Cumulative metrics
        df['cumulative_solar_kwh'] = df['solar_generation_kwh'].cumsum()
        df['cumulative_consumption_kwh'] = df['total_consumption_kwh'].cumsum()
        df['cumulative_carbon_offset_kg'] = df['carbon_offset_kg'].cumsum()
        
        return df
    
    def calculate_storage_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate storage/battery metrics at community level.
        
        Note: Storage metrics are aggregated from individual user batteries.
        For community dashboard, we estimate based on battery power flow.
        
        Args:
            df: DataFrame with battery power data
            
        Returns:
            DataFrame with storage metrics
        """
        if df.empty:
            return df
        
        # Estimate storage network capacity (kWh) - based on peak battery power
        # This would ideally come from user battery capacities aggregation
        # For now, estimate: peak battery discharge rate * 4 hours = capacity
        max_battery_power = df['battery_power_kw'].abs().max()
        df['storage_network_capacity_kwh'] = max_battery_power * 4.0 if max_battery_power > 0 else 0.0
        
        # Estimate current SOC (%) - simplified model based on battery power flow
        # Positive battery_power_kw = discharging (negative = charging)
        # This is a simplified estimation; actual SOC should come from user aggregation
        # For community level, we estimate based on power flow direction
        battery_discharging = df['battery_power_kw'] > 0
        # If discharging, estimate SOC decreasing; if charging, estimate SOC increasing
        # Simplified: assume 50% average with ±10% variation based on power flow
        base_soc = 50.0
        soc_variation = np.clip(df['battery_power_kw'] / (max_battery_power + 0.1) * 20, -20, 20)
        df['current_soc_pct'] = np.clip(base_soc + soc_variation, 0, 100)
        
        # Available energy (kWh) = capacity * (SOC / 100)
        df['storage_available_energy_kwh'] = df['storage_network_capacity_kwh'] * (df['current_soc_pct'] / 100.0)
        
        return df
    
    def calculate_pricing_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate grid pricing/tariff metrics.
        
        Args:
            df: DataFrame with grid interaction data
            
        Returns:
            DataFrame with pricing metrics
        """
        if df.empty:
            return df
        
        # Import rate ($/kWh) - time-of-use pricing
        # Base rate with peak/off-peak variation
        # Peak hours: 6-10, 18-22 (higher rate)
        # Off-peak: other hours (lower rate)
        base_import_rate = 0.12  # $/kWh base rate
        peak_import_multiplier = 1.5  # 50% higher during peak
        
        is_peak = ((df['hour'] >= 6) & (df['hour'] <= 10)) | ((df['hour'] >= 18) & (df['hour'] <= 22))
        df['import_rate_usd_per_kwh'] = base_import_rate * np.where(is_peak, peak_import_multiplier, 1.0)
        
        # Export rate ($/kWh) - feed-in tariff (typically lower than import rate)
        base_export_rate = 0.08  # $/kWh base feed-in rate
        # Export rate can be time-dependent (higher during peak demand)
        df['export_rate_usd_per_kwh'] = base_export_rate * np.where(is_peak, 1.2, 1.0)
        
        return df
    
    def calculate_alert_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate outage/alert metrics.
        
        Args:
            df: DataFrame with grid stability data
            
        Returns:
            DataFrame with alert metrics
        """
        if df.empty:
            return df
        
        # Outage zones - based on stability index threshold
        # If stability index drops below 0.5, consider it an outage condition
        stability_threshold = 0.5
        outage_condition = df['grid_stability_index'] < stability_threshold
        
        # Count of outage zones (simplified: 1 if outage condition, 0 otherwise)
        # In real system, this would map to actual geographic zones
        df['outage_zones_count'] = outage_condition.astype(int)
        
        # Outage zones list (comma-separated zone IDs)
        # Simplified: if outage, mark as "Zone_1" (would be actual zone IDs in production)
        df['outage_zones_list'] = df.apply(
            lambda row: "Zone_1" if row['outage_zones_count'] > 0 else "", 
            axis=1
        )
        
        return df
    
    def engineer_features(self, df: pd.DataFrame, interval_hours: float = 1.0) -> pd.DataFrame:
        """
        Complete feature engineering pipeline.
        
        Args:
            df: Transformed DataFrame (hourly intervals)
            interval_hours: Time interval in hours (default: 1.0 for hourly data)
            
        Returns:
            DataFrame with all engineered features
        """
        if df.empty:
            return df
        
        # Calculate power metrics
        df = self.calculate_power_metrics(df)
        
        # Calculate energy metrics
        df = self.calculate_energy_metrics(df, interval_hours)
        
        # Calculate grid metrics
        df = self.calculate_grid_metrics(df)
        
        # Calculate stability metrics
        df = self.calculate_stability_metrics(df)
        
        # Calculate renewable metrics
        df = self.calculate_renewable_metrics(df)
        
        # Calculate carbon metrics
        df = self.calculate_carbon_metrics(df)
        
        # Calculate storage metrics
        df = self.calculate_storage_metrics(df)
        
        # Calculate pricing metrics
        df = self.calculate_pricing_metrics(df)
        
        # Calculate alert metrics
        df = self.calculate_alert_metrics(df)
        
        logger.info(f"Feature engineering complete: {len(df.columns)} columns")
        
        return df

