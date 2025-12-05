"""
Test DR Service - Check if user_001 should have reduction RIGHT NOW
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db.database import get_database, Collections, connect_to_mongo, close_mongo_connection
from app.services.infrastructure.demand_response_service import DemandResponseService

async def test_dr():
    await connect_to_mongo()
    
    dr_service = DemandResponseService()
    
    # Load events from DB
    await dr_service._load_events_from_db()
    
    # Get current time
    current_time = datetime.now(ZoneInfo("Asia/Kolkata"))  # Your timezone
    
    print(f"\n=== DR Debug Info ===")
    print(f"Current Time: {current_time}")
    print(f"Total Events Loaded: {len(dr_service._events)}")
    
    # Check all events
    for event_id, event in dr_service._events.items():
        print(f"\n--- Event: {event.event_id} ---")
        print(f"Title: {event.title}")
        print(f"Start: {event.start_time} (tzinfo: {event.start_time.tzinfo})")
        print(f"End: {event.end_time} (tzinfo: {event.end_time.tzinfo})")
        print(f"Is Active? {event.is_active(current_time)}")
        print(f"Participants: {event.participants}")
        print(f"Target Reduction: {event.target_reduction_pct * 100}%")
    
    # Check active events
    active_events = dr_service.get_active_events(current_time)
    print(f"\n=== Active Events: {len(active_events)} ===")
    
    # Check user_001 reduction
    reduction = dr_service.get_member_reduction("user_001", current_time)
    print(f"\n=== user_001 Reduction ===")
    print(f"Current Reduction: {reduction * 100}%")
    
    if reduction == 0:
        print("\n❌ NO REDUCTION ACTIVE!")
        print("Possible reasons:")
        print("1. Event not active for current time")
        print("2. user_001 not in participants")
        print("3. Timezone mismatch")
    else:
        print(f"\n✅ REDUCTION ACTIVE: {reduction * 100}%")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(test_dr())

