"""
Comprehensive Debug Script for Community Energy Simulation

Tests all simulation components and verifies calculations across:
- Community-level simulation
- User-level simulation
- Data consistency checks
- Calculation verification
"""
import sys
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine
from app.services.community.dashboard_service import CommunityDashboardService
from app.services.user.dashboard_service import UserDashboardService


class SimulationDebugger:
    """Comprehensive debugger for simulation system."""
    
    def __init__(self):
        self.model_service = CommunityModelService()
        self.engine = CommunitySimulationEngine(self.model_service)
        self.community_service = CommunityDashboardService()
        self.user_service = UserDashboardService()
        self.model = self.model_service.get_model()
    
    def print_header(self, title: str):
        """Print a formatted header."""
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)
    
    def print_section(self, title: str):
        """Print a formatted section header."""
        print(f"\n--- {title} ---")
    
    def test_model_loading(self):
        """Test if model loads correctly."""
        self.print_header("MODEL LOADING TEST")
        
        if self.model is None:
            print("[ERROR] Model not loaded!")
            return False
        
        print(f"[OK] Model loaded successfully")
        print(f"  Community ID: {self.model.community.community_id}")
        print(f"  Timezone: {self.model.community.timezone}")
        print(f"  Number of members: {len(self.model.members)}")
        
        print(f"\n  Members:")
        for member in self.model.members:
            print(f"    - {member.member_id} ({member.member_type.value})")
            print(f"      PV: {member.assets.pv_capacity_kw} kW")
            print(f"      Battery: {member.assets.battery_capacity_kwh} kWh")
            print(f"      Load: {member.assets.load_capacity_kw} kW")
        
        return True
    
    def test_community_simulation(self, timestamp: datetime = None):
        """Test community-level simulation."""
        self.print_header("COMMUNITY SIMULATION TEST")
        
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo(self.model.community.timezone))
        
        print(f"Simulation timestamp: {timestamp}\n")
        
        result = self.engine.simulate_community(timestamp)
        
        if not result:
            print("❌ ERROR: Simulation returned empty result!")
            return None
        
        # Extract values
        generation = result.get('total_generation_kw', 0)
        consumption = result.get('total_consumption_kw', 0)
        net_balance = result.get('total_net_balance_kw', 0)
        grid_export = result.get('total_grid_export_kw', 0)
        grid_import = result.get('total_grid_import_kw', 0)
        battery_power = result.get('total_battery_power_kw', 0)
        members = result.get('members', [])
        
        print(f"Community Totals:")
        print(f"  Generation:        {generation:>8.3f} kW")
        print(f"  Consumption:       {consumption:>8.3f} kW")
        print(f"  Battery Power:     {battery_power:>8.3f} kW")
        print(f"  Net Balance:       {net_balance:>8.3f} kW")
        print(f"  Grid Export:       {grid_export:>8.3f} kW")
        print(f"  Grid Import:       {grid_import:>8.3f} kW")
        
        # Verify calculations
        self.print_section("Calculation Verification")
        expected_net = generation - consumption + battery_power
        print(f"  Expected Net Balance = Generation - Consumption + Battery")
        print(f"                       = {generation:.3f} - {consumption:.3f} + {battery_power:.3f}")
        print(f"                       = {expected_net:.3f} kW")
        print(f"  Actual Net Balance:   {net_balance:.3f} kW")
        
        if abs(expected_net - net_balance) < 0.001:
            print(f"  [OK] Net balance calculation is correct")
        else:
            print(f"  [ERROR] Net balance mismatch! Difference: {abs(expected_net - net_balance):.3f} kW")
        
        # Member details
        self.print_section("Member Details")
        total_member_gen = 0
        total_member_cons = 0
        total_member_battery = 0
        total_member_net = 0
        total_member_export = 0
        total_member_import = 0
        
        for m in members:
            m_gen = m.get('solar_generation_kw', 0)
            m_cons = m.get('consumption_kw', 0)
            m_battery = m.get('battery_power_kw', 0)
            m_net = m.get('net_balance_kw', 0)
            m_export = m.get('grid_export_kw', 0)
            m_import = m.get('grid_import_kw', 0)
            
            total_member_gen += m_gen
            total_member_cons += m_cons
            total_member_battery += m_battery
            total_member_net += m_net
            total_member_export += m_export
            total_member_import += m_import
            
            print(f"\n  {m.get('member_id')}:")
            print(f"    Generation:  {m_gen:>6.3f} kW")
            print(f"    Consumption: {m_cons:>6.3f} kW")
            print(f"    Battery:     {m_battery:>6.3f} kW")
            print(f"    Net Balance: {m_net:>6.3f} kW")
            print(f"    Grid Export: {m_export:>6.3f} kW")
            print(f"    Grid Import: {m_import:>6.3f} kW")
            print(f"    Battery SOC: {m.get('battery_soc', 0)*100:>5.1f}%")
            
            # Verify member calculation
            expected_m_net = m_gen - m_cons + m_battery
            if abs(expected_m_net - m_net) > 0.001:
                print(f"    [WARN] Member net balance mismatch! Expected: {expected_m_net:.3f}, Got: {m_net:.3f}")
        
        # Verify member aggregation
        self.print_section("Member Aggregation Verification")
        print(f"Sum of member values:")
        print(f"  Generation:  {total_member_gen:>8.3f} kW (community: {generation:.3f})")
        print(f"  Consumption: {total_member_cons:>8.3f} kW (community: {consumption:.3f})")
        print(f"  Battery:     {total_member_battery:>8.3f} kW (community: {battery_power:.3f})")
        print(f"  Net Balance: {total_member_net:>8.3f} kW (community: {net_balance:.3f})")
        print(f"  Grid Export: {total_member_export:>8.3f} kW (community: {grid_export:.3f})")
        print(f"  Grid Import: {total_member_import:>8.3f} kW (community: {grid_import:.3f})")
        
        if abs(total_member_gen - generation) < 0.001:
            print(f"  [OK] Generation aggregation correct")
        else:
            print(f"  [ERROR] Generation aggregation mismatch!")
        
        if abs(total_member_cons - consumption) < 0.001:
            print(f"  [OK] Consumption aggregation correct")
        else:
            print(f"  [ERROR] Consumption aggregation mismatch!")
        
        if abs(total_member_net - net_balance) < 0.001:
            print(f"  [OK] Net balance aggregation correct")
        else:
            print(f"  [ERROR] Net balance aggregation mismatch!")
        
        return result
    
    async def test_user_dashboard(self, user_id: str, timestamp: datetime = None):
        """Test user dashboard simulation."""
        self.print_header(f"USER DASHBOARD TEST - {user_id}")
        
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo(self.model.community.timezone))
        
        print(f"Timestamp: {timestamp}\n")
        
        # Get dashboard data
        dashboard = await self.user_service.get_user_dashboard(user_id, include_users=False)
        
        # Get current data
        current_data = self.user_service.get_user_data_at_timestamp(user_id, timestamp)
        
        print(f"Dashboard Data (Daily Totals):")
        print(f"  Produced Today:    {dashboard.get('produced_kwh_today', 0):>8.2f} kWh")
        print(f"  Consumed Today:    {dashboard.get('consumed_kwh_today', 0):>8.2f} kWh")
        print(f"  Net Balance Today: {dashboard.get('net_kwh_today', 0):>8.2f} kWh")
        print(f"  Current Flow Rate: {dashboard.get('current_net_balance_kw', 0):>8.2f} kW")
        
        if current_data:
            print(f"\nCurrent Instantaneous Data:")
            print(f"  Generation:   {current_data.get('solar_generation_kw', 0):>8.3f} kW")
            print(f"  Consumption:  {current_data.get('consumption_kw', 0):>8.3f} kW")
            print(f"  Battery Power: {current_data.get('battery_power_kw', 0):>8.3f} kW")
            print(f"  Net Balance:  {current_data.get('net_balance_kw', 0):>8.3f} kW")
            print(f"  Grid Export:  {current_data.get('grid_export_kw', 0):>8.3f} kW")
            print(f"  Grid Import:  {current_data.get('grid_import_kw', 0):>8.3f} kW")
            print(f"  Battery SOC:  {current_data.get('battery_soc_pct', 0):>7.1f}%")
        
        # Verify net balance calculation
        produced = dashboard.get('produced_kwh_today', 0)
        consumed = dashboard.get('consumed_kwh_today', 0)
        net = dashboard.get('net_kwh_today', 0)
        expected_net = produced - consumed
        
        self.print_section("Verification")
        print(f"  Expected Net = Produced - Consumed")
        print(f"               = {produced:.2f} - {consumed:.2f}")
        print(f"               = {expected_net:.2f} kWh")
        print(f"  Actual Net:   {net:.2f} kWh")
        
        if abs(expected_net - net) < 0.01:
            print(f"  [OK] Daily net balance calculation is correct")
        else:
            print(f"  [ERROR] Daily net balance mismatch! Difference: {abs(expected_net - net):.2f} kWh")
        
        return dashboard, current_data
    
    async def test_community_dashboard(self, timestamp: datetime = None):
        """Test community dashboard service."""
        self.print_header("COMMUNITY DASHBOARD SERVICE TEST")
        
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo(self.model.community.timezone))
        
        print(f"Timestamp: {timestamp}\n")
        
        # Get dashboard data
        dashboard = await self.community_service.get_community_dashboard_data(
            include_trends=False
        )
        
        energy_flow = dashboard.get('total_energy_flow', {})
        
        print(f"Dashboard Data:")
        print(f"  Generation (live):  {energy_flow.get('generation', {}).get('live', 0):>8.2f} kW")
        print(f"  Consumption (live): {energy_flow.get('consumption', {}).get('live', 0):>8.2f} kW")
        print(f"  Net Balance:        {energy_flow.get('net', 0):>8.2f} kW")
        print(f"  Grid Export:        {energy_flow.get('grid_export_kw', 0):>8.2f} kW")
        print(f"  Grid Import:        {energy_flow.get('grid_import_kw', 0):>8.2f} kW")
        
        return dashboard
    
    def compare_simulation_vs_dashboard(self, sim_result: dict, dashboard: dict):
        """Compare simulation engine output vs dashboard service output."""
        self.print_header("SIMULATION vs DASHBOARD COMPARISON")
        
        energy_flow = dashboard.get('total_energy_flow', {})
        
        sim_gen = sim_result.get('total_generation_kw', 0)
        sim_cons = sim_result.get('total_consumption_kw', 0)
        sim_net = sim_result.get('total_net_balance_kw', 0)
        sim_export = sim_result.get('total_grid_export_kw', 0)
        sim_import = sim_result.get('total_grid_import_kw', 0)
        
        dash_gen = energy_flow.get('generation', {}).get('live', 0)
        dash_cons = energy_flow.get('consumption', {}).get('live', 0)
        dash_net = energy_flow.get('net', 0)
        dash_export = energy_flow.get('grid_export_kw', 0)
        dash_import = energy_flow.get('grid_import_kw', 0)
        
        print(f"{'Metric':<20} {'Simulation':>12} {'Dashboard':>12} {'Match':>10}")
        print("-" * 60)
        
        def compare(name, sim_val, dash_val, tolerance=0.1):
            match = "[OK]" if abs(sim_val - dash_val) < tolerance else "[ERROR]"
            print(f"{name:<20} {sim_val:>12.3f} {dash_val:>12.2f} {match:>10}")
        
        compare("Generation (kW)", sim_gen, dash_gen)
        compare("Consumption (kW)", sim_cons, dash_cons)
        compare("Net Balance (kW)", sim_net, dash_net, tolerance=0.5)
        compare("Grid Export (kW)", sim_export, dash_export)
        compare("Grid Import (kW)", sim_import, dash_import, tolerance=0.5)
    
    def test_pattern_access(self, timestamp: datetime = None):
        """Test pattern file access and data."""
        self.print_header("PATTERN DATA TEST")
        
        if timestamp is None:
            timestamp = datetime.now(ZoneInfo(self.model.community.timezone))
        
        print(f"Timestamp: {timestamp}\n")
        
        pattern_row = self.engine._get_pattern_row(timestamp)
        
        if pattern_row is None:
            print("[ERROR] No pattern row found!")
            return None
        
        print(f"Pattern Row Data:")
        for key, value in pattern_row.items():
            if isinstance(value, (int, float)):
                print(f"  {key:<40} {value:>10.6f}")
            else:
                print(f"  {key:<40} {str(value):>10}")
        
        return pattern_row
    
    async def run_all_tests(self):
        """Run all debug tests."""
        print("\n" + "=" * 80)
        print("  COMPREHENSIVE SIMULATION DEBUG TEST SUITE")
        print("=" * 80)
        
        # Test model loading
        if not self.test_model_loading():
            print("\n[ERROR] Cannot proceed - model not loaded!")
            return
        
        # Use current time
        now = datetime.now(ZoneInfo(self.model.community.timezone))
        
        # Test pattern access
        self.test_pattern_access(now)
        
        # Test community simulation
        sim_result = self.test_community_simulation(now)
        
        if sim_result:
            # Test community dashboard
            community_dashboard = await self.test_community_dashboard(now)
            
            # Compare simulation vs dashboard
            if community_dashboard:
                self.compare_simulation_vs_dashboard(sim_result, community_dashboard)
            
            # Test user dashboards for all members
            for member in self.model.members:
                await self.test_user_dashboard(member.member_id, now)
        
        # Summary
        self.print_header("TEST SUMMARY")
        print("All tests completed. Review output above for any issues.")
        print("\nKey things to check:")
        print("  1. Net balance = Generation - Consumption + Battery Power")
        print("  2. Member values aggregate correctly to community totals")
        print("  3. Dashboard values match simulation engine output")
        print("  4. Grid export/import values are consistent")


async def main():
    """Main entry point."""
    debugger = SimulationDebugger()
    await debugger.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())

