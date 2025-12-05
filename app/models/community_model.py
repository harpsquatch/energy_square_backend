"""
Community Model Pydantic Schemas
Validates the complete community model configuration including members, assets, behavior, and control.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Dict, List, Optional, Literal, Tuple
from datetime import datetime
from enum import Enum


class MemberType(str, Enum):
    """Member type enumeration."""
    CONSUMER = "consumer"
    PROSUMER = "prosumer"


class CustomerCategory(str, Enum):
    """Customer category enumeration with behavioral characteristics."""
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    
    def get_outside_active_hours_factor(self) -> float:
        """
        Get activity factor outside of active hours for this category.
        
        Returns:
            Factor (0.0-1.0) representing baseline consumption outside active hours
        """
        factors = {
            "residential": 0.25,  # 25% - sleeping, baseline loads only
            "commercial": 0.05,   # 5% - empty offices, security/emergency systems
            "industrial": 0.90,   # 90% - many run continuous processes 24/7
        }
        return factors.get(self.value, 0.25)
    
    def get_temperature_sensitivity(self) -> float:
        """
        Get temperature sensitivity normalization divisor for this category.
        Lower divisor = higher sensitivity to temperature changes.
        
        Returns:
            Normalization divisor for temperature deviation calculations
        """
        divisors = {
            "residential": 10.0,  # High sensitivity (HVAC for comfort)
            "commercial": 15.0,   # Medium sensitivity (office comfort)
            "industrial": 30.0,   # Low sensitivity (processes less affected)
        }
        return divisors.get(self.value, 10.0)
    
    def get_default_behavior_profile(self) -> dict:
        """
        Get default behavioral parameters for this customer category.
        Users don't need to know technical details - they just select their type.
        
        Returns:
            Dictionary of behavior and noise parameters suitable for this category
        """
        profiles = {
            "residential": {
                "behavior": {
                    "active_hours": [6, 22],           # 6 AM - 10 PM (people at home)
                    "weekday_factor": 1.0,             # Normal weekday activity
                    "weekend_factor": 0.85,            # Slightly less on weekends (people away)
                    "temperature_sensitivity": 0.5,    # Moderate HVAC usage
                    "demand_response_acceptance": 0.7, # Willing to participate in DR
                    "pv_self_consumption_preference": 0.8,  # Prefer to use own solar
                    "battery_usage_preference": 0.6,   # Moderate battery cycling
                    "routine_drift_hours": 1.0,        # 1 hour variability (flexible schedules)
                    "seasonal_scaling_factors": None,
                    "maintenance_days": []
                },
                "variability": {
                    "variability_level": 0.15,    # 15% - humans are unpredictable
                    "random_seed": 42              # Default seed for reproducibility
                }
            },
            "commercial": {
                "behavior": {
                    "active_hours": [8, 18],           # 8 AM - 6 PM (business hours)
                    "weekday_factor": 1.0,             # Full activity on weekdays
                    "weekend_factor": 0.1,             # Minimal weekend activity (closed)
                    "temperature_sensitivity": 0.3,    # Office HVAC (moderate)
                    "demand_response_acceptance": 0.5, # May participate in DR
                    "pv_self_consumption_preference": 0.9,  # High - reduce electricity bills
                    "battery_usage_preference": 0.5,   # Moderate battery use
                    "routine_drift_hours": 0.5,        # Low variability (fixed business hours)
                    "seasonal_scaling_factors": None,
                    "maintenance_days": []
                },
                "variability": {
                    "variability_level": 0.10,    # 10% - more predictable schedules
                    "random_seed": 42
                }
            },
            "industrial": {
                "behavior": {
                    "active_hours": [0, 24],           # 24/7 operations
                    "weekday_factor": 1.0,             # Constant
                    "weekend_factor": 1.0,             # No difference (continuous)
                    "temperature_sensitivity": 0.1,    # Low (processes don't care)
                    "demand_response_acceptance": 0.3, # Low (can't stop production easily)
                    "pv_self_consumption_preference": 0.9,  # High - reduce costs
                    "battery_usage_preference": 0.7,   # High cycling (energy arbitrage)
                    "routine_drift_hours": 0.0,        # Zero variability (automated processes)
                    "seasonal_scaling_factors": None,
                    "maintenance_days": []
                },
                "variability": {
                    "variability_level": 0.05,    # 5% - automated/consistent
                    "random_seed": 42
                }
            },
        }
        return profiles.get(self.value, profiles["residential"])


class BatteryChemistry(str, Enum):
    """Battery chemistry types with different operating characteristics."""
    LITHIUM_ION = "lithium_ion"
    LEAD_ACID = "lead_acid"
    LIFEPO4 = "lifepo4"
    
    def get_soc_limits(self) -> Tuple[float, float]:
        """
        Get safe SOC operating limits for this chemistry.
        
        Returns:
            Tuple of (min_soc, max_soc) as fractions (0.0-1.0)
        """
        limits = {
            "lithium_ion": (0.10, 0.95),  # 10%-95%
            "lead_acid": (0.20, 0.90),    # 20%-90%
            "lifepo4": (0.05, 1.00),      # 5%-100%
        }
        return limits.get(self.value, (0.10, 0.95))
    
    def get_max_power_rate(self) -> float:
        """
        Get maximum charge/discharge C-rate for this chemistry.
        
        Returns:
            Max power rate as fraction of capacity per hour
        """
        rates = {
            "lithium_ion": 0.8,   # 0.8C (80% per hour)
            "lead_acid": 0.2,     # 0.2C (20% per hour - slow charging)
            "lifepo4": 1.0,       # 1.0C (100% per hour - fast charging)
        }
        return rates.get(self.value, 0.8)
    
    def get_round_trip_efficiency(self) -> float:
        """
        Get typical round-trip efficiency for this chemistry.
        
        Returns:
            Efficiency as fraction (0.0-1.0)
        """
        efficiencies = {
            "lithium_ion": 0.92,  # 92%
            "lead_acid": 0.80,    # 80% (lower due to internal resistance)
            "lifepo4": 0.95,      # 95% (best)
        }
        return efficiencies.get(self.value, 0.90)


class LoopMode(str, Enum):
    """Simulation loop mode."""
    CYCLIC = "cyclic"
    LINEAR = "linear"


# === Community Metadata ===
# Note: AggregationMethod enum removed (not used in simulation)

class CommunityMetadata(BaseModel):
    """Community-level metadata."""
    community_id: str = Field(..., description="Unique community identifier")
    name: str = Field(..., description="Readable community name")
    timezone: str = Field(default="UTC", description="Timezone for all timestamps")
    base_pattern_ref: str = Field(..., description="Reference to canonical pattern file")
    created_at: datetime = Field(..., description="Creation timestamp")
    version: str = Field(default="1.0", description="Model version")
    description: Optional[str] = Field(default=None, description="Community description")


# === Simulation Control ===

class SimulationControl(BaseModel):
    """Simulation runtime control parameters."""
    time_step_seconds: int = Field(default=3600, ge=1, description="Simulation update rate in seconds")
    loop_mode: LoopMode = Field(default=LoopMode.CYCLIC, description="Pattern loop mode")
    start_timestamp: datetime = Field(..., description="Simulation start timestamp")
    real_time_speed_factor: float = Field(default=1.0, gt=0, description="Speed multiplier for real-time replay")


# === Member Assets ===

class MemberAssets(BaseModel):
    """Physical assets and capacities for a member."""
    load_capacity_kw: float = Field(..., ge=0, description="Nominal peak demand in kW")
    pv_capacity_kw: float = Field(default=0.0, ge=0, description="Installed PV capacity in kW")
    battery_capacity_kwh: float = Field(default=0.0, ge=0, description="Storage capacity in kWh")
    battery_chemistry: BatteryChemistry = Field(default=BatteryChemistry.LITHIUM_ION, description="Battery chemistry type (determines SOC limits)")
    inverter_efficiency: float = Field(default=0.92, ge=0, le=1, description="Inverter efficiency (0-1)")
    round_trip_efficiency: float = Field(default=0.90, ge=0, le=1, description="Battery round-trip efficiency (0-1)")
    grid_import_limit_kw: float = Field(default=1000.0, ge=0, description="Grid import limit in kW")
    grid_export_limit_kw: float = Field(default=0.0, ge=0, description="Grid export limit in kW")
    # Note: battery_min_soc and battery_max_soc are automatically determined by battery_chemistry
    # You can override them if needed for specific battery models
    battery_min_soc: Optional[float] = Field(default=None, ge=0, le=1, description="Override minimum battery SOC (leave None to use chemistry defaults)")
    battery_max_soc: Optional[float] = Field(default=None, ge=0, le=1, description="Override maximum battery SOC (leave None to use chemistry defaults)")
    
    @model_validator(mode='after')
    def set_soc_limits_from_chemistry(self):
        """Set SOC limits based on battery chemistry if not explicitly provided."""
        if self.battery_capacity_kwh > 0:
            # Get chemistry-appropriate SOC limits
            chem_min, chem_max = self.battery_chemistry.get_soc_limits()
            
            # Use chemistry defaults if not overridden
            if self.battery_min_soc is None:
                self.battery_min_soc = chem_min
            if self.battery_max_soc is None:
                self.battery_max_soc = chem_max
            
            # Validate that overridden values are sensible
            if self.battery_min_soc >= self.battery_max_soc:
                raise ValueError(
                    f"battery_min_soc ({self.battery_min_soc}) must be less than "
                    f"battery_max_soc ({self.battery_max_soc}) for {self.battery_chemistry.value}"
                )
        else:
            # No battery, set to 0
            if self.battery_min_soc is None:
                self.battery_min_soc = 0.0
            if self.battery_max_soc is None:
                self.battery_max_soc = 0.0
        
        return self


# === Seasonal Scaling Factors ===

class SeasonalFactors(BaseModel):
    """Seasonal scaling factors for a month."""
    load: float = Field(default=1.0, gt=0, description="Load multiplier")
    pv: float = Field(default=1.0, gt=0, description="PV generation multiplier")


class SeasonalScalingFactors(BaseModel):
    """Monthly seasonal scaling factors."""
    january: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    february: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    march: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    april: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    may: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    june: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    july: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    august: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    september: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    october: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    november: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    december: SeasonalFactors = Field(default_factory=lambda: SeasonalFactors())
    
    def get_month_factor(self, month: int) -> SeasonalFactors:
        """Get factors for a month (1-12)."""
        months = [
            self.january, self.february, self.march, self.april,
            self.may, self.june, self.july, self.august,
            self.september, self.october, self.november, self.december
        ]
        return months[month - 1]


# === Member Behavior ===

class MemberBehavior(BaseModel):
    """Behavioral configuration for a member."""
    active_hours: List[int] = Field(default=[6, 22], min_length=2, max_length=2, description="Active hours [start, end]")
    weekday_factor: float = Field(default=1.0, gt=0, description="Weekday load multiplier")
    weekend_factor: float = Field(default=0.85, gt=0, description="Weekend load multiplier")
    temperature_sensitivity: float = Field(default=0.0, ge=0, le=1, description="Temperature correlation coefficient")
    demand_response_acceptance: float = Field(default=0.5, ge=0, le=1, description="Probability of responding to DR signals")
    pv_self_consumption_preference: float = Field(default=0.5, ge=0, le=1, description="PV self-consumption preference")
    battery_usage_preference: float = Field(default=0.5, ge=0, le=1, description="Battery depth of cycling preference")
    routine_drift_hours: float = Field(default=0.0, ge=0, description="Allowable daily timing offset in hours")
    seasonal_scaling_factors: Optional[SeasonalScalingFactors] = Field(default=None, description="Per-member seasonal factors")
    maintenance_days: List[str] = Field(default_factory=list, description="Maintenance dates (YYYY-MM-DD)")
    
    @field_validator('active_hours')
    @classmethod
    def validate_active_hours(cls, v):
        """Ensure start < end."""
        if len(v) == 2 and v[0] >= v[1]:
            raise ValueError("active_hours start must be less than end")
        return v


# === Behavioral Variability ===
# Note: Market/P2P trading parameters removed (not implemented in simulation)

class BehavioralVariability(BaseModel):
    """
    Behavioral variability configuration.
    
    Controls how much member behavior deviates from expected patterns.
    Higher values = more unpredictable, lower values = more consistent.
    """
    variability_level: float = Field(
        default=0.10, 
        ge=0, 
        le=1, 
        description="Behavioral variability (0=perfectly predictable, 1=highly random). Residential typically 15%, commercial 10%, industrial 5%"
    )
    random_seed: int = Field(
        default=42, 
        description="Seed for reproducible random variations (same seed = same pattern)"
    )


# === Member Definition ===
# Note: Aggregation configuration removed (not implemented in simulation)

class Member(BaseModel):
    """Complete member definition."""
    member_id: str = Field(..., description="Unique member identifier")
    member_type: MemberType = Field(..., description="Member type (consumer or prosumer)")
    customer_category: CustomerCategory = Field(default=CustomerCategory.RESIDENTIAL, description="Customer category (residential, commercial, industrial)")
    group_id: Optional[str] = Field(default=None, description="Optional cluster or neighborhood ID")
    connection_point: Optional[str] = Field(default=None, description="Optional location label (e.g., 'North Zone', 'Building A')")
    assets: MemberAssets = Field(..., description="Physical assets and capacities")
    behavior: MemberBehavior = Field(..., description="Behavioral configuration")
    variability: BehavioralVariability = Field(default_factory=BehavioralVariability, description="Behavioral variability (predictability of patterns)")


# === Community Control ===

class CommunityControl(BaseModel):
    """Community-level control parameters."""
    grid_import_limit_kw: float = Field(default=10000.0, ge=0, description="Community grid import limit")
    grid_export_limit_kw: float = Field(default=5000.0, ge=0, description="Community grid export limit")
    # Market rates
    import_rate_usd_per_kwh: float = Field(default=0.12, ge=0, description="Grid import rate in USD per kWh")
    export_rate_usd_per_kwh: float = Field(default=0.08, ge=0, description="Grid export rate in USD per kWh")
    # Carbon offset
    carbon_offset_factor_kg_per_kwh: float = Field(default=0.5, ge=0, description="Carbon offset factor in kg CO2 per kWh")
    # Grid nominal values (reference values for simulation calculations)
    grid_voltage_v: float = Field(default=480.0, gt=0, description="Nominal grid voltage in Volts (reference value)")
    grid_frequency_hz: float = Field(default=60.0, gt=0, description="Nominal grid frequency in Hertz (reference value)")
    # Note: grid_stability_index and grid_load_reference_kw are calculated at runtime from simulation state
    # Note: battery_max_power_rate is per-chemistry (see BatteryChemistry.get_max_power_rate())
    # Note: Contribution tiers/leaderboards will be implemented later based on actual simulation performance
    # Note: outside_active_hours_factor and temperature_normalization_divisor are per-member (see CustomerCategory methods)
    # Note: routine_drift implementation removed (dead code, not called in simulation)
    # Regional/climate defaults
    temperature_base_celsius: float = Field(default=20.0, description="Regional base temperature for temperature sensitivity calculations (Celsius)")


# === Complete Community Model ===
# Note: Temporal modifiers (seasonal_scaling_factors, maintenance_days) are per-member in MemberBehavior
# Note: Environment/weather data not implemented - simulation uses pattern file only
# Note: Network topology (nodes, feeders) removed - not used in simulation (member.connection_point is just a label)
# Note: Aggregation rules removed (simulation uses hardcoded sum aggregation)
# Note: Output handlers (MQTT, Kafka, file) removed - results cached in background service

class CommunityModel(BaseModel):
    """Complete community model schema."""
    community: CommunityMetadata = Field(..., description="Community metadata")
    simulation_control: SimulationControl = Field(..., description="Simulation control")
    members: List[Member] = Field(default_factory=list, description="List of community members")
    community_control: CommunityControl = Field(default_factory=CommunityControl, description="Community control")
    
    @model_validator(mode='after')
    def validate_members(self):
        """Validate member configurations."""
        member_ids = [m.member_id for m in self.members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Duplicate member_id found in members list")
        return self
    
    def get_member(self, member_id: str) -> Optional[Member]:
        """Get a member by ID."""
        for member in self.members:
            if member.member_id == member_id:
                return member
        return None
    
    def get_members_by_group(self, group_id: str) -> List[Member]:
        """Get all members in a group."""
        return [m for m in self.members if m.group_id == group_id]
    
    def get_members_by_type(self, member_type: MemberType) -> List[Member]:
        """Get all members of a specific type."""
        return [m for m in self.members if m.member_type == member_type]

