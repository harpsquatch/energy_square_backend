"""
MongoDB Model for Community Configuration

This module defines the MongoDB document structure for storing
community configuration parameters as ground truth.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from bson import ObjectId


class CommunityConfigDocument(BaseModel):
    """MongoDB document model for community configuration"""
    
    # Document metadata
    id: Optional[ObjectId] = Field(alias="_id", default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = Field(default=1)
    
    # Community Size Parameters
    total_households: int = Field(default=500, ge=1, le=10000)
    average_household_size: float = Field(default=2.5, ge=1.0, le=10.0)
    total_population: int = Field(default=1250)  # Calculated field
    
    # Solar Panel Configuration
    households_with_solar: int = Field(default=300, ge=0)
    average_solar_capacity_per_household: float = Field(default=8.0, ge=0.0, le=50.0)
    total_solar_capacity: float = Field(default=2400.0)  # Calculated field
    
    # Solar Panel Specifications
    solar_panel_efficiency: float = Field(default=0.20, ge=0.1, le=0.5)
    solar_panel_area_per_household: float = Field(default=40.0, ge=0.0, le=200.0)
    total_solar_area: float = Field(default=12000.0)  # Calculated field
    
    # Household Energy Consumption
    average_household_consumption: float = Field(default=3.5, ge=0.0, le=20.0)
    peak_household_consumption: float = Field(default=7.0, ge=0.0, le=50.0)
    total_community_consumption: float = Field(default=1750.0)  # Calculated field
    
    # Scaling Factors
    regional_to_community_scaling: float = Field(default=0.0001, ge=0.00001, le=0.01)
    demand_scaling_factor: float = Field(default=0.25, ge=0.01, le=1.0)
    generation_scaling_factor: float = Field(default=1.0, ge=0.1, le=5.0)
    
    # Grid Interaction Parameters
    grid_import_capacity: float = Field(default=2000.0, ge=0.0, le=10000.0)
    grid_export_capacity: float = Field(default=1500.0, ge=0.0, le=10000.0)
    grid_stability_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    
    # Storage Parameters
    battery_capacity_per_household: float = Field(default=10.0, ge=0.0, le=100.0)
    total_battery_capacity: float = Field(default=5000.0)  # Calculated field
    battery_efficiency: float = Field(default=0.95, ge=0.5, le=1.0)
    
    # Market Parameters
    trading_volume_percentage: float = Field(default=0.1, ge=0.0, le=1.0)
    price_fluctuation_range: float = Field(default=0.12, ge=0.0, le=1.0)
    average_energy_price: float = Field(default=0.25, ge=0.0, le=2.0)
    
    # UI/Display Parameters
    battery_distribution_north: float = Field(default=0.4, ge=0.0, le=1.0, description="North battery distribution percentage")
    battery_distribution_south: float = Field(default=0.35, ge=0.0, le=1.0, description="South battery distribution percentage")
    battery_distribution_center: float = Field(default=0.25, ge=0.0, le=1.0, description="Center battery distribution percentage")
    
    # Leaderboard Parameters
    contribution_tier_gold: float = Field(default=0.15, ge=0.0, le=1.0, description="Gold tier contribution percentage")
    contribution_tier_silver: float = Field(default=0.35, ge=0.0, le=1.0, description="Silver tier contribution percentage")
    contribution_tier_bronze: float = Field(default=0.50, ge=0.0, le=1.0, description="Bronze tier contribution percentage")
    
    # Mock Data Parameters (for leaderboards and examples)
    mock_trader_volume: float = Field(default=1500.0, ge=0.0, le=10000.0, description="Mock trader volume for leaderboards")
    mock_solar_farm_production: float = Field(default=2500.0, ge=0.0, le=10000.0, description="Mock solar farm production")
    mock_efficiency_high: float = Field(default=0.95, ge=0.0, le=1.0, description="Mock high efficiency value")
    mock_efficiency_medium: float = Field(default=0.92, ge=0.0, le=1.0, description="Mock medium efficiency value")
    mock_carbon_offset: float = Field(default=500.0, ge=0.0, le=10000.0, description="Mock carbon offset value")
    
    # Fallback Scaling Parameters
    fallback_regional_scaling: float = Field(default=0.001, ge=0.0001, le=0.01, description="Fallback regional scaling factor")
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
    
    def calculate_derived_values(self) -> None:
        """Calculate values that depend on other parameters"""
        self.total_population = int(self.total_households * self.average_household_size)
        self.total_solar_capacity = self.households_with_solar * self.average_solar_capacity_per_household
        self.total_solar_area = self.households_with_solar * self.solar_panel_area_per_household
        self.total_community_consumption = self.total_households * self.average_household_consumption
        self.total_battery_capacity = self.total_households * self.battery_capacity_per_household
    
    def update_and_calculate(self, **kwargs) -> None:
        """Update parameters and recalculate derived values"""
        for key, value in kwargs.items():
            if hasattr(self, key) and key not in ['id', 'created_at', 'version']:
                setattr(self, key, value)
            elif key not in ['id', 'created_at', 'version']:
                raise ValueError(f"Invalid configuration parameter: {key}")
        
        self.calculate_derived_values()
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "total_households": self.total_households,
            "average_household_size": self.average_household_size,
            "total_population": self.total_population,
            "households_with_solar": self.households_with_solar,
            "average_solar_capacity_per_household": self.average_solar_capacity_per_household,
            "total_solar_capacity": self.total_solar_capacity,
            "solar_panel_efficiency": self.solar_panel_efficiency,
            "solar_panel_area_per_household": self.solar_panel_area_per_household,
            "total_solar_area": self.total_solar_area,
            "average_household_consumption": self.average_household_consumption,
            "peak_household_consumption": self.peak_household_consumption,
            "total_community_consumption": self.total_community_consumption,
            "regional_to_community_scaling": self.regional_to_community_scaling,
            "demand_scaling_factor": self.demand_scaling_factor,
            "generation_scaling_factor": self.generation_scaling_factor,
            "grid_import_capacity": self.grid_import_capacity,
            "grid_export_capacity": self.grid_export_capacity,
            "grid_stability_threshold": self.grid_stability_threshold,
            "battery_capacity_per_household": self.battery_capacity_per_household,
            "total_battery_capacity": self.total_battery_capacity,
            "battery_efficiency": self.battery_efficiency,
            "trading_volume_percentage": self.trading_volume_percentage,
            "price_fluctuation_range": self.price_fluctuation_range,
            "average_energy_price": self.average_energy_price,
            # UI/Display
            "battery_distribution_north": self.battery_distribution_north,
            "battery_distribution_south": self.battery_distribution_south,
            "battery_distribution_center": self.battery_distribution_center,
            # Leaderboards
            "contribution_tier_gold": self.contribution_tier_gold,
            "contribution_tier_silver": self.contribution_tier_silver,
            "contribution_tier_bronze": self.contribution_tier_bronze,
            # Mock parameters
            "mock_trader_volume": self.mock_trader_volume,
            "mock_solar_farm_production": self.mock_solar_farm_production,
            "mock_efficiency_high": self.mock_efficiency_high,
            "mock_efficiency_medium": self.mock_efficiency_medium,
            "mock_carbon_offset": self.mock_carbon_offset,
            # Fallback scaling
            "fallback_regional_scaling": self.fallback_regional_scaling,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version
        }
