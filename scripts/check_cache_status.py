"""Check the status of the background simulation cache"""
import asyncio
from app.services.infrastructure.background_service import get_background_service
from app.db.database import connect_to_mongo

async def check():
    try:
        await connect_to_mongo()
        print("✓ MongoDB connected\n")
        
        service = get_background_service()
        
        # Get cache status
        status = service.get_cache_status()
        
        print("=== Background Service Status ===")
        print(f"Running: {status['running']}")
        print(f"Current timestamp: {status['current_timestamp']}")
        print(f"Has current data: {status['has_current_data']}")
        print(f"Update interval: {status['update_interval_seconds']}s")
        
        print(f"\n=== Cache Structure ===")
        print(f"Today count: {status['cache_structure']['today_count']} hours")
        print(f"Week count: {status['cache_structure']['week_count']} hours")
        print(f"Month count: {status['cache_structure']['month_count']} hours")
        
        # Get today's data
        today_data = service.get_today_data()
        print(f"\n=== Today's Data ===")
        print(f"Total entries: {len(today_data)}")
        if today_data:
            print(f"First entry timestamp: {today_data[0].get('timestamp')}")
            print(f"Last entry timestamp: {today_data[-1].get('timestamp')}")
            
            # Check if member data exists
            first_entry_data = today_data[0].get('data', {})
            members = first_entry_data.get('members', [])
            print(f"Members in each entry: {len(members)}")
            if members:
                print(f"Sample member IDs: {[m.get('member_id') for m in members]}")
        
        # Try to get member-specific history
        print(f"\n=== Member-Specific History (user_001) ===")
        member_history = service.get_hourly_history(member_id='user_001', hours=24)
        print(f"Member history entries: {len(member_history)}")
        if member_history:
            print(f"First entry: {member_history[0].get('timestamp')}")
            member_data = member_history[0].get('data', {})
            print(f"Sample data keys: {list(member_data.keys())[:10]}")
            print(f"Solar generation: {member_data.get('solar_generation_kw')} kW")
            print(f"Consumption: {member_data.get('consumption_kw')} kW")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(check())

