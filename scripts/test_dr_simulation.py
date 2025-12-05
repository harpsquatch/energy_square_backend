"""
Test DR with Actual Simulation - Show consumption before and after DR
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db.database import connect_to_mongo, close_mongo_connection
from app.services.infrastructure.demand_response_service import get_demand_response_service
from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine

async def test_dr_simulation():
    print("\n" + "="*80)
    print("DR SIMULATION TEST - Consumption Before/After")
    print("="*80)
    
    await connect_to_mongo()
    
    # Get current time
    current_time = datetime.now(ZoneInfo("Asia/Kolkata"))
    current_hour = current_time.replace(minute=0, second=0, microsecond=0)
    print(f"\n[SETUP] Current time: {current_time}")
    print(f"[SETUP] Simulating hour: {current_hour}")
    
    # Initialize services
    print("\n[SETUP] Initializing services...")
    model_service = CommunityModelService()
    simulation_engine = CommunitySimulationEngine(model_service)
    dr_service = get_demand_response_service()
    
    # Load DR events
    print("\n[SETUP] Loading DR events...")
    await dr_service._load_events_from_db()
    print(f"✓ Loaded {len(dr_service._events)} events")
    
    # Check user_001 DR status
    print("\n[STEP 1] Checking user_001 DR status...")
    reduction_pct = dr_service.get_member_reduction("user_001", current_hour)
    print(f"  DR Reduction: {reduction_pct * 100}%")
    
    # Get model
    model = model_service.get_model()
    if not model:
        print("✗ Model not loaded!")
        await close_mongo_connection()
        return
    
    # Find user_001 member
    user_001 = None
    for member in model.members:
        if member.member_id == "user_001":
            user_001 = member
            break
    
    if not user_001:
        print("✗ user_001 not found in model!")
        await close_mongo_connection()
        return
    
    print(f"✓ Found user_001: {user_001.member_id}")
    
    # Simulate WITHOUT DR
    print("\n[STEP 2] Simulating user_001 WITHOUT DR reduction...")
    result_no_dr = simulation_engine.simulate_member(user_001, current_hour, apply_demand_response=False)
    consumption_no_dr = result_no_dr.get('consumption_kw', 0)
    print(f"  Consumption WITHOUT DR: {consumption_no_dr:.2f} kW")
    
    # Simulate WITH DR
    print("\n[STEP 3] Simulating user_001 WITH DR reduction...")
    result_with_dr = simulation_engine.simulate_member(user_001, current_hour, apply_demand_response=True)
    consumption_with_dr = result_with_dr.get('consumption_kw', 0)
    print(f"  Consumption WITH DR: {consumption_with_dr:.2f} kW")
    
    # Calculate difference
    print("\n[STEP 4] Results:")
    print(f"  Before DR: {consumption_no_dr:.2f} kW")
    print(f"  After DR:  {consumption_with_dr:.2f} kW")
    if consumption_no_dr > 0:
        actual_reduction = ((consumption_no_dr - consumption_with_dr) / consumption_no_dr) * 100
        print(f"  Actual Reduction: {actual_reduction:.1f}%")
        print(f"  Expected Reduction: {reduction_pct * 100:.1f}%")
        print(f"  Difference: {consumption_no_dr - consumption_with_dr:.2f} kW")
    
    # Full community simulation
    print("\n[STEP 5] Running full community simulation WITH DR...")
    community_result = simulation_engine.simulate_community(current_hour, apply_demand_response=True)
    
    # Find user_001 in community results
    members_data = community_result.get('members', [])
    for member_data in members_data:
        if member_data.get('member_id') == 'user_001':
            print(f"  user_001 consumption from community sim: {member_data.get('consumption_kw', 0):.2f} kW")
            break
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(test_dr_simulation())

