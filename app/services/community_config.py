"""
Community Configuration for Energy Square Platform

This module manages community configuration stored in MongoDB as ground truth,
eliminating hardcoded values and providing persistent configuration management.
"""

from typing import Dict, Any, Optional
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.database import get_database
from app.models.community_config import CommunityConfigDocument

logger = logging.getLogger(__name__)


class CommunityConfigManager:
    """Manager for community configuration with MongoDB persistence"""
    
    def __init__(self):
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.collection_name = "community_config"
        self._config_cache: Optional[CommunityConfigDocument] = None
    
    async def _get_database(self) -> AsyncIOMotorDatabase:
        """Get database connection"""
        if self.db is None:
            self.db = await get_database()
        return self.db
    
    async def _get_collection(self):
        """Get the community config collection"""
        db = await self._get_database()
        return db[self.collection_name]
    
    async def _load_config(self) -> CommunityConfigDocument:
        """Load configuration from MongoDB or create default"""
        try:
            collection = await self._get_collection()
            
            # Try to find existing singleton configuration
            config_doc = await collection.find_one({"singleton": True})
            
            if config_doc:
                # Convert MongoDB document to Pydantic model
                config = CommunityConfigDocument(**config_doc)
                logger.info("Loaded community configuration from MongoDB")
                return config
            else:
                # Create default configuration
                logger.info("No config found in MongoDB, creating default configuration")
                default_config = CommunityConfigDocument()
                await self._save_config(default_config)
                return default_config
                
        except Exception as e:
            logger.error(f"Error loading config from MongoDB: {e}, using defaults")
            return CommunityConfigDocument()
    
    async def _save_config(self, config: CommunityConfigDocument) -> None:
        """Save configuration to MongoDB"""
        try:
            collection = await self._get_collection()
            
            # Convert to dict for MongoDB storage and add singleton marker
            config_dict = config.dict(by_alias=True, exclude={"id"})
            config_dict["singleton"] = True
            
            # Upsert singleton document deterministically
            await collection.update_one(
                {"singleton": True},
                {"$set": config_dict},
                upsert=True
            )
            
            logger.info("Saved community configuration to MongoDB")
            
        except Exception as e:
            logger.error(f"Error saving config to MongoDB: {e}")
            raise
    
    async def get_config(self) -> CommunityConfigDocument:
        """Get the current community configuration"""
        if self._config_cache is None:
            self._config_cache = await self._load_config()
        return self._config_cache
    
    async def update_config(self, **kwargs) -> None:
        """Update configuration parameters and save to MongoDB"""
        try:
            # Get current config
            config = await self.get_config()
            
            # Update and recalculate derived values
            config.update_and_calculate(**kwargs)
            
            # Save to MongoDB
            await self._save_config(config)
            
            # Update cache
            self._config_cache = config
            
            logger.info(f"Updated configuration: {list(kwargs.keys())}")
            
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            raise
    
    async def reset_config(self) -> None:
        """Reset configuration to defaults and save to MongoDB"""
        try:
            # Create new default configuration
            default_config = CommunityConfigDocument()
            
            # Save to MongoDB
            await self._save_config(default_config)
            
            # Update cache
            self._config_cache = default_config
            
            logger.info("Reset configuration to defaults in MongoDB")
            
        except Exception as e:
            logger.error(f"Error resetting config: {e}")
            raise
    
    async def get_scaling_factors(self) -> Dict[str, float]:
        """Get all scaling factors for calculations"""
        config = await self.get_config()
        return {
            "regional_to_community_scaling": config.regional_to_community_scaling,
            "demand_scaling_factor": config.demand_scaling_factor,
            "generation_scaling_factor": config.generation_scaling_factor,
            "trading_volume_percentage": config.trading_volume_percentage
        }
    
    async def get_community_metrics(self) -> Dict[str, Any]:
        """Get key community metrics for dashboard display"""
        config = await self.get_config()
        return {
            "total_households": config.total_households,
            "households_with_solar": config.households_with_solar,
            "solar_coverage_percentage": (config.households_with_solar / config.total_households) * 100,
            "total_solar_capacity": config.total_solar_capacity,
            "total_community_consumption": config.total_community_consumption,
            "average_household_consumption": config.average_household_consumption,
            "total_battery_capacity": config.total_battery_capacity,
            "grid_import_capacity": config.grid_import_capacity,
            "grid_export_capacity": config.grid_export_capacity
        }
    
    async def calculate_realistic_scaling(self, regional_demand_mw: float) -> float:
        """Calculate realistic community consumption from regional demand"""
        config = await self.get_config()
        regional_demand_kw = regional_demand_mw * 1000
        community_demand_kw = regional_demand_kw * config.regional_to_community_scaling
        
        # Ensure it's within realistic bounds
        max_realistic_demand = config.total_community_consumption * 1.5
        min_realistic_demand = config.total_community_consumption * 0.5
        
        return max(min_realistic_demand, min(community_demand_kw, max_realistic_demand))
    
    async def calculate_solar_generation_scaling(self, raw_solar_power: float) -> float:
        """Calculate realistic solar generation scaling"""
        config = await self.get_config()
        max_realistic_generation = config.total_solar_capacity * 1.2
        min_realistic_generation = 0.0
        
        return max(min_realistic_generation, min(raw_solar_power, max_realistic_generation))
    
    async def validate_configuration(self) -> Dict[str, Any]:
        """Validate current configuration for potential issues"""
        config = await self.get_config()
        issues = []
        warnings = []
        
        # Check for potential issues
        if config.households_with_solar > config.total_households:
            issues.append("Solar households exceed total households")
        
        if config.peak_household_consumption < config.average_household_consumption:
            issues.append("Peak consumption is less than average consumption")
        
        if config.regional_to_community_scaling > 0.01:
            warnings.append("Regional scaling factor seems high (>1% of regional demand)")
        
        if config.total_solar_capacity > config.total_community_consumption * 2:
            warnings.append("Solar capacity is more than 2x community consumption")
        
        if config.battery_capacity_per_household > 50:
            warnings.append("Battery capacity per household seems high (>50 kWh)")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "config_summary": {
                "total_households": config.total_households,
                "solar_coverage": f"{(config.households_with_solar / config.total_households * 100):.1f}%",
                "total_solar_capacity": f"{config.total_solar_capacity:.0f} kW",
                "total_consumption": f"{config.total_community_consumption:.0f} kW",
                "solar_ratio": f"{(config.total_solar_capacity / config.total_community_consumption):.2f}"
            }
        }


# Global configuration instance
community_config = CommunityConfigManager()


async def get_community_config() -> CommunityConfigDocument:
    """Get the global community configuration"""
    return await community_config.get_config()


async def get_scaling_factors() -> Dict[str, float]:
    """Get scaling factors for energy calculations"""
    return await community_config.get_scaling_factors()


async def get_community_metrics() -> Dict[str, Any]:
    """Get community metrics for dashboard"""
    return await community_config.get_community_metrics()