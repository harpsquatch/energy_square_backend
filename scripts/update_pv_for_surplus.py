"""
Update MongoDB community model to increase PV capacities for surplus generation.
This script increases PV capacity for all members to ensure generation > consumption.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.db.database import Collections


async def update_pv_capacities():
    """Update PV capacities in MongoDB to create surplus generation."""
    
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
    print(f"  Current members: {len(doc.get('members', []))}")
    
    # Update PV capacities for each member
    # Strategy: Set PV capacity to 2x load capacity to ensure surplus
    updates = []
    for i, member in enumerate(doc.get('members', [])):
        member_id = member.get('member_id')
        current_pv = member.get('assets', {}).get('pv_capacity_kw', 0)
        current_load = member.get('assets', {}).get('load_capacity_kw', 0)
        
        # Set PV to 2.5x load capacity to ensure significant surplus
        new_pv = current_load * 2.5
        
        updates.append({
            'member_id': member_id,
            'old_pv': current_pv,
            'new_pv': new_pv,
            'load': current_load
        })
        
        # Update in document
        doc['members'][i]['assets']['pv_capacity_kw'] = new_pv
    
    # Update MongoDB
    result = await collection.update_one(
        {"community.community_id": community_id},
        {"$set": {"members": doc['members']}}
    )
    
    if result.modified_count > 0:
        print(f"\n✓ Successfully updated PV capacities:")
        for update in updates:
            print(f"  - {update['member_id']}:")
            print(f"    PV: {update['old_pv']:.1f} kW → {update['new_pv']:.1f} kW")
            print(f"    Load: {update['load']:.1f} kW")
            print(f"    Expected surplus: ~{update['new_pv'] - update['load']:.1f} kW (during peak generation)")
    else:
        print("✗ No changes made (document may not have been updated)")
    
    print(f"\n✓ MongoDB update complete!")
    print(f"  Note: The backend will reload the model automatically on next simulation cycle")
    print(f"  Or restart the backend to pick up changes immediately")
    
    # Close connection
    client.close()


if __name__ == "__main__":
    print("Updating PV capacities in MongoDB to create surplus generation...")
    print("=" * 60)
    asyncio.run(update_pv_capacities())

