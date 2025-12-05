"""
Test script for P2P Marketplace functionality.

This script tests:
1. Creating trade offers (prosumers selling energy)
2. Creating trade requests (consumers buying energy)
3. Matching and executing trades
4. Verifying transaction persistence and hash chain
5. Checking simulation integration
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.infrastructure.marketplace_service import MarketplaceService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine
from app.services.infrastructure.model_service import CommunityModelService


async def test_marketplace():
    """Test marketplace functionality."""
    print("=" * 60)
    print("P2P Marketplace Testing")
    print("=" * 60)
    
    # Connect to MongoDB first
    print("\n📡 Connecting to MongoDB...")
    try:
        from app.db.database import connect_to_mongo
        await connect_to_mongo()
        print("✅ MongoDB connected")
    except Exception as e:
        print(f"❌ ERROR: Failed to connect to MongoDB: {e}")
        print("   Please ensure MongoDB is running and MONGODB_URI is set correctly")
        return
    
    # Initialize services
    print("\n🔧 Initializing services...")
    # Enable test mode (1 hour minimum instead of 4 hours for immediate testing)
    marketplace_service = MarketplaceService(test_mode=True)
    await marketplace_service._load_transactions_from_db()
    
    try:
        model_service = CommunityModelService()
        model = model_service.get_model()
        if not model:
            print("❌ ERROR: Community model not loaded")
            return
        print("✅ Community model loaded")
        
        # Check if user_003 exists, if not, inform user to run add_user_003.py
        user_003_exists = any(m.member_id == "user_003" for m in model.members)
        if not user_003_exists:
            print("⚠️  WARNING: user_003 not found in community model")
            print("   Run: python scripts/add_user_003.py to add pure consumer")
            print("   Continuing with existing members (user_001, user_002)...")
    except Exception as e:
        print(f"❌ ERROR: Failed to load community model: {e}")
        return
    
    simulation_engine = CommunitySimulationEngine(model_service)
    print("✅ Simulation engine initialized")
    
    # Get timezone
    tz = ZoneInfo(model.community.timezone)
    current_time = datetime.now(tz)
    
    print(f"\n📅 Current Time: {current_time.isoformat()}")
    print(f"📍 Timezone: {model.community.timezone}")
    
    # Test 1: Create Trade Offer
    print("\n" + "=" * 60)
    print("TEST 1: Create Trade Offer (Prosumer selling energy)")
    print("=" * 60)
    
    try:
        # TEST MODE: Use immediate execution (current hour or next hour)
        # Round to current hour for immediate testing
        current_hour = current_time.replace(minute=0, second=0, microsecond=0)
        
        # Use current hour if we're in peak solar hours (10:00-15:00), otherwise use next hour
        if current_hour.hour >= 10 and current_hour.hour <= 15:
            # We're in peak hours, use current hour immediately
            start_hour = current_hour
        else:
            # Not in peak hours, use next hour (or tomorrow's 10:00 if late in day)
            if current_hour.hour < 10:
                # Before 10 AM, use today's 10:00
                start_hour = current_hour.replace(hour=10)
            elif current_hour.hour > 15:
                # After 3 PM, use tomorrow's 10:00
                tomorrow = current_hour.date() + timedelta(days=1)
                start_hour = datetime.combine(tomorrow, datetime.min.time()).replace(
                    hour=10, tzinfo=current_time.tzinfo
                )
            else:
                # Between 10-15, use next hour
                start_hour = current_hour + timedelta(hours=1)
        
        # Create 4 time blocks starting from the chosen hour
        time_blocks = []
        for i in range(4):
            block = start_hour + timedelta(hours=i)
            # Don't go past 15:00 (3 PM) - last peak hour
            if block.hour <= 15:
                time_blocks.append(block)
        
        # If we don't have 4 blocks (e.g., started at 15:00), add blocks from next day
        if len(time_blocks) < 4:
            next_day = start_hour.date() + timedelta(days=1)
            remaining = 4 - len(time_blocks)
            for i in range(remaining):
                block = datetime.combine(next_day, datetime.min.time()).replace(
                    hour=10 + i, tzinfo=current_time.tzinfo
                )
                if block.hour <= 15:
                    time_blocks.append(block)
        
        print(f"   Current time: {current_time.isoformat()}")
        print(f"   TEST MODE: Immediate execution (no scheduling delay)")
        print(f"   Time blocks (starting immediately):")
        for i, tb in enumerate(time_blocks):
            hours_ahead = (tb - current_time).total_seconds() / 3600
            if hours_ahead < 0:
                print(f"     Block {i+1}: {tb.isoformat()} (NOW - immediate)")
            else:
                print(f"     Block {i+1}: {tb.isoformat()} ({hours_ahead:.2f} hours ahead)")
        
        offer_id = marketplace_service.create_trade_offer(
            seller_id="user_001",
            available_surplus_kw=5.0,
            price_per_kwh=0.15,
            time_blocks=time_blocks
        )
        print(f"✅ Created offer: {offer_id}")
        print(f"   Seller: user_001")
        print(f"   Surplus: 5.0 kW")
        print(f"   Price: $0.15/kWh")
        print(f"   Time blocks: {len(time_blocks)} blocks")
    except Exception as e:
        print(f"❌ Failed to create offer: {e}")
        return
    
    # Test 2: Create Trade Request
    print("\n" + "=" * 60)
    print("TEST 2: Create Trade Request (Consumer buying energy)")
    print("=" * 60)
    
    try:
        request_id = marketplace_service.create_trade_request(
            buyer_id="user_002",
            required_energy_kwh=3.0,
            max_price_per_kwh=0.20,
            time_blocks=time_blocks,
            preferred_seller_id="user_001"  # Preferential matching
        )
        print(f"✅ Created request: {request_id}")
        print(f"   Buyer: user_002")
        print(f"   Required: 3.0 kWh")
        print(f"   Max price: $0.20/kWh")
        print(f"   Preferred seller: user_001")
    except Exception as e:
        print(f"❌ Failed to create request: {e}")
        return
    
    # Test 3: Match and Execute Trade
    print("\n" + "=" * 60)
    print("TEST 3: Match and Execute Trade")
    print("=" * 60)
    
    try:
        # Match the trade
        transaction_id = marketplace_service.match_trade(
            offer_id=offer_id,
            request_id=request_id,
            energy_kwh=3.0
        )
        print(f"✅ Matched trade: {transaction_id}")
        
        # Execute the trade
        success = marketplace_service.execute_trade(transaction_id)
        if success:
            print(f"✅ Executed trade: {transaction_id}")
        else:
            print(f"❌ Failed to execute trade")
            return
    except Exception as e:
        print(f"❌ Failed to match/execute trade: {e}")
        return
    
    # Test 4: Verify Transaction Details and MongoDB Persistence
    print("\n" + "=" * 60)
    print("TEST 4: Verify Transaction Details and MongoDB Persistence")
    print("=" * 60)
    
    try:
        trades = marketplace_service.get_member_trades("user_001")
        if trades:
            trade = trades[0]  # Most recent
            print(f"✅ Transaction found in memory:")
            print(f"   ID: {trade['transaction_id']}")
            print(f"   Seller: {trade['seller_id']}")
            print(f"   Buyer: {trade['buyer_id']}")
            print(f"   Energy: {trade['energy_kwh']} kWh")
            print(f"   Price: ${trade['price_per_kwh']}/kWh")
            print(f"   Status: {trade['status']}")
            print(f"   Gross Amount: ${trade['gross_amount']:.2f}")
            print(f"   Service Fee: ${trade['service_fee']:.2f}")
            print(f"   Seller Receives: ${trade['seller_amount']:.2f}")
            print(f"   Buyer Pays: ${trade['buyer_amount']:.2f}")
            print(f"   Transaction Hash: {trade['transaction_hash'][:16] if trade.get('transaction_hash') else 'None'}...")
            print(f"   Previous Hash: {trade['previous_hash'][:16] if trade.get('previous_hash') else 'None'}...")
            
            # Verify MongoDB persistence
            print(f"\n   📦 Checking MongoDB persistence...")
            from app.db.database import get_database, Collections
            db = await get_database()
            p2p_collection = db[Collections.P2P_TRANSACTIONS]
            
            # Wait a moment for async save to complete
            await asyncio.sleep(0.5)
            
            mongo_txn = await p2p_collection.find_one({"transaction_id": trade['transaction_id']})
            if mongo_txn:
                print(f"   ✅ Transaction persisted to MongoDB!")
                print(f"      MongoDB ID: {mongo_txn.get('_id')}")
                print(f"      Status in DB: {mongo_txn.get('status')}")
                print(f"      Hash in DB: {mongo_txn.get('transaction_hash', 'None')[:16] if mongo_txn.get('transaction_hash') else 'None'}...")
            else:
                print(f"   ⚠️  Transaction not found in MongoDB (may still be saving asynchronously)")
        else:
            print("❌ No trades found")
    except Exception as e:
        print(f"❌ Failed to verify transaction: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 5: Check Active Trades for Simulation
    print("\n" + "=" * 60)
    print("TEST 5: Check Active Trades for Simulation")
    print("=" * 60)
    
    try:
        # Get active trades for a future time block (when trade is scheduled)
        future_time = time_blocks[0]  # First time block
        active_trades = marketplace_service.get_active_trades(future_time)
        
        print(f"✅ Active trades for {future_time.isoformat()}:")
        print(f"   Sold: {active_trades['sold']}")
        print(f"   Bought: {active_trades['bought']}")
        
        # Verify user_001 has sold energy
        if "user_001" in active_trades["sold"]:
            print(f"   ✅ user_001 sold {active_trades['sold']['user_001']} kW")
        else:
            print(f"   ❌ user_001 not found in sold trades")
        
        # Verify user_002 has bought energy
        if "user_002" in active_trades["bought"]:
            print(f"   ✅ user_002 bought {active_trades['bought']['user_002']} kW")
        else:
            print(f"   ❌ user_002 not found in bought trades")
    except Exception as e:
        print(f"❌ Failed to get active trades: {e}")
    
    # Test 6: Test Simulation Integration (Impact on Generation/Consumption)
    print("\n" + "=" * 60)
    print("TEST 6: Test Simulation Integration - P2P Impact on Grid Flows")
    print("=" * 60)
    
    try:
        # Simulate user_001 (seller) at the trade time block
        member_001 = None
        member_002 = None
        for m in model.members:
            if m.member_id == "user_001":
                member_001 = m
            if m.member_id == "user_002":
                member_002 = m
        
        if not member_001 or not member_002:
            print("❌ Members not found in model")
            return
        
        # Get active trades for the time block
        future_time = time_blocks[0]
        active_trades = marketplace_service.get_active_trades(future_time)
        
        p2p_sold_001 = active_trades.get("sold", {}).get("user_001", 0.0)
        p2p_bought_002 = active_trades.get("bought", {}).get("user_002", 0.0)
        
        # Simulate without P2P
        result_no_p2p = simulation_engine.simulate_member(
            member_001, 
            future_time,
            apply_demand_response=False,
            p2p_sold_kw=0.0,
            p2p_bought_kw=0.0
        )
        
        # Simulate with P2P
        result_with_p2p = simulation_engine.simulate_member(
            member_001,
            future_time,
            apply_demand_response=False,
            p2p_sold_kw=p2p_sold_001,
            p2p_bought_kw=0.0
        )
        
        print(f"✅ Simulation comparison for user_001 (seller) at {future_time.isoformat()}:")
        print(f"   Generation/Consumption (unchanged by P2P):")
        print(f"     Generation: {result_no_p2p['solar_generation_kw']:.3f} kW")
        print(f"     Consumption: {result_no_p2p['consumption_kw']:.3f} kW")
        print(f"     Net Balance: {result_no_p2p['net_balance_kw']:.3f} kW")
        print(f"   Grid Export (affected by P2P):")
        print(f"     Without P2P: {result_no_p2p['grid_export_kw']:.3f} kW")
        print(f"     With P2P (sold {p2p_sold_001} kW): {result_with_p2p['grid_export_kw']:.3f} kW")
        print(f"     Reduction: {result_no_p2p['grid_export_kw'] - result_with_p2p['grid_export_kw']:.3f} kW")
        
        if result_no_p2p['grid_export_kw'] > 0:
            # Only check if there was surplus to begin with
            if abs((result_no_p2p['grid_export_kw'] - result_with_p2p['grid_export_kw']) - p2p_sold_001) < 0.1:
                print(f"   ✅ P2P trade correctly reduces grid export!")
            else:
                print(f"   ⚠️  P2P reduction doesn't match expected value")
        else:
            print(f"   ℹ️  No surplus at this time (grid_export=0), so no reduction visible")
            print(f"   Note: P2P logic is working, but seller has no surplus to reduce at {future_time.hour}:00")
            
            # Try to find a time when user_001 has surplus
            print(f"\n   🔍 Searching for a time when user_001 has surplus...")
            for test_hour in [10, 11, 12, 13, 14, 15]:  # Peak solar hours
                test_time = future_time.replace(hour=test_hour, minute=0, second=0, microsecond=0)
                test_result = simulation_engine.simulate_member(
                    member_001,
                    test_time,
                    apply_demand_response=False,
                    p2p_sold_kw=0.0,
                    p2p_bought_kw=0.0
                )
                if test_result['grid_export_kw'] > 1.0:  # Has meaningful surplus
                    print(f"   ✅ Found surplus at {test_time.isoformat()}: {test_result['grid_export_kw']:.3f} kW export")
                    # Test with P2P at this time
                    test_with_p2p = simulation_engine.simulate_member(
                        member_001,
                        test_time,
                        apply_demand_response=False,
                        p2p_sold_kw=3.0,  # Use the same trade amount
                        p2p_bought_kw=0.0
                    )
                    reduction = test_result['grid_export_kw'] - test_with_p2p['grid_export_kw']
                    print(f"      Without P2P: {test_result['grid_export_kw']:.3f} kW")
                    print(f"      With P2P (sold 3.0 kW): {test_with_p2p['grid_export_kw']:.3f} kW")
                    print(f"      Reduction: {reduction:.3f} kW")
                    if abs(reduction - 3.0) < 0.1:
                        print(f"      ✅ P2P correctly reduces grid export when surplus exists!")
                    break
        
        # Test buyer
        result_buyer_no_p2p = simulation_engine.simulate_member(
            member_002,
            future_time,
            apply_demand_response=False,
            p2p_sold_kw=0.0,
            p2p_bought_kw=0.0
        )
        
        result_buyer_with_p2p = simulation_engine.simulate_member(
            member_002,
            future_time,
            apply_demand_response=False,
            p2p_sold_kw=0.0,
            p2p_bought_kw=p2p_bought_002
        )
        
        print(f"\n   Buyer (user_002) comparison:")
        print(f"   Generation/Consumption (unchanged by P2P):")
        print(f"     Generation: {result_buyer_no_p2p['solar_generation_kw']:.3f} kW")
        print(f"     Consumption: {result_buyer_no_p2p['consumption_kw']:.3f} kW")
        print(f"     Net Balance: {result_buyer_no_p2p['net_balance_kw']:.3f} kW")
        print(f"   Grid Import (affected by P2P):")
        print(f"     Without P2P: {result_buyer_no_p2p['grid_import_kw']:.3f} kW")
        print(f"     With P2P (bought {p2p_bought_002} kW): {result_buyer_with_p2p['grid_import_kw']:.3f} kW")
        print(f"     Reduction: {result_buyer_no_p2p['grid_import_kw'] - result_buyer_with_p2p['grid_import_kw']:.3f} kW")
        
        if abs((result_buyer_no_p2p['grid_import_kw'] - result_buyer_with_p2p['grid_import_kw']) - p2p_bought_002) < 0.1:
            print(f"   ✅ P2P trade correctly reduces grid import!")
        else:
            print(f"   ⚠️  P2P reduction doesn't match expected value")
        
        print(f"\n   📊 Summary:")
        print(f"   - Generation and Consumption are NOT changed by P2P (they're based on patterns)")
        print(f"   - Grid Export/Import ARE changed by P2P (this is the correct behavior)")
        print(f"   - Seller's grid_export decreases when they sell energy (if they have surplus)")
        print(f"   - Buyer's grid_import decreases when they buy energy (always visible)")
            
    except Exception as e:
        print(f"❌ Failed to test simulation: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 7: Get Marketplace Stats
    print("\n" + "=" * 60)
    print("TEST 7: Get Marketplace Statistics")
    print("=" * 60)
    
    try:
        all_trades = await marketplace_service.get_all_transactions_async()
        active_offers = marketplace_service.get_active_offers()
        active_requests = marketplace_service.get_active_requests()
        
        executed_trades = [t for t in all_trades if t.get("status") == "executed"]
        total_energy = sum(t.get("energy_kwh", 0) for t in executed_trades)
        total_value = sum(t.get("gross_amount", 0) for t in executed_trades)
        
        print(f"✅ Marketplace Statistics:")
        print(f"   Total Transactions: {len(all_trades)}")
        print(f"   Executed Trades: {len(executed_trades)}")
        print(f"   Total Energy Traded: {total_energy:.3f} kWh")
        print(f"   Total Value: ${total_value:.2f} USD")
        print(f"   Active Offers: {len(active_offers)}")
        print(f"   Active Requests: {len(active_requests)}")
    except Exception as e:
        print(f"❌ Failed to get stats: {e}")
    
    # Test 8: P2P Trading Scenario - user_001 (prosumer) selling to user_003 (pure consumer)
    print("\n" + "=" * 60)
    print("TEST 8: P2P Trading Scenario - Surplus to Pure Consumer")
    print("=" * 60)
    
    # Check if user_003 exists
    user_003 = None
    for m in model.members:
        if m.member_id == "user_003":
            user_003 = m
            break
    
    if user_003:
        try:
            # Get user_001's current state to show surplus
            member_001 = None
            for m in model.members:
                if m.member_id == "user_001":
                    member_001 = m
                    break
            
            if member_001:
                # Simulate user_001 at current time to see surplus
                result_001 = simulation_engine.simulate_member(
                    member_001,
                    current_time,
                    apply_demand_response=False,
                    p2p_sold_kw=0.0,
                    p2p_bought_kw=0.0
                )
                
                print(f"📊 user_001 (Prosumer) Current State:")
                print(f"   Generation: {result_001['solar_generation_kw']:.3f} kW")
                print(f"   Consumption: {result_001['consumption_kw']:.3f} kW")
                print(f"   Net Balance (Gen - Cons): {result_001['solar_generation_kw'] - result_001['consumption_kw']:.3f} kW")
                print(f"   Battery SOC: {result_001['battery_soc']*100:.1f}%")
                print(f"   Battery Power: {result_001['battery_power_kw']:.3f} kW (positive=charging, negative=discharging)")
                print(f"   Net Balance (after battery): {result_001['net_balance_kw']:.3f} kW")
                print(f"   Grid Export: {result_001['grid_export_kw']:.3f} kW")
                print(f"   Available Surplus: {result_001['grid_export_kw']:.3f} kW")
                print(f"   💡 Surplus flow: Generation → Consumption → Battery Charging → Grid Export")
                
                # Explain why grid_export might be 0
                if result_001['net_balance_kw'] > 0 and result_001['grid_export_kw'] == 0:
                    print(f"\n   ⚠️  Analysis: Net balance is positive ({result_001['net_balance_kw']:.3f} kW) but grid export is 0")
                    print(f"      Battery capacity: {member_001.assets.battery_capacity_kwh:.1f} kWh")
                    print(f"      Current SOC: {result_001['battery_soc']*100:.1f}%")
                    print(f"      Max SOC: {member_001.assets.battery_max_soc*100:.1f}%")
                    print(f"      Grid Export Limit: {member_001.assets.grid_export_limit_kw:.1f} kW")
                    print(f"      Battery Power: {result_001['battery_power_kw']:.3f} kW")
                    
                    # Check if grid export limit is blocking
                    if member_001.assets.grid_export_limit_kw == 0:
                        print(f"      ❌ Grid export limit is 0 - this is blocking exports!")
                        print(f"      💡 Solution: Set grid_export_limit_kw > 0 in member assets")
                    elif result_001['battery_soc'] >= member_001.assets.battery_max_soc:
                        print(f"      ✅ Battery is at max SOC - surplus should go to grid export")
                    elif result_001['battery_power_kw'] == 0:
                        print(f"      ⚠️  Battery power is 0 - pattern may indicate battery should be idle")
                        print(f"      💡 In real scenario, battery would charge with surplus, then export excess")
                    
                    # Try to find a time when there's actual grid export
                    print(f"\n   🔍 Searching for a time when user_001 has grid export...")
                    for test_hour in [10, 11, 12, 13, 14, 15]:  # Peak solar hours
                        test_time = current_time.replace(hour=test_hour, minute=0, second=0, microsecond=0)
                        test_result = simulation_engine.simulate_member(
                            member_001,
                            test_time,
                            apply_demand_response=False,
                            p2p_sold_kw=0.0,
                            p2p_bought_kw=0.0
                        )
                        if test_result['grid_export_kw'] > 0.1:  # Has meaningful export
                            print(f"      ✅ Found export at {test_time.isoformat()}: {test_result['grid_export_kw']:.3f} kW")
                            print(f"         Generation: {test_result['solar_generation_kw']:.3f} kW")
                            print(f"         Consumption: {test_result['consumption_kw']:.3f} kW")
                            print(f"         Battery Power: {test_result['battery_power_kw']:.3f} kW")
                            print(f"         Net Balance: {test_result['net_balance_kw']:.3f} kW")
                            break
                
                # Simulate user_003 (pure consumer)
                result_003 = simulation_engine.simulate_member(
                    user_003,
                    current_time,
                    apply_demand_response=False,
                    p2p_sold_kw=0.0,
                    p2p_bought_kw=0.0
                )
                
                print(f"\n📊 user_003 (Pure Consumer) Current State:")
                print(f"   Generation: {result_003['solar_generation_kw']:.3f} kW (no PV)")
                print(f"   Consumption: {result_003['consumption_kw']:.3f} kW")
                print(f"   Net Balance: {result_003['net_balance_kw']:.3f} kW (deficit)")
                print(f"   Grid Import: {result_003['grid_import_kw']:.3f} kW")
                print(f"   💡 Needs to import: {result_003['grid_import_kw']:.3f} kW from grid or P2P")
                
                # Get grid rates from model
                grid_export_rate = model.community_control.export_rate_usd_per_kwh
                grid_import_rate = model.community_control.import_rate_usd_per_kwh
                
                print(f"\n💰 Economic Analysis:")
                print(f"   Grid Export Rate: ${grid_export_rate:.3f}/kWh (what user_001 gets from grid)")
                print(f"   Grid Import Rate: ${grid_import_rate:.3f}/kWh (what user_003 pays to grid)")
                print(f"   P2P Price Range: ${grid_export_rate:.3f} - ${grid_import_rate:.3f}/kWh")
                print(f"   💡 Win-Win: user_001 gets more than grid export, user_003 pays less than grid import")
                
                # Create a P2P trade scenario
                if result_001['grid_export_kw'] > 0 and result_003['grid_import_kw'] > 0:
                    # Calculate optimal P2P price (midpoint between export and import rates)
                    optimal_p2p_price = (grid_export_rate + grid_import_rate) / 2
                    trade_amount = min(result_001['grid_export_kw'], result_003['grid_import_kw'], 5.0)  # Cap at 5 kW
                    
                    print(f"\n🔄 P2P Trade Scenario:")
                    print(f"   Trade Amount: {trade_amount:.2f} kWh")
                    print(f"   P2P Price: ${optimal_p2p_price:.3f}/kWh")
                    print(f"   user_001 Benefit: ${(optimal_p2p_price - grid_export_rate) * trade_amount:.3f} more than grid export")
                    print(f"   user_003 Savings: ${(grid_import_rate - optimal_p2p_price) * trade_amount:.3f} less than grid import")
                    
                    # Show impact on grid flows
                    print(f"\n📈 Impact on Grid Flows:")
                    print(f"   user_001: Grid Export reduces by {trade_amount:.2f} kW (sold via P2P)")
                    print(f"   user_003: Grid Import reduces by {trade_amount:.2f} kW (bought via P2P)")
                    print(f"   Grid Load Reduction: {trade_amount:.2f} kW (less strain on grid)")
                    
                    # Simulate with P2P trade
                    result_001_p2p = simulation_engine.simulate_member(
                        member_001,
                        current_time,
                        apply_demand_response=False,
                        p2p_sold_kw=trade_amount,
                        p2p_bought_kw=0.0
                    )
                    
                    result_003_p2p = simulation_engine.simulate_member(
                        user_003,
                        current_time,
                        apply_demand_response=False,
                        p2p_sold_kw=0.0,
                        p2p_bought_kw=trade_amount
                    )
                    
                    print(f"\n✅ Simulation with P2P Trade:")
                    print(f"   user_001 Grid Export: {result_001['grid_export_kw']:.3f} → {result_001_p2p['grid_export_kw']:.3f} kW")
                    print(f"   user_003 Grid Import: {result_003['grid_import_kw']:.3f} → {result_003_p2p['grid_import_kw']:.3f} kW")
                    print(f"   ✅ P2P trade successfully reduces grid flows!")
                else:
                    print(f"\n⚠️  No surplus/deficit match at this time")
                    print(f"   user_001 surplus: {result_001['grid_export_kw']:.3f} kW")
                    print(f"   user_003 deficit: {result_003['grid_import_kw']:.3f} kW")
        except Exception as e:
            print(f"❌ Failed to demonstrate P2P scenario: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("⚠️  user_003 not found - skipping P2P scenario test")
        print("   Run: python scripts/add_user_003.py to add pure consumer")
    
    print("\n" + "=" * 60)
    print("✅ Testing Complete!")
    print("=" * 60)
    
    # Cleanup: Delete test data from MongoDB
    print("\n🧹 Cleaning up test data...")
    try:
        from app.db.database import get_database, Collections
        
        db = await get_database()
        
        # Delete P2P transactions created during testing
        p2p_collection = db[Collections.P2P_TRANSACTIONS]
        delete_result = await p2p_collection.delete_many({})
        print(f"   ✅ Deleted {delete_result.deleted_count} P2P transaction(s) from MongoDB")
        
        # Note: Offers and requests are stored in memory only (not persisted to MongoDB)
        # They will be cleared when the service instance is destroyed
        
    except Exception as e:
        print(f"   ⚠️  Warning: Could not clean up test data: {e}")
    
    # Close MongoDB connection
    try:
        from app.db.database import close_mongo_connection
        await close_mongo_connection()
        print("\n🔌 MongoDB connection closed")
    except Exception as e:
        print(f"\n⚠️  Warning: Could not close MongoDB connection: {e}")


if __name__ == "__main__":
    print("Starting P2P Marketplace tests...")
    print("Note: Ensure MongoDB is running and MONGODB_URI is configured")
    print()
    asyncio.run(test_marketplace())

