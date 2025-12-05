"""Check if member data exists in the cache"""
import asyncio
from app.services.infrastructure.background_service import get_background_service
from app.db.database import connect_to_mongo

async def check():
    try:
        await connect_to_mongo()
        print("✓ MongoDB connected\n")
        
        service = get_background_service()
        
        # Get today's data
        today_data = service.get_today_data()
        print(f"=== Today's Cache ===")
        print(f"Total entries: {len(today_data)}")
        
        if today_data:
            # Check first entry
            first_entry = today_data[0]
            print(f"\nFirst entry timestamp: {first_entry.get('timestamp')}")
            
            community_data = first_entry.get('data', {})
            print(f"Community data keys: {list(community_data.keys())}")
            
            # Check if members exist
            members = community_data.get('members', [])
            print(f"\nMembers in community data: {len(members)}")
            
            if members:
                member = members[0]
                print(f"\nFirst member:")
                print(f"  ID: {member.get('member_id')}")
                print(f"  Keys: {list(member.keys())}")
                print(f"  Solar: {member.get('solar_generation_kw')} kW")
                print(f"  Consumption: {member.get('consumption_kw')} kW")
            else:
                print("\n❌ NO MEMBER DATA IN CACHE!")
        
        # Now test get_hourly_history with member_id
        print(f"\n=== Member-Specific History (user_001) ===")
        member_history = service.get_hourly_history(member_id='user_001', hours=24)
        print(f"Member history entries: {len(member_history)}")
        
        if member_history:
            print(f"\nFirst 3 entries:")
            for i, entry in enumerate(member_history[:3]):
                data = entry.get('data', {})
                print(f"  {i+1}. {entry.get('timestamp')}: {data.get('consumption_kw')} kW consumed, {data.get('solar_generation_kw')} kW solar")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(check())

