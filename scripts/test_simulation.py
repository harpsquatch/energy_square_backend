"""Test if simulation is working"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine
from app.db.database import connect_to_mongo

async def test():
    try:
        # Connect to MongoDB
        await connect_to_mongo()
        print("✓ MongoDB connected")
        
        # Load model
        model_service = CommunityModelService()
        model = model_service.get_model()
        
        if not model:
            print("✗ Failed to load model")
            return
            
        print(f"✓ Model loaded: {model.community.community_id}")
        print(f"  Members: {len(model.members)}")
        for m in model.members:
            print(f"    - {m.member_id}: {m.assets.pv_capacity_kw}kW PV, {m.assets.battery_capacity_kwh}kWh battery")
        
        # Test simulation
        print("\n  Running simulation...")
        engine = CommunitySimulationEngine(model_service=model_service)
        now = datetime.now(ZoneInfo(model.community.timezone))
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        result = engine.simulate_community(current_hour)
        
        print(f"\n✓ Simulation successful!")
        print(f"  Timestamp: {result.get('timestamp')}")
        print(f"  Total Generation: {result.get('total_generation_kw', 0):.2f} kW")
        print(f"  Total Consumption: {result.get('total_consumption_kw', 0):.2f} kW")
        print(f"  Net Balance: {result.get('net_balance_kw', 0):.2f} kW")
        print(f"  Members simulated: {len(result.get('members', []))}")
        
        # Show first member details
        if result.get('members'):
            member = result['members'][0]
            print(f"\n  Sample Member ({member.get('member_id')}):")
            print(f"    Solar: {member.get('solar_generation_kw', 0):.2f} kW")
            print(f"    Consumption: {member.get('consumption_kw', 0):.2f} kW")
            print(f"    Battery SOC: {member.get('battery_soc_pct', 0):.1f}%")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())

