#!/usr/bin/env python3
"""
Test script to analyze the demand data patterns
"""

import json
from datetime import datetime

def analyze_demand_data():
    """Analyze the demand data to show patterns"""
    
    # Load the data
    with open('artifacts/transformed_data.json', 'r') as f:
        data = json.load(f)
    
    demand_data = data.get('market_data', {}).get('demand_data', [])
    
    print(f"📊 DEMAND DATA ANALYSIS")
    print(f"=" * 50)
    print(f"Total records: {len(demand_data)}")
    
    # Analyze first few records
    print(f"\n🔍 FIRST 5 RECORDS:")
    for i, record in enumerate(demand_data[:5]):
        print(f"\nRecord {i+1}:")
        print(f"  Date: {record.get('date')}")
        print(f"  Hour: {record.get('hour')}")
        print(f"  Period: {record.get('period')}")
        print(f"  DateTime: {record.get('datetime')}")
        
        # Show regional values
        regions = ['Calabria', 'Sardegna', 'Sicilia', 'North', 'Central-northern Italy', 'Centeral-southern Italy', 'Southern-Italy']
        for region in regions:
            value = record.get(region)
            if value is not None and not (isinstance(value, float) and (value != value)):  # Not NaN
                print(f"  {region}: {value} MW")
    
    # Analyze by hour
    print(f"\n⏰ DEMAND BY HOUR:")
    hourly_demand = {}
    
    for record in demand_data:
        hour = record.get('hour')
        if hour not in hourly_demand:
            hourly_demand[hour] = []
        
        # Sum up regional demand
        total_demand = 0
        for region in regions:
            value = record.get(region)
            if value is not None and not (isinstance(value, float) and (value != value)):
                total_demand += float(value)
        
        if total_demand > 0:
            hourly_demand[hour].append(total_demand)
    
    # Calculate averages
    for hour in sorted(hourly_demand.keys()):
        if hourly_demand[hour]:
            avg_demand = sum(hourly_demand[hour]) / len(hourly_demand[hour])
            print(f"  Hour {hour:2d}: {avg_demand:8.2f} MW (avg)")
    
    # Show scaling examples
    print(f"\n🏠 SCALING EXAMPLES:")
    print(f"National demand at hour 12: {hourly_demand.get(12, [0])[0] if hourly_demand.get(12) else 0:.2f} MW")
    print(f"Household consumption (÷20M): {hourly_demand.get(12, [0])[0] * 1000 / 20000000 if hourly_demand.get(12) else 0:.4f} kW")
    print(f"Community consumption (÷8K): {hourly_demand.get(12, [0])[0] * 1000 / 8000 if hourly_demand.get(12) else 0:.2f} kW")

if __name__ == "__main__":
    analyze_demand_data()
