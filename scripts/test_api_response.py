"""Test what the API is returning for user dashboard"""
import requests
import json

try:
    response = requests.get("http://localhost:8000/api/user/user-dashboard?user_id=user_001")
    
    if response.status_code == 200:
        data = response.json()
        
        print("=== User Dashboard API Response ===")
        print(f"Status: {response.status_code}")
        print(f"\nDaily Totals:")
        print(f"  produced_kwh_today: {data.get('produced_kwh_today', 'N/A')}")
        print(f"  consumed_kwh_today: {data.get('consumed_kwh_today', 'N/A')}")
        print(f"  net_kwh_today: {data.get('net_kwh_today', 'N/A')}")
        
        print(f"\nCurrent Values:")
        print(f"  current_generation_kw: {data.get('current_generation_kw', 'N/A')}")
        print(f"  current_consumption_kw: {data.get('current_consumption_kw', 'N/A')}")
        print(f"  current_net_balance_kw: {data.get('current_net_balance_kw', 'N/A')}")
        
        print(f"\nBattery:")
        print(f"  battery_soc_pct: {data.get('battery_soc_pct', 'N/A')}")
        print(f"  battery_capacity_kwh: {data.get('battery_capacity_kwh', 'N/A')}")
        
        print(f"\nOther:")
        print(f"  solar_capacity_kw: {data.get('solar_capacity_kw', 'N/A')}")
        print(f"  location: {data.get('location', 'N/A')}")
        
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

