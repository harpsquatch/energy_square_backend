"""Quick script to check MongoDB setup"""
import asyncio
from app.db.database import connect_to_mongo, get_database, Collections

async def check():
    try:
        await connect_to_mongo()
        print("✓ MongoDB connected")
        
        db = await get_database()
        
        # Check community model
        col = db[Collections.COMMUNITY_MODELS]
        doc = await col.find_one({})
        if doc:
            print("✓ Community model found")
            community_id = doc.get('community', {}).get('community_id')
            members_count = len(doc.get('members', []))
            print(f"  Community ID: {community_id}")
            print(f"  Members: {members_count}")
        else:
            print("✗ NO COMMUNITY MODEL FOUND - Run: python scripts/init_mongodb_community.py")
        
        # Check users
        users_col = db[Collections.USERS]
        users_count = await users_col.count_documents({})
        if users_count > 0:
            print(f"✓ {users_count} users found")
            cursor = users_col.find({})
            async for user in cursor:
                print(f"  - {user.get('user_id')} ({user.get('role')})")
        else:
            print("✗ NO USERS FOUND - Run: python scripts/init_users.py")
            
    except Exception as e:
        print(f"✗ Error: {e}")

asyncio.run(check())

