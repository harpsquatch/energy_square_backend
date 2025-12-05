"""
Complete DR System Test - Test the entire flow step by step
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db.database import connect_to_mongo, close_mongo_connection
from app.services.infrastructure.demand_response_service import get_demand_response_service

async def test_complete_dr_flow():
    print("\n" + "="*80)
    print("COMPLETE DR SYSTEM TEST")
    print("="*80)
    
    # Step 1: Connect to MongoDB
    print("\n[STEP 1] Connecting to MongoDB...")
    await connect_to_mongo()
    print("✓ Connected")
    
    # Step 2: Get DR service instance (first call)
    print("\n[STEP 2] Getting DR service instance (1st call)...")
    dr_service_1 = get_demand_response_service()
    print(f"✓ Got instance: {id(dr_service_1)}")
    print(f"  Events loaded: {len(dr_service_1._events)}")
    print(f"  MongoDB available: {dr_service_1._mongodb_available}")
    
    # Step 3: Load events explicitly
    print("\n[STEP 3] Loading events from MongoDB...")
    await dr_service_1._load_events_from_db()
    print(f"✓ Events after load: {len(dr_service_1._events)}")
    for event_id, event in dr_service_1._events.items():
        print(f"  - {event_id}: {event.title}, Participants: {list(event.participants.keys())}")
    
    # Step 4: Get DR service instance again (should be same singleton)
    print("\n[STEP 4] Getting DR service instance (2nd call)...")
    dr_service_2 = get_demand_response_service()
    print(f"✓ Got instance: {id(dr_service_2)}")
    print(f"  Is same instance? {dr_service_1 is dr_service_2}")
    print(f"  Events loaded: {len(dr_service_2._events)}")
    
    # Step 5: Opt-in user_001
    print("\n[STEP 5] Opting in user_001 to event dr_57437d18...")
    success = dr_service_2.opt_in("user_001", "dr_57437d18")
    print(f"✓ Opt-in success: {success}")
    
    # Step 6: Check event participants after opt-in
    print("\n[STEP 6] Checking event participants after opt-in...")
    event = dr_service_2._events.get("dr_57437d18")
    if event:
        print(f"✓ Event found: {event.title}")
        print(f"  Participants: {event.participants}")
    else:
        print("✗ Event not found!")
    
    # Step 7: Get member reduction (current time)
    print("\n[STEP 7] Getting reduction for user_001 at current time...")
    current_time = datetime.now(ZoneInfo("Asia/Kolkata"))
    reduction = dr_service_2.get_member_reduction("user_001", current_time)
    print(f"  Current time: {current_time}")
    print(f"  Reduction: {reduction * 100}%")
    
    # Step 8: Get active events
    print("\n[STEP 8] Getting active events...")
    active_events = dr_service_2.get_active_events(current_time)
    print(f"✓ Active events: {len(active_events)}")
    for event in active_events:
        print(f"  - {event.event_id}: {event.title}")
        print(f"    Active? {event.is_active(current_time)}")
        print(f"    Participants: {event.participants}")
    
    # Step 9: Simulate calling get_demand_response_service() from simulation
    print("\n[STEP 9] Simulating call from simulation engine...")
    dr_service_3 = get_demand_response_service()
    print(f"✓ Got instance: {id(dr_service_3)}")
    print(f"  Is same instance? {dr_service_3 is dr_service_2}")
    print(f"  Events loaded: {len(dr_service_3._events)}")
    
    # Step 10: Get member reduction from "simulation" instance
    print("\n[STEP 10] Getting reduction from 'simulation' instance...")
    reduction_sim = dr_service_3.get_member_reduction("user_001", current_time)
    print(f"  Reduction: {reduction_sim * 100}%")
    
    # Step 11: Check event details
    print("\n[STEP 11] Checking event dr_57437d18 details...")
    event_check = dr_service_3._events.get("dr_57437d18")
    if event_check:
        print(f"✓ Event found")
        print(f"  Title: {event_check.title}")
        print(f"  Start: {event_check.start_time}")
        print(f"  End: {event_check.end_time}")
        print(f"  Is active now? {event_check.is_active(current_time)}")
        print(f"  Participants: {event_check.participants}")
        print(f"  user_001 in participants? {'user_001' in event_check.participants}")
    else:
        print("✗ Event not found!")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(test_complete_dr_flow())

