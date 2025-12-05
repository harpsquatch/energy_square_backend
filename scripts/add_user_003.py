"""
Add user_003 as a pure consumer (no PV generation) to the community model.
This user will only consume energy and import from grid or buy via P2P.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.db.database import Collections


async def add_user_003():
    """Add user_003 as a pure consumer to the community model."""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.DATABASE_NAME]
    collection = db[Collections.COMMUNITY_MODELS]
    
    # Find the community model
    community_id = "community_001"
    doc = await collection.find_one({"community.community_id": community_id})
    
    if not doc:
        print(f"✗ Community model '{community_id}' not found in MongoDB")
        print("  Run: python scripts/init_mongodb_community.py first")
        client.close()
        return
    
    print(f"✓ Found community model: {community_id}")
    
    # Check if user_003 already exists
    existing_members = doc.get('members', [])
    for member in existing_members:
        if member.get('member_id') == 'user_003':
            print(f"✗ user_003 already exists in the community model")
            client.close()
            return
    
    # Create user_003 as a pure consumer (no PV, no battery, just consumption)
    user_003 = {
        "member_id": "user_003",
        "member_type": "consumer",  # Pure consumer, no generation
        "customer_category": "residential",
        "group_id": None,
        "assets": {
            "pv_capacity_kw": 0.0,  # No solar panels
            "battery_capacity_kwh": 0.0,  # No battery storage
            "battery_chemistry": "lithium_ion",
            "load_capacity_kw": 10.0,  # Higher consumption (pure consumer)
            "grid_import_limit_kw": 1000.0,
            "grid_export_limit_kw": 0.0  # Cannot export (no generation)
        },
        "behavior": {
            "active_hours": [6, 22],
            "weekday_factor": 1.0,
            "weekend_factor": 0.85,
            "temperature_sensitivity": 0.5,
            "demand_response_acceptance": 0.7,
            "pv_self_consumption_preference": 0.0,  # Not applicable (no PV)
            "battery_usage_preference": 0.0,  # Not applicable (no battery)
            "routine_drift_hours": 1.0,
            "seasonal_scaling_factors": None,
            "maintenance_days": []
        },
        "variability": {
            "variability_level": 0.15,  # 15% unpredictability (residential)
            "random_seed": 43  # Different seed from user_001
        }
    }
    
    # Add user_003 to members list
    doc['members'].append(user_003)
    
    # Update MongoDB
    result = await collection.update_one(
        {"community.community_id": community_id},
        {"$set": {"members": doc['members']}}
    )
    
    if result.modified_count > 0:
        print(f"\n✓ Successfully added user_003:")
        print(f"  - Type: Pure Consumer (no PV, no battery)")
        print(f"  - Load Capacity: 10.0 kW")
        print(f"  - PV Capacity: 0.0 kW (no generation)")
        print(f"  - Battery Capacity: 0.0 kWh (no storage)")
        print(f"  - Will import from grid or buy via P2P")
    else:
        print("✗ No changes made (document may not have been updated)")
    
    print(f"\n✓ MongoDB update complete!")
    print(f"  Note: The backend will reload the model automatically on next simulation cycle")
    print(f"  Or restart the backend to pick up changes immediately")
    
    # Close connection
    client.close()


if __name__ == "__main__":
    print("Adding user_003 (pure consumer) to community model...")
    print("=" * 60)
    asyncio.run(add_user_003())


