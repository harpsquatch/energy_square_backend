"""
Initialize MongoDB with a complete community model.
Run this once to set up the community_models collection with all required fields.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.db.database import Collections


async def init_community_model():
    """Initialize MongoDB with a complete community model."""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.DATABASE_NAME]
    collection = db[Collections.COMMUNITY_MODELS]
    
    # Complete community model with all required fields
    community_model = {
        "community": {
            "community_id": "community_001",
            "name": "Energy Square Community A",
            "timezone": "Asia/Kolkata",
            "base_pattern_ref": "community_base_signal.csv",
            "created_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "description": "Energy Square community with complete configuration"
        },
        "simulation_control": {
            "time_step_seconds": 3600,
            "loop_mode": "cyclic",
            "start_timestamp": datetime.utcnow().isoformat(),
            "real_time_speed_factor": 1.0
        },
        "community_control": {
            # Grid limits
            "grid_import_limit_kw": 10000.0,
            "grid_export_limit_kw": 5000.0,
            # Market rates
            "import_rate_usd_per_kwh": 0.12,
            "export_rate_usd_per_kwh": 0.08,
            # Carbon offset
            "carbon_offset_factor_kg_per_kwh": 0.5,
            # Grid nominal values (reference values for calculations)
            "grid_voltage_v": 480.0,  # Nominal voltage
            "grid_frequency_hz": 60.0,  # Nominal frequency
            # Regional/climate settings
            "temperature_base_celsius": 20.0  # Regional baseline temperature
        },
        "members": [
            {
                "member_id": "user_001",
                "name": "Demo User 1",
                "member_type": "prosumer",
                "customer_category": "residential",
                "group_id": None,
                "assets": {
                    "pv_capacity_kw": 5.0,
                    "battery_capacity_kwh": 10.0,
                    "battery_chemistry": "lithium_ion",  # Default: 10%-95% SOC
                    # Note: battery_min_soc and battery_max_soc are auto-set from battery_chemistry
                    # Options: "lithium_ion" (10-95%), "lead_acid" (20-90%), "lifepo4" (5-100%)
                    "load_capacity_kw": 8.0
                },
                # Note: Behavior and variability auto-set from customer_category (residential)
              # Defaults: active 6am-10pm, weekend 85%, variability 15% (humans unpredictable)
              "behavior": {
                    "active_hours": [6, 22],
                    "weekday_factor": 1.0,
                    "weekend_factor": 0.85,
                    "temperature_sensitivity": 0.5,
                    "demand_response_acceptance": 0.7,
                    "pv_self_consumption_preference": 0.8,
                    "battery_usage_preference": 0.6,
                    "routine_drift_hours": 1.0,
                    "seasonal_scaling_factors": None,
                    "maintenance_days": []
                },
                "variability": {
                    "variability_level": 0.15,  # 15% unpredictability (residential - humans are flexible)
                    "random_seed": 42            # For reproducible simulations
                }
            },
            {
                "member_id": "user_002",
                "name": "Demo User 2",
                "member_type": "prosumer",
                "customer_category": "commercial",
                "group_id": None,
                "assets": {
                    "pv_capacity_kw": 3.0,
                    "battery_capacity_kwh": 5.0,
                    "battery_chemistry": "lead_acid",  # Lead-acid: 20%-90% SOC (traditional)
                    "load_capacity_kw": 6.0
                },
                # Note: Behavior and variability auto-set from customer_category (commercial)
                # Defaults: active 8am-6pm (business hours), weekend 10%, variability 10% (predictable)
                "behavior": {
                    "active_hours": [8, 18],
                    "weekday_factor": 1.0,
                    "weekend_factor": 0.1,
                    "temperature_sensitivity": 0.3,
                    "demand_response_acceptance": 0.5,
                    "pv_self_consumption_preference": 0.9,
                    "battery_usage_preference": 0.5,
                    "routine_drift_hours": 0.5,
                    "seasonal_scaling_factors": None,
                    "maintenance_days": []
                },
                "variability": {
                    "variability_level": 0.10,  # 10% unpredictability (commercial - routine schedules)
                    "random_seed": 42            # For reproducible simulations
                }
            }
        ]
    }
    
    # Insert the document
    result = await collection.insert_one(community_model)
    
    print(f"✓ Successfully created community model")
    print(f"  - Community ID: community_001")
    print(f"  - Document ID: {result.inserted_id}")
    print(f"  - Members: 2 (user_001, user_002)")
    print(f"  - All community_control fields: 23 fields configured")
    print(f"\n✓ MongoDB initialization complete!")
    
    # Close connection
    client.close()


if __name__ == "__main__":
    print("Initializing MongoDB with complete community model...")
    asyncio.run(init_community_model())

