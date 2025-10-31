"""
Community Configuration API Endpoints

This module provides endpoints for community managers to configure
community parameters through the frontend interface.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, validator
import logging
from app.services.community_config import community_config, CommunityConfigDocument

logger = logging.getLogger(__name__)

router = APIRouter()


class CommunityConfigUpdate(BaseModel):
    """Schema for updating community configuration"""
    
    # Community Size Parameters
    total_households: Optional[int] = Field(None, ge=1, le=10000, description="Number of households in the community")
    average_household_size: Optional[float] = Field(None, ge=1.0, le=10.0, description="Average people per household")
    
    # Solar Panel Configuration
    households_with_solar: Optional[int] = Field(None, ge=0, description="Number of households with solar panels")
    average_solar_capacity_per_household: Optional[float] = Field(None, ge=0.0, le=50.0, description="kW per household")
    solar_panel_efficiency: Optional[float] = Field(None, ge=0.1, le=0.5, description="Solar panel efficiency (0.1-0.5)")
    solar_panel_area_per_household: Optional[float] = Field(None, ge=0.0, le=200.0, description="m² per household")
    
    # Household Energy Consumption
    average_household_consumption: Optional[float] = Field(None, ge=0.0, le=20.0, description="kW per household")
    peak_household_consumption: Optional[float] = Field(None, ge=0.0, le=50.0, description="kW peak consumption per household")
    
    # Scaling Factors
    regional_to_community_scaling: Optional[float] = Field(None, ge=0.00001, le=0.01, description="Regional to community scaling factor")
    demand_scaling_factor: Optional[float] = Field(None, ge=0.01, le=1.0, description="Demand scaling factor")
    
    # Grid Interaction Parameters
    grid_import_capacity: Optional[float] = Field(None, ge=0.0, le=10000.0, description="kW max grid import")
    grid_export_capacity: Optional[float] = Field(None, ge=0.0, le=10000.0, description="kW max grid export")
    grid_stability_threshold: Optional[float] = Field(None, ge=0.5, le=1.0, description="Grid stability threshold")
    
    # Storage Parameters
    battery_capacity_per_household: Optional[float] = Field(None, ge=0.0, le=100.0, description="kWh per household")
    battery_efficiency: Optional[float] = Field(None, ge=0.5, le=1.0, description="Battery efficiency")
    
    # Market Parameters
    trading_volume_percentage: Optional[float] = Field(None, ge=0.0, le=1.0, description="Trading volume percentage")
    price_fluctuation_range: Optional[float] = Field(None, ge=0.0, le=1.0, description="Price fluctuation range")
    average_energy_price: Optional[float] = Field(None, ge=0.0, le=2.0, description="€/kWh average price")
    
    # UI/Display Parameters
    battery_distribution_north: Optional[float] = Field(None, ge=0.0, le=1.0, description="North battery distribution percentage")
    battery_distribution_south: Optional[float] = Field(None, ge=0.0, le=1.0, description="South battery distribution percentage")
    battery_distribution_center: Optional[float] = Field(None, ge=0.0, le=1.0, description="Center battery distribution percentage")
    
    # Leaderboard Parameters
    contribution_tier_gold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Gold tier contribution percentage")
    contribution_tier_silver: Optional[float] = Field(None, ge=0.0, le=1.0, description="Silver tier contribution percentage")
    contribution_tier_bronze: Optional[float] = Field(None, ge=0.0, le=1.0, description="Bronze tier contribution percentage")
    
    # Mock Data Parameters
    mock_trader_volume: Optional[float] = Field(None, ge=0.0, le=10000.0, description="Mock trader volume for leaderboards")
    mock_solar_farm_production: Optional[float] = Field(None, ge=0.0, le=10000.0, description="Mock solar farm production")
    mock_efficiency_high: Optional[float] = Field(None, ge=0.0, le=1.0, description="Mock high efficiency value")
    mock_efficiency_medium: Optional[float] = Field(None, ge=0.0, le=1.0, description="Mock medium efficiency value")
    mock_carbon_offset: Optional[float] = Field(None, ge=0.0, le=10000.0, description="Mock carbon offset value")
    
    # Fallback Scaling Parameters
    fallback_regional_scaling: Optional[float] = Field(None, ge=0.0001, le=0.01, description="Fallback regional scaling factor")
    
    @validator('households_with_solar')
    def validate_solar_households(cls, v, values):
        if v is not None and 'total_households' in values and values['total_households'] is not None:
            if v > values['total_households']:
                raise ValueError('households_with_solar cannot exceed total_households')
        return v
    
    @validator('peak_household_consumption')
    def validate_peak_consumption(cls, v, values):
        if v is not None and 'average_household_consumption' in values and values['average_household_consumption'] is not None:
            if v < values['average_household_consumption']:
                raise ValueError('peak_household_consumption must be >= average_household_consumption')
        return v


class CommunityConfigResponse(BaseModel):
    """Schema for community configuration response"""
    config: Dict[str, Any]
    metrics: Dict[str, Any]
    scaling_factors: Dict[str, float]


@router.get("/config", response_model=CommunityConfigResponse)
async def get_community_config():
    """Get current community configuration"""
    try:
        config = await community_config.get_config()
        metrics = await community_config.get_community_metrics()
        scaling_factors = await community_config.get_scaling_factors()
        
        return CommunityConfigResponse(
            config=config.to_dict(),
            metrics=metrics,
            scaling_factors=scaling_factors
        )
    except Exception as e:
        logger.error(f"Error getting community config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get community configuration"
        )


@router.put("/config", response_model=CommunityConfigResponse)
async def update_community_config(config_update: CommunityConfigUpdate):
    """Update community configuration"""
    try:
        # Convert to dict and filter out None values
        update_data = {k: v for k, v in config_update.dict().items() if v is not None}
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No configuration parameters provided"
            )
        
        # Update configuration
        await community_config.update_config(**update_data)
        
        # Get updated configuration
        config = await community_config.get_config()
        metrics = await community_config.get_community_metrics()
        scaling_factors = await community_config.get_scaling_factors()
        
        logger.info(f"Community configuration updated: {list(update_data.keys())}")
        
        return CommunityConfigResponse(
            config=config.to_dict(),
            metrics=metrics,
            scaling_factors=scaling_factors
        )
        
    except ValueError as e:
        logger.error(f"Validation error updating community config: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating community config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update community configuration"
        )


@router.post("/config/reset")
async def reset_community_config():
    """Reset community configuration to default values"""
    try:
        # Reset to default configuration
        await community_config.reset_config()
        
        config = await community_config.get_config()
        metrics = await community_config.get_community_metrics()
        scaling_factors = await community_config.get_scaling_factors()
        
        logger.info("Community configuration reset to defaults")
        
        return CommunityConfigResponse(
            config=config.to_dict(),
            metrics=metrics,
            scaling_factors=scaling_factors
        )
        
    except Exception as e:
        logger.error(f"Error resetting community config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset community configuration"
        )


@router.get("/config/validation")
async def validate_configuration():
    """Validate current configuration for potential issues"""
    try:
        # Delegate to business logic layer
        validation_result = await community_config.validate_configuration()
        return validation_result
        
    except Exception as e:
        logger.error(f"Error validating configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate configuration"
        )
