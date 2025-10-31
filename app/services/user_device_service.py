"""
User Device Service - Manages individual user devices (solar, battery, consumption)
Bottom-up approach: Each user has their own devices, aggregated to community level
"""
from typing import Dict, Any, List, Optional
from app.db.database import get_database
import logging

logger = logging.getLogger(__name__)


class UserDeviceService:
    """Service for managing individual user devices and metrics"""

    async def get_user_device_data(self, user_id: str) -> Dict[str, Any]:
        """Get device data for a specific user from MongoDB"""
        try:
            db = await get_database()
            user_doc = await db["user_devices"].find_one(
                {"user_id": user_id},
                {"_id": 0}
            )
            
            if user_doc:
                return user_doc
            
            # Return default if user not found
            logger.warning(f"User {user_id} not found in user_devices, returning defaults")
            return self._get_default_user_data(user_id)
            
        except Exception as e:
            logger.error(f"Error getting user device data for {user_id}: {e}")
            return self._get_default_user_data(user_id)

    async def get_all_users_data(self) -> List[Dict[str, Any]]:
        """Get device data for all users (for community aggregation)"""
        try:
            db = await get_database()
            cursor = db["user_devices"].find({}, {"_id": 0})
            users = []
            async for doc in cursor:
                users.append(doc)
            return users
        except Exception as e:
            logger.error(f"Error getting all users data: {e}")
            return []

    async def initialize_sample_users(self):
        """Initialize 5 sample users with different device configurations"""
        try:
            db = await get_database()
            
            sample_users = [
                {
                    "user_id": "user_001",
                    "name": "Solar Pro User",
                    "solar_capacity_kw": 5.0,  # 5kW solar system
                    "battery_capacity_kwh": 10.0,  # 10kWh battery
                    "battery_soc_pct": 85.0,
                    "avg_daily_consumption_kwh": 12.0,
                    "location": "North Zone"
                },
                {
                    "user_id": "user_002",
                    "name": "Moderate Solar User",
                    "solar_capacity_kw": 3.5,  # 3.5kW solar system
                    "battery_capacity_kwh": 7.5,  # 7.5kWh battery
                    "battery_soc_pct": 65.0,
                    "avg_daily_consumption_kwh": 10.0,
                    "location": "Central Zone"
                },
                {
                    "user_id": "user_003",
                    "name": "Small Solar User",
                    "solar_capacity_kw": 2.0,  # 2kW solar system
                    "battery_capacity_kwh": 5.0,  # 5kWh battery
                    "battery_soc_pct": 45.0,
                    "avg_daily_consumption_kwh": 8.0,
                    "location": "South Zone"
                },
                {
                    "user_id": "user_004",
                    "name": "Large Solar User",
                    "solar_capacity_kw": 8.0,  # 8kW solar system
                    "battery_capacity_kwh": 15.0,  # 15kWh battery
                    "battery_soc_pct": 75.0,
                    "avg_daily_consumption_kwh": 15.0,
                    "location": "North Zone"
                },
                {
                    "user_id": "user_005",
                    "name": "Standard Solar User",
                    "solar_capacity_kw": 4.0,  # 4kW solar system
                    "battery_capacity_kwh": 8.0,  # 8kWh battery
                    "battery_soc_pct": 55.0,
                    "avg_daily_consumption_kwh": 9.5,
                    "location": "Central Zone"
                }
            ]
            
            # Upsert each user
            for user in sample_users:
                await db["user_devices"].update_one(
                    {"user_id": user["user_id"]},
                    {"$set": user},
                    upsert=True
                )
            
            logger.info(f"Initialized {len(sample_users)} sample users")
            return sample_users
            
        except Exception as e:
            logger.error(f"Error initializing sample users: {e}")
            raise

    def _get_default_user_data(self, user_id: str) -> Dict[str, Any]:
        """Return default device data for a user (fallback)"""
        return {
            "user_id": user_id,
            "name": "Default User",
            "solar_capacity_kw": 4.0,
            "battery_capacity_kwh": 8.0,
            "battery_soc_pct": 50.0,
            "avg_daily_consumption_kwh": 10.0,
            "location": "Unknown"
        }

    async def calculate_user_production_today(self, user_id: str, community_24h_flow: List[Dict[str, Any]]) -> float:
        """Calculate user's production today based on their solar capacity vs community total
        
        Uses community production patterns scaled by user's capacity share.
        """
        try:
            user_data = await self.get_user_device_data(user_id)
            user_capacity = user_data.get("solar_capacity_kw", 0)
            
            # Get total community production for 24h
            total_produced_24h = sum([p.get('produced', 0) for p in community_24h_flow])
            
            # Get all users to calculate community total capacity
            all_users = await self.get_all_users_data()
            if not all_users:
                # Fallback: use community config
                from app.services.community_config import get_community_config
                config = await get_community_config()
                total_capacity = getattr(config, 'total_solar_capacity', 20.0)  # Default 20kW
            else:
                total_capacity = sum([u.get("solar_capacity_kw", 0) for u in all_users])
            
            if total_capacity == 0:
                return 0.0
            
            # User's share of production = (user_capacity / total_capacity) * total_production
            user_production_24h = (user_capacity / total_capacity) * total_produced_24h
            
            return round(user_production_24h, 2)
            
        except Exception as e:
            logger.error(f"Error calculating user production: {e}")
            return 0.0

    async def calculate_user_consumption_today(self, user_id: str) -> float:
        """Calculate user's consumption today based on their average daily consumption
        
        Uses real-time patterns from community demand data scaled to user's average.
        """
        try:
            user_data = await self.get_user_device_data(user_id)
            avg_daily = user_data.get("avg_daily_consumption_kwh", 10.0)
            
            # For MVP: use average daily consumption
            # In production: would use hourly patterns from smart meter data
            return round(avg_daily, 2)
            
        except Exception as e:
            logger.error(f"Error calculating user consumption: {e}")
            return 0.0

    async def aggregate_community_metrics(self) -> Dict[str, Any]:
        """Aggregate all user metrics to get community totals (bottom-up)"""
        try:
            all_users = await self.get_all_users_data()
            
            if not all_users:
                logger.warning("No users found, returning empty metrics")
                return {
                    "total_solar_capacity_kw": 0.0,
                    "total_battery_capacity_kwh": 0.0,
                    "total_consumption_kwh": 0.0,
                    "user_count": 0
                }
            
            total_solar_capacity = sum([u.get("solar_capacity_kw", 0) for u in all_users])
            total_battery_capacity = sum([u.get("battery_capacity_kwh", 0) for u in all_users])
            total_consumption = sum([u.get("avg_daily_consumption_kwh", 0) for u in all_users])
            
            # Calculate weighted average battery SOC
            total_battery_energy = 0
            for user in all_users:
                capacity = user.get("battery_capacity_kwh", 0)
                soc = user.get("battery_soc_pct", 0)
                total_battery_energy += capacity * (soc / 100.0)
            
            avg_soc = (total_battery_energy / total_battery_capacity * 100.0) if total_battery_capacity > 0 else 0.0
            
            return {
                "total_solar_capacity_kw": round(total_solar_capacity, 2),
                "total_battery_capacity_kwh": round(total_battery_capacity, 2),
                "total_consumption_kwh": round(total_consumption, 2),
                "average_battery_soc_pct": round(avg_soc, 1),
                "user_count": len(all_users)
            }
            
        except Exception as e:
            logger.error(f"Error aggregating community metrics: {e}")
            return {
                "total_solar_capacity_kw": 0.0,
                "total_battery_capacity_kwh": 0.0,
                "total_consumption_kwh": 0.0,
                "average_battery_soc_pct": 0.0,
                "user_count": 0
            }

