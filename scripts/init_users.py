"""
Initialize Users in MongoDB

Creates default users for testing:
- manager: Community manager with full access
- member1, member2, member3: Individual members
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.database import connect_to_mongo, close_mongo_connection
from app.services.auth.auth_service import get_auth_service


async def create_default_users():
    """Create default users for testing."""
    print("Initializing users in MongoDB...")
    
    try:
        # Connect to MongoDB
        await connect_to_mongo()
        print("Connected to MongoDB")
        
        auth_service = get_auth_service()
        
        # Load existing users
        await auth_service._load_users_from_db()
        
        # Create manager user
        if not await auth_service.get_user("manager"):
            await auth_service.create_user(
                user_id="manager",
                password="manager123",
                full_name="Community Manager",
                role="manager",
                member_id=None  # Manager can see all members
            )
            print("Created manager user (username: manager, password: manager123)")
        else:
            print("Manager user already exists")
        
        # Create member users (matching community_001 members)
        members = [
            ("user_001", "password", "Demo User 1", "user_001"),
            ("user_002", "password", "Demo User 2", "user_002"),
            ("user_003", "password", "Demo User 3 (Pure Consumer)", "user_003"),
        ]
        
        for username, password, full_name, member_id in members:
            if not await auth_service.get_user(username):
                await auth_service.create_user(
                    user_id=username,
                    password=password,
                    full_name=full_name,
                    role="member",
                    member_id=member_id
                )
                print(f"Created user: {username} (password: {password}, member_id: {member_id})")
            else:
                print(f"User {username} already exists")
        
        print("\nUsers initialized successfully!")
        print("\nTest Credentials:")
        print("  Manager: username='manager', password='manager123' (full community access)")
        print("  User 1: username='user_001', password='password' (member: user_001, prosumer)")
        print("  User 2: username='user_002', password='password' (member: user_002, prosumer)")
        print("  User 3: username='user_003', password='password' (member: user_003, pure consumer)")
        
    except Exception as e:
        print(f"Error initializing users: {e}")
        raise
    finally:
        await close_mongo_connection()
        print("\nMongoDB connection closed")


if __name__ == "__main__":
    asyncio.run(create_default_users())

