"""
Work Allocation Optimization Algorithm

This algorithm optimizes weekly work allocation to:
1. Meet baseline income requirements (5.6K/month)
2. Maintain stable baseline clients
3. Allocate time for system building (business growth)
4. Maximize strategic work that compounds (projects, agency-building)

The key insight: We're optimizing for business growth, not just income maximization.
Hourly work pays bills but doesn't scale. System building and project work compound.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import numpy as np
from scipy.optimize import minimize, linprog


class WorkType(Enum):
    """Types of work with different growth potential."""
    BASELINE_CLIENT = "baseline_client"  # Stable, predictable, low growth
    HIGH_RATE_HOURLY = "high_rate_hourly"  # Better pay, still hourly
    PROJECT_BASED = "project_based"  # Higher value, compounds
    SYSTEM_BUILDING = "system_building"  # Highest compound value


@dataclass
class Client:
    """Represents a client with their characteristics."""
    name: str
    hourly_rate: float
    min_hours_per_week: float
    max_hours_per_week: float
    work_type: WorkType
    growth_potential: float  # 0-1 scale: how much this work compounds


@dataclass
class OptimizationResult:
    """Result of the optimization algorithm."""
    baseline_client_1_hours: float
    baseline_client_2_hours: float
    system_building_hours: float
    high_rate_hours: float
    project_hours: float
    total_billable_hours: float
    weekly_income: float
    monthly_income: float
    business_growth_score: float  # 0-1: how well this builds the business
    is_feasible: bool
    message: str


@dataclass
class ScenarioAnalysis:
    """Analysis of a specific work allocation scenario."""
    scenario_name: str
    hourly_hours: float
    project_hours: float
    system_building_hours: float
    total_billable_hours: float
    weekly_income: float
    monthly_income: float
    hours_remaining_after_baseline: float
    business_growth_score: float
    meets_baseline: bool
    num_clients_needed: float  # If using hourly work
    recommendation: str


@dataclass
class MonthlyGrowthPlan:
    """Monthly growth plan with work allocation strategy."""
    month: str
    month_number: int
    target_income: float
    hourly_hours: float
    project_hours: float
    system_building_hours: float
    hourly_rate: float
    project_rate: float
    num_clients: float
    weekly_income: float
    monthly_income: float
    growth_score: float
    strategy: str
    replacement_opportunity: str  # What to replace this month


class WorkAllocationOptimizer:
    """
    Optimizes work allocation to balance income needs with business growth.
    
    The algorithm uses a multi-objective approach:
    - Primary: Ensure baseline income is met
    - Secondary: Maximize business growth potential
    - Constraint: Respect weekly hour limits
    """
    
    # Constants
    MAX_BILLABLE_HOURS_PER_WEEK = 50.0
    SYSTEM_BUILDING_HOURS_PER_WEEK = 8.0
    BASELINE_INCOME_PER_MONTH = 5600.0
    WEEKS_PER_MONTH = 4.33  # Average weeks per month
    MAX_HOURS_PER_CLIENT_PER_WEEK = 20.0  # Maximum hours per client per week
    MIN_HOURS_PER_CLIENT_PER_WEEK = 15.0  # Minimum hours per client per week
    
    # Growth potential weights (higher = more important for business building)
    GROWTH_WEIGHTS = {
        WorkType.BASELINE_CLIENT: 0.1,      # Low: pays bills, doesn't scale
        WorkType.HIGH_RATE_HOURLY: 0.3,    # Medium: better pay, still hourly
        WorkType.PROJECT_BASED: 0.8,        # High: compounds, builds portfolio
        WorkType.SYSTEM_BUILDING: 1.0,      # Highest: builds the business itself
    }
    
    def __init__(
        self,
        baseline_client_1_rate: float = 40.0,  # $/hour
        baseline_client_2_rate: float = 40.0,  # $/hour
        high_rate_hourly_rate: float = 50.0,  # $/hour
        project_hourly_equivalent: float = 40.0,  # $/hour equivalent
    ):
        """
        Initialize the optimizer with rate assumptions.
        
        Args:
            baseline_client_1_rate: Hourly rate for baseline client 1
            baseline_client_2_rate: Hourly rate for baseline client 2
            high_rate_hourly_rate: Rate for high-rate hourly work
            project_hourly_equivalent: Effective hourly rate for project work
        """
        self.baseline_client_1_rate = baseline_client_1_rate
        self.baseline_client_2_rate = baseline_client_2_rate
        self.high_rate_hourly_rate = high_rate_hourly_rate
        self.project_hourly_equivalent = project_hourly_equivalent
        
        # Calculate minimum baseline hours needed
        self.min_baseline_income_per_week = self.BASELINE_INCOME_PER_MONTH / self.WEEKS_PER_MONTH
        
        # Calculate minimum hours needed for baseline at different rates
        self.min_hours_at_40 = self.min_baseline_income_per_week / 40.0
        self.min_hours_at_50 = self.min_baseline_income_per_week / 50.0
        
    def _calculate_income(
        self,
        client_1_hours: float,
        client_2_hours: float,
        high_rate_hours: float,
        project_hours: float
    ) -> float:
        """Calculate weekly income from allocated hours."""
        return (
            client_1_hours * self.baseline_client_1_rate +
            client_2_hours * self.baseline_client_2_rate +
            high_rate_hours * self.high_rate_hourly_rate +
            project_hours * self.project_hourly_equivalent
        )
    
    def _calculate_business_growth_score(
        self,
        client_1_hours: float,
        client_2_hours: float,
        high_rate_hours: float,
        project_hours: float,
        system_building_hours: float
    ) -> float:
        """
        Calculate a score representing how well this allocation builds the business.
        
        Higher score = more compounding work (system building, projects)
        Lower score = more hourly work (baseline clients, high-rate hourly)
        """
        total_hours = (
            client_1_hours + client_2_hours + 
            high_rate_hours + project_hours + system_building_hours
        )
        
        if total_hours == 0:
            return 0.0
        
        # Weighted average of growth potential
        weighted_growth = (
            client_1_hours * self.GROWTH_WEIGHTS[WorkType.BASELINE_CLIENT] +
            client_2_hours * self.GROWTH_WEIGHTS[WorkType.BASELINE_CLIENT] +
            high_rate_hours * self.GROWTH_WEIGHTS[WorkType.HIGH_RATE_HOURLY] +
            project_hours * self.GROWTH_WEIGHTS[WorkType.PROJECT_BASED] +
            system_building_hours * self.GROWTH_WEIGHTS[WorkType.SYSTEM_BUILDING]
        )
        
        return weighted_growth / total_hours
    
    def _objective_function(self, x: np.ndarray) -> float:
        """
        Objective function to minimize (negative of what we want to maximize).
        
        We want to:
        1. Minimize baseline client hours (just enough to meet income)
        2. Maximize system building and project hours (business growth)
        
        x = [client_1_hours, client_2_hours, high_rate_hours, project_hours]
        Note: system_building_hours is fixed at 8
        """
        client_1_hours, client_2_hours, high_rate_hours, project_hours = x
        system_building_hours = self.SYSTEM_BUILDING_HOURS_PER_WEEK
        
        # Calculate growth score (we want to maximize this, so minimize negative)
        growth_score = self._calculate_business_growth_score(
            client_1_hours, client_2_hours, high_rate_hours, 
            project_hours, system_building_hours
        )
        
        # We want to minimize baseline hours (just enough to meet requirements)
        # and maximize growth work
        # So we minimize: (baseline hours) - (growth work * weight)
        baseline_hours = client_1_hours + client_2_hours
        growth_hours = project_hours + system_building_hours
        
        # Objective: minimize baseline hours, maximize growth hours
        # Negative because we're minimizing
        return baseline_hours - (growth_hours * 2.0) - (growth_score * 10.0)
    
    def _constraints(self) -> List[Dict]:
        """
        Define constraints for the optimization problem.
        
        Constraints:
        1. Total billable hours <= 50
        2. Baseline client 1: 15-20 hours
        3. Baseline client 2: 15-20 hours
        4. Weekly income >= minimum required
        5. All hours >= 0
        """
        constraints = []
        
        # Constraint: Total billable hours <= 50
        # billable = client_1 + client_2 + high_rate + project (system building not billable)
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: self.MAX_BILLABLE_HOURS_PER_WEEK - (
                x[0] + x[1] + x[2] + x[3]
            )
        })
        
        # Constraint: Baseline client 1: 15-20 hours
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: x[0] - 15.0  # >= 15
        })
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: 20.0 - x[0]  # <= 20
        })
        
        # Constraint: Baseline client 2: 15-20 hours
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: x[1] - 15.0  # >= 15
        })
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: 20.0 - x[1]  # <= 20
        })
        
        # Constraint: Weekly income >= minimum required
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: self._calculate_income(
                x[0], x[1], x[2], x[3]
            ) - self.min_baseline_income_per_week
        })
        
        # Constraint: All hours >= 0
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: x[0]  # client_1 >= 0
        })
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: x[1]  # client_2 >= 0
        })
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: x[2]  # high_rate >= 0
        })
        constraints.append({
            'type': 'ineq',
            'fun': lambda x: x[3]  # project >= 0
        })
        
        return constraints
    
    def optimize(self) -> OptimizationResult:
        """
        Run the optimization algorithm.
        
        Returns:
            OptimizationResult with optimal allocation
        """
        # Initial guess: minimum baseline hours, rest for growth work
        # x = [client_1_hours, client_2_hours, high_rate_hours, project_hours]
        initial_guess = np.array([17.5, 17.5, 0.0, 0.0])  # Start with middle of baseline range
        
        # Bounds: [client_1, client_2, high_rate, project]
        bounds = [
            (15.0, 20.0),  # Baseline client 1
            (15.0, 20.0),  # Baseline client 2
            (0.0, None),   # High rate (no upper bound)
            (0.0, None),   # Project (no upper bound)
        ]
        
        try:
            # Run optimization
            result = minimize(
                self._objective_function,
                initial_guess,
                method='SLSQP',  # Sequential Least Squares Programming
                bounds=bounds,
                constraints=self._constraints(),
                options={'maxiter': 1000, 'ftol': 1e-6}
            )
            
            if not result.success:
                # If optimization failed, try a fallback allocation
                return self._fallback_allocation(result.message)
            
            client_1_hours = max(15.0, min(20.0, result.x[0]))
            client_2_hours = max(15.0, min(20.0, result.x[1]))
            high_rate_hours = max(0.0, result.x[2])
            project_hours = max(0.0, result.x[3])
            system_building_hours = self.SYSTEM_BUILDING_HOURS_PER_WEEK
            
            # Calculate totals
            total_billable = client_1_hours + client_2_hours + high_rate_hours + project_hours
            weekly_income = self._calculate_income(
                client_1_hours, client_2_hours, high_rate_hours, project_hours
            )
            monthly_income = weekly_income * self.WEEKS_PER_MONTH
            growth_score = self._calculate_business_growth_score(
                client_1_hours, client_2_hours, high_rate_hours, 
                project_hours, system_building_hours
            )
            
            # Validate feasibility
            is_feasible = (
                total_billable <= self.MAX_BILLABLE_HOURS_PER_WEEK and
                monthly_income >= self.BASELINE_INCOME_PER_MONTH and
                15.0 <= client_1_hours <= 20.0 and
                15.0 <= client_2_hours <= 20.0
            )
            
            message = "Optimization successful" if is_feasible else "Solution found but constraints may not be fully satisfied"
            
            return OptimizationResult(
                baseline_client_1_hours=round(client_1_hours, 2),
                baseline_client_2_hours=round(client_2_hours, 2),
                system_building_hours=round(system_building_hours, 2),
                high_rate_hours=round(high_rate_hours, 2),
                project_hours=round(project_hours, 2),
                total_billable_hours=round(total_billable, 2),
                weekly_income=round(weekly_income, 2),
                monthly_income=round(monthly_income, 2),
                business_growth_score=round(growth_score, 3),
                is_feasible=is_feasible,
                message=message
            )
            
        except Exception as e:
            return self._fallback_allocation(f"Optimization error: {str(e)}")
    
    def _fallback_allocation(self, error_message: str) -> OptimizationResult:
        """
        Fallback allocation if optimization fails.
        Uses conservative approach: minimum baseline hours, rest for growth.
        """
        # Minimum baseline: 15 hours each = 30 hours
        # System building: 8 hours (fixed)
        # Remaining: 50 - 30 - 8 = 12 hours for growth work
        
        client_1_hours = 15.0
        client_2_hours = 15.0
        system_building_hours = self.SYSTEM_BUILDING_HOURS_PER_WEEK
        high_rate_hours = 0.0
        project_hours = 12.0  # Allocate remaining to projects (highest growth)
        
        total_billable = client_1_hours + client_2_hours + high_rate_hours + project_hours
        weekly_income = self._calculate_income(
            client_1_hours, client_2_hours, high_rate_hours, project_hours
        )
        monthly_income = weekly_income * self.WEEKS_PER_MONTH
        growth_score = self._calculate_business_growth_score(
            client_1_hours, client_2_hours, high_rate_hours, 
            project_hours, system_building_hours
        )
        
        return OptimizationResult(
            baseline_client_1_hours=client_1_hours,
            baseline_client_2_hours=client_2_hours,
            system_building_hours=system_building_hours,
            high_rate_hours=high_rate_hours,
            project_hours=project_hours,
            total_billable_hours=total_billable,
            weekly_income=round(weekly_income, 2),
            monthly_income=round(monthly_income, 2),
            business_growth_score=round(growth_score, 3),
            is_feasible=monthly_income >= self.BASELINE_INCOME_PER_MONTH,
            message=f"Fallback allocation used. {error_message}"
        )
    
    def analyze_scenarios(self) -> List[ScenarioAnalysis]:
        """
        Analyze different scenarios to help determine optimal strategy.
        
        Explores:
        1. All hourly work at $40/hr
        2. All project work at $40/hr equivalent
        3. Mixed approach (minimum hourly + rest project)
        4. Optimal balance for growth
        """
        scenarios = []
        
        # Scenario 1: All hourly at baseline rate
        hourly_hours_needed = self.min_baseline_income_per_week / self.baseline_client_1_rate
        if hourly_hours_needed <= self.MAX_BILLABLE_HOURS_PER_WEEK:
            remaining_hours = self.MAX_BILLABLE_HOURS_PER_WEEK - hourly_hours_needed - self.SYSTEM_BUILDING_HOURS_PER_WEEK
            num_clients = hourly_hours_needed / self.MAX_HOURS_PER_CLIENT_PER_WEEK
            
            recommendation = self._generate_recommendation(
                hourly_hours=hourly_hours_needed,
                project_hours=0.0,
                num_clients=num_clients,
                remaining_hours=remaining_hours,
                scenario_type="all_hourly"
            )
            
            scenarios.append(ScenarioAnalysis(
                scenario_name=f"All Hourly (${self.baseline_client_1_rate}/hr)",
                hourly_hours=hourly_hours_needed,
                project_hours=0.0,
                system_building_hours=self.SYSTEM_BUILDING_HOURS_PER_WEEK,
                total_billable_hours=hourly_hours_needed,
                weekly_income=self.min_baseline_income_per_week,
                monthly_income=self.BASELINE_INCOME_PER_MONTH,
                hours_remaining_after_baseline=max(0, remaining_hours),
                business_growth_score=self._calculate_business_growth_score(
                    hourly_hours_needed, 0.0, 0.0, 0.0, self.SYSTEM_BUILDING_HOURS_PER_WEEK
                ) if hourly_hours_needed > 0 else 0.0,
                meets_baseline=True,
                num_clients_needed=num_clients,
                recommendation=recommendation
            ))
        
        # Scenario 2: All project work at project rate equivalent
        project_hours_needed = self.min_baseline_income_per_week / self.project_hourly_equivalent
        if project_hours_needed <= self.MAX_BILLABLE_HOURS_PER_WEEK:
            remaining_hours = self.MAX_BILLABLE_HOURS_PER_WEEK - project_hours_needed - self.SYSTEM_BUILDING_HOURS_PER_WEEK
            
            recommendation = self._generate_recommendation(
                hourly_hours=0.0,
                project_hours=project_hours_needed,
                num_clients=0.0,
                remaining_hours=remaining_hours,
                scenario_type="all_project"
            )
            
            scenarios.append(ScenarioAnalysis(
                scenario_name=f"All Project-Based (${self.project_hourly_equivalent}/hr equiv)",
                hourly_hours=0.0,
                project_hours=project_hours_needed,
                system_building_hours=self.SYSTEM_BUILDING_HOURS_PER_WEEK,
                total_billable_hours=project_hours_needed,
                weekly_income=self.min_baseline_income_per_week,
                monthly_income=self.BASELINE_INCOME_PER_MONTH,
                hours_remaining_after_baseline=max(0, remaining_hours),
                business_growth_score=self._calculate_business_growth_score(
                    0.0, 0.0, 0.0, project_hours_needed, self.SYSTEM_BUILDING_HOURS_PER_WEEK
                ),
                meets_baseline=True,
                num_clients_needed=0.0,
                recommendation=recommendation
            ))
        
        # Scenario 3: Minimum hourly + rest for projects
        min_hourly = self.min_baseline_income_per_week / self.baseline_client_1_rate
        if min_hourly <= self.MAX_BILLABLE_HOURS_PER_WEEK:
            remaining_for_projects = self.MAX_BILLABLE_HOURS_PER_WEEK - min_hourly - self.SYSTEM_BUILDING_HOURS_PER_WEEK
            num_clients_min = min_hourly / self.MAX_HOURS_PER_CLIENT_PER_WEEK
            
            recommendation = self._generate_recommendation(
                hourly_hours=min_hourly,
                project_hours=max(0, remaining_for_projects),
                num_clients=num_clients_min,
                remaining_hours=0.0,
                scenario_type="min_hourly_max_project"
            )
            
            scenarios.append(ScenarioAnalysis(
                scenario_name="Min Hourly + Max Projects",
                hourly_hours=min_hourly,
                project_hours=max(0, remaining_for_projects),
                system_building_hours=self.SYSTEM_BUILDING_HOURS_PER_WEEK,
                total_billable_hours=min_hourly + max(0, remaining_for_projects),
                weekly_income=self.min_baseline_income_per_week + (max(0, remaining_for_projects) * self.project_hourly_equivalent),
                monthly_income=(self.min_baseline_income_per_week + (max(0, remaining_for_projects) * self.project_hourly_equivalent)) * self.WEEKS_PER_MONTH,
                hours_remaining_after_baseline=0.0,
                business_growth_score=self._calculate_business_growth_score(
                    min_hourly, 0.0, 0.0, max(0, remaining_for_projects), self.SYSTEM_BUILDING_HOURS_PER_WEEK
                ),
                meets_baseline=True,
                num_clients_needed=num_clients_min,
                recommendation=recommendation
            ))
        
        # Scenario 4: Flexible - 2 clients at min hours each, rest for projects
        num_baseline_clients = 2.0
        client_hours_min = self.MIN_HOURS_PER_CLIENT_PER_WEEK * num_baseline_clients
        income_from_clients = client_hours_min * self.baseline_client_1_rate
        if income_from_clients < self.min_baseline_income_per_week:
            # Need more hours or higher rate
            additional_hours_needed = (self.min_baseline_income_per_week - income_from_clients) / self.baseline_client_1_rate
            total_hourly = client_hours_min + additional_hours_needed
        else:
            total_hourly = client_hours_min
            additional_hours_needed = 0.0
        
        if total_hourly <= self.MAX_BILLABLE_HOURS_PER_WEEK:
            remaining_for_projects = self.MAX_BILLABLE_HOURS_PER_WEEK - total_hourly - self.SYSTEM_BUILDING_HOURS_PER_WEEK
            meets_baseline = (total_hourly * self.baseline_client_1_rate) >= self.min_baseline_income_per_week
            
            recommendation = self._generate_recommendation(
                hourly_hours=total_hourly,
                project_hours=max(0, remaining_for_projects),
                num_clients=num_baseline_clients,
                remaining_hours=0.0,
                scenario_type="fixed_clients",
                meets_baseline=meets_baseline,
                hours_per_client=total_hourly / num_baseline_clients
            )
            
            scenarios.append(ScenarioAnalysis(
                scenario_name=f"{int(num_baseline_clients)} Clients ({self.MIN_HOURS_PER_CLIENT_PER_WEEK}-{self.MAX_HOURS_PER_CLIENT_PER_WEEK}hrs each) + Projects",
                hourly_hours=total_hourly,
                project_hours=max(0, remaining_for_projects),
                system_building_hours=self.SYSTEM_BUILDING_HOURS_PER_WEEK,
                total_billable_hours=total_hourly + max(0, remaining_for_projects),
                weekly_income=(total_hourly * self.baseline_client_1_rate) + (max(0, remaining_for_projects) * self.project_hourly_equivalent),
                monthly_income=((total_hourly * self.baseline_client_1_rate) + (max(0, remaining_for_projects) * self.project_hourly_equivalent)) * self.WEEKS_PER_MONTH,
                hours_remaining_after_baseline=0.0,
                business_growth_score=self._calculate_business_growth_score(
                    total_hourly, 0.0, 0.0, max(0, remaining_for_projects), self.SYSTEM_BUILDING_HOURS_PER_WEEK
                ),
                meets_baseline=meets_baseline,
                num_clients_needed=num_baseline_clients,
                recommendation=recommendation
            ))
        
        return scenarios
    
    def _generate_recommendation(
        self,
        hourly_hours: float,
        project_hours: float,
        num_clients: float,
        remaining_hours: float,
        scenario_type: str,
        meets_baseline: bool = True,
        hours_per_client: Optional[float] = None
    ) -> str:
        """
        Dynamically generate recommendation text based on calculated values.
        
        No hardcoded strings - everything is calculated from parameters.
        """
        if scenario_type == "all_hourly":
            if num_clients > 0:
                hours_per_client_calc = hourly_hours / num_clients if num_clients > 0 else 0
                if remaining_hours > 0:
                    return f"Need {num_clients:.1f} clients at {hours_per_client_calc:.1f} hrs/week each, or fewer clients with more hours. Leaves {remaining_hours:.1f} hrs for growth work."
                else:
                    return f"Need {num_clients:.1f} clients at {hours_per_client_calc:.1f} hrs/week each. No hours remaining for growth work."
            else:
                return f"Requires {hourly_hours:.1f} hrs/week of hourly work. Leaves {remaining_hours:.1f} hrs for growth work."
        
        elif scenario_type == "all_project":
            if remaining_hours > 0:
                return f"Uses {project_hours:.1f} hrs/week for projects. Leaves {remaining_hours:.1f} hrs for additional projects/system building."
            else:
                return f"Uses {project_hours:.1f} hrs/week for projects. No additional hours available."
        
        elif scenario_type == "min_hourly_max_project":
            if project_hours > 0:
                return f"{hourly_hours:.1f} hrs hourly ({num_clients:.1f} clients), {project_hours:.1f} hrs projects. Optimal balance for growth."
            else:
                return f"{hourly_hours:.1f} hrs hourly ({num_clients:.1f} clients). No hours available for projects."
        
        elif scenario_type == "fixed_clients":
            if hours_per_client is None:
                hours_per_client = hourly_hours / num_clients if num_clients > 0 else 0
            
            baseline_status = "Meets baseline" if meets_baseline else "May need more hours or higher rate"
            if project_hours > 0:
                return f"{int(num_clients)} clients at {hours_per_client:.1f} hrs/week each, {project_hours:.1f} hrs for projects. {baseline_status}."
            else:
                return f"{int(num_clients)} clients at {hours_per_client:.1f} hrs/week each. {baseline_status}. No hours available for projects."
        
        else:
            return f"Hourly: {hourly_hours:.1f} hrs, Projects: {project_hours:.1f} hrs"
    
    def print_scenario_analysis(self, scenarios: List[ScenarioAnalysis]):
        """Print a comprehensive scenario analysis."""
        print("\n" + "="*70)
        print("SCENARIO ANALYSIS: Finding Your Optimal Strategy")
        print("="*70)
        
        print(f"\n🎯 BASELINE REQUIREMENTS:")
        print(f"   Target Income:      ${self.BASELINE_INCOME_PER_MONTH:,.2f}/month")
        print(f"   Weekly Target:      ${self.min_baseline_income_per_week:,.2f}/week")
        print(f"   Min Hours @ $40/hr: {self.min_hours_at_40:.1f} hrs/week")
        print(f"   System Building:    {self.SYSTEM_BUILDING_HOURS_PER_WEEK} hrs/week (FIXED)")
        print(f"   Max Billable:       {self.MAX_BILLABLE_HOURS_PER_WEEK} hrs/week")
        
        print(f"\n📊 SCENARIO COMPARISON:")
        print("-" * 70)
        
        for i, scenario in enumerate(scenarios, 1):
            status_icon = "✅" if scenario.meets_baseline else "⚠️"
            growth_icon = "🚀" if scenario.business_growth_score >= 0.6 else "📈" if scenario.business_growth_score >= 0.4 else "📉"
            
            print(f"\n{status_icon} SCENARIO {i}: {scenario.scenario_name}")
            print(f"   Hourly Work:        {scenario.hourly_hours:.1f} hrs/week")
            if scenario.num_clients_needed > 0:
                print(f"   Clients Needed:     {scenario.num_clients_needed:.1f} clients")
            print(f"   Project Work:       {scenario.project_hours:.1f} hrs/week")
            print(f"   System Building:    {scenario.system_building_hours:.1f} hrs/week")
            print(f"   Total Billable:     {scenario.total_billable_hours:.1f} hrs/week")
            print(f"   Monthly Income:     ${scenario.monthly_income:,.2f}")
            print(f"   {growth_icon} Growth Score:      {scenario.business_growth_score:.3f}/1.0")
            if scenario.hours_remaining_after_baseline > 0:
                print(f"   Hours Remaining:    {scenario.hours_remaining_after_baseline:.1f} hrs for growth")
            print(f"   💡 {scenario.recommendation}")
        
        # Find best scenario
        if scenarios:
            best_growth = max(scenarios, key=lambda s: s.business_growth_score if s.meets_baseline else 0)
            print(f"\n🏆 RECOMMENDED STRATEGY:")
            print(f"   {best_growth.scenario_name}")
            print(f"   {best_growth.recommendation}")
            print(f"   Growth Score: {best_growth.business_growth_score:.3f}/1.0")
        
        print("="*70 + "\n")
    
    def plan_growth_trajectory(
        self,
        start_month: str = "December",
        start_income: float = 5000.0,
        target_month: str = "November",
        target_income: float = 100000.0,
        months_to_target: int = 12,
        growth_type: str = "exponential"  # "exponential" or "linear"
    ) -> List[MonthlyGrowthPlan]:
        """
        Plan growth trajectory from start to target income.
        
        Strategy: Start with easiest mix (more hourly), gradually replace with
        higher-value work (projects, better rates) as business compounds.
        
        Args:
            start_month: Starting month name
            start_income: Starting monthly income
            target_month: Target month name
            target_income: Target monthly income
            months_to_target: Number of months to reach target
            growth_type: "exponential" (compounding) or "linear" (steady)
        """
        plans = []
        
        # Calculate monthly targets
        if growth_type == "exponential":
            # Exponential growth: r = (target/start)^(1/months) - 1
            growth_rate = (target_income / start_income) ** (1.0 / months_to_target) - 1.0
            monthly_targets = [
                start_income * ((1 + growth_rate) ** month)
                for month in range(months_to_target + 1)
            ]
        else:
            # Linear growth
            monthly_increase = (target_income - start_income) / months_to_target
            monthly_targets = [
                start_income + (monthly_increase * month)
                for month in range(months_to_target + 1)
            ]
        
        # Month names
        month_names = [
            "December", "January", "February", "March", "April", "May",
            "June", "July", "August", "September", "October", "November", "December"
        ]
        
        # Starting strategy: easiest mix (more hourly, less project)
        # Gradually shift to more project work and higher rates
        current_hourly_rate = self.baseline_client_1_rate
        current_project_rate = self.project_hourly_equivalent
        
        for month_idx, target in enumerate(monthly_targets):
            month_name = month_names[month_idx % len(month_names)]
            
            # Calculate weekly target
            weekly_target = target / self.WEEKS_PER_MONTH
            
            # Strategy evolution: early months = more hourly (easier), later = more project (compounds)
            # Month 0-3: 70% hourly, 30% project
            # Month 4-7: 50% hourly, 50% project  
            # Month 8-11: 30% hourly, 70% project
            if month_idx <= 3:
                hourly_pct = 0.70
                project_pct = 0.30
                strategy_phase = "Foundation (Easy Mix)"
                replacement = "Replace low-rate hourly with project work"
            elif month_idx <= 7:
                hourly_pct = 0.50
                project_pct = 0.50
                strategy_phase = "Transition (Balanced)"
                replacement = "Replace hourly clients with higher-rate projects"
            else:
                hourly_pct = 0.30
                project_pct = 0.70
                strategy_phase = "Scale (Project-Focused)"
                replacement = "Replace remaining hourly with premium projects/agency work"
            
            # Rate progression: increase rates as you get better clients/projects
            rate_multiplier = 1.0 + (month_idx * 0.05)  # 5% increase per month
            month_hourly_rate = current_hourly_rate * rate_multiplier
            month_project_rate = current_project_rate * rate_multiplier
            
            # Calculate hours needed
            # Total available: 50 billable - 8 system building = 42 hours
            available_hours = self.MAX_BILLABLE_HOURS_PER_WEEK - self.SYSTEM_BUILDING_HOURS_PER_WEEK
            
            # Try to hit target with this mix
            hourly_hours = available_hours * hourly_pct
            project_hours = available_hours * project_pct
            
            # Calculate income from this mix
            weekly_income = (hourly_hours * month_hourly_rate) + (project_hours * month_project_rate)
            monthly_income = weekly_income * self.WEEKS_PER_MONTH
            
            # If below target, adjust (prioritize projects for growth)
            if monthly_income < target:
                # Increase project hours (better for growth)
                additional_needed = (target - monthly_income) / self.WEEKS_PER_MONTH
                additional_project_hours = additional_needed / month_project_rate
                
                # Can we take from hourly?
                if hourly_hours >= additional_project_hours:
                    hourly_hours -= additional_project_hours
                    project_hours += additional_project_hours
                else:
                    # Need more hours - increase project hours
                    project_hours += additional_project_hours
                    # Cap at max
                    total = hourly_hours + project_hours
                    if total > available_hours:
                        project_hours = available_hours - hourly_hours
                
                # Recalculate
                weekly_income = (hourly_hours * month_hourly_rate) + (project_hours * month_project_rate)
                monthly_income = weekly_income * self.WEEKS_PER_MONTH
            
            # Calculate number of clients
            num_clients = hourly_hours / self.MAX_HOURS_PER_CLIENT_PER_WEEK if hourly_hours > 0 else 0.0
            
            # Calculate growth score
            growth_score = self._calculate_business_growth_score(
                hourly_hours, 0.0, 0.0, project_hours, self.SYSTEM_BUILDING_HOURS_PER_WEEK
            )
            
            plans.append(MonthlyGrowthPlan(
                month=month_name,
                month_number=month_idx,
                target_income=target,
                hourly_hours=round(hourly_hours, 1),
                project_hours=round(project_hours, 1),
                system_building_hours=self.SYSTEM_BUILDING_HOURS_PER_WEEK,
                hourly_rate=round(month_hourly_rate, 0),
                project_rate=round(month_project_rate, 0),
                num_clients=round(num_clients, 1),
                weekly_income=round(weekly_income, 2),
                monthly_income=round(monthly_income, 2),
                growth_score=round(growth_score, 3),
                strategy=strategy_phase,
                replacement_opportunity=replacement
            ))
        
        return plans
    
    def print_growth_trajectory(self, plans: List[MonthlyGrowthPlan]):
        """Print the growth trajectory plan."""
        print("\n" + "="*80)
        print("GROWTH TRAJECTORY: From Foundation to Scale")
        print("="*80)
        
        print(f"\n🎯 GOAL:")
        print(f"   Start:     ${plans[0].target_income:,.0f}/month ({plans[0].month})")
        print(f"   Target:    ${plans[-1].target_income:,.0f}/month ({plans[-1].month})")
        print(f"   Timeline:  {len(plans)-1} months")
        print(f"   Growth:    {((plans[-1].target_income / plans[0].target_income) - 1) * 100:.0f}% increase")
        
        print(f"\n📅 MONTHLY BREAKDOWN:")
        print("-" * 80)
        
        for plan in plans:
            status = "✅" if plan.monthly_income >= plan.target_income * 0.95 else "⚠️"
            growth_icon = "🚀" if plan.growth_score >= 0.6 else "📈" if plan.growth_score >= 0.4 else "📉"
            
            print(f"\n{status} {plan.month} (Month {plan.month_number})")
            print(f"   Target Income:      ${plan.target_income:,.0f}/month")
            print(f"   Projected Income:    ${plan.monthly_income:,.0f}/month")
            print(f"   Strategy Phase:     {plan.strategy}")
            print(f"   ────────────────────────────────────────────────────────────")
            print(f"   Hourly Work:         {plan.hourly_hours:.1f} hrs/week @ ${plan.hourly_rate:.0f}/hr")
            print(f"   Project Work:        {plan.project_hours:.1f} hrs/week @ ${plan.project_rate:.0f}/hr equiv")
            print(f"   System Building:     {plan.system_building_hours:.1f} hrs/week")
            if plan.num_clients > 0:
                print(f"   Clients Needed:      {plan.num_clients:.1f} clients")
            print(f"   {growth_icon} Growth Score:        {plan.growth_score:.3f}/1.0")
            print(f"   💡 This Month:        {plan.replacement_opportunity}")
        
        print(f"\n📊 KEY MILESTONES:")
        milestones = [
            (3, "Q1 Complete - Foundation Established"),
            (6, "Mid-Year - Transition Phase"),
            (9, "Q3 Complete - Scaling Phase"),
            (12, "Year Complete - Target Achieved")
        ]
        
        for month_num, milestone in milestones:
            if month_num < len(plans):
                plan = plans[month_num]
                print(f"   Month {month_num}: ${plan.monthly_income:,.0f}/month - {milestone}")
        
        print("="*80 + "\n")
    
    def get_december_starting_plan(self) -> MonthlyGrowthPlan:
        """
        Get the easiest starting plan for December (5K target).
        Focuses on easiest mix to achieve: more hourly, less project.
        """
        december_target = 5000.0
        weekly_target = december_target / self.WEEKS_PER_MONTH
        
        # Easiest mix: 70% hourly, 30% project (hourly is easier to get)
        available_hours = self.MAX_BILLABLE_HOURS_PER_WEEK - self.SYSTEM_BUILDING_HOURS_PER_WEEK
        hourly_hours = available_hours * 0.70
        project_hours = available_hours * 0.30
        
        # Calculate with current rates
        weekly_income = (hourly_hours * self.baseline_client_1_rate) + (project_hours * self.project_hourly_equivalent)
        monthly_income = weekly_income * self.WEEKS_PER_MONTH
        
        # Adjust if needed
        if monthly_income < december_target:
            additional = (december_target - monthly_income) / self.WEEKS_PER_MONTH
            additional_hours = additional / self.baseline_client_1_rate
            hourly_hours += additional_hours
            if hourly_hours + project_hours > available_hours:
                hourly_hours = available_hours - project_hours
        
        weekly_income = (hourly_hours * self.baseline_client_1_rate) + (project_hours * self.project_hourly_equivalent)
        monthly_income = weekly_income * self.WEEKS_PER_MONTH
        num_clients = hourly_hours / self.MAX_HOURS_PER_CLIENT_PER_WEEK
        
        growth_score = self._calculate_business_growth_score(
            hourly_hours, 0.0, 0.0, project_hours, self.SYSTEM_BUILDING_HOURS_PER_WEEK
        )
        
        return MonthlyGrowthPlan(
            month="December",
            month_number=0,
            target_income=december_target,
            hourly_hours=round(hourly_hours, 1),
            project_hours=round(project_hours, 1),
            system_building_hours=self.SYSTEM_BUILDING_HOURS_PER_WEEK,
            hourly_rate=self.baseline_client_1_rate,
            project_rate=self.project_hourly_equivalent,
            num_clients=round(num_clients, 1),
            weekly_income=round(weekly_income, 2),
            monthly_income=round(monthly_income, 2),
            growth_score=round(growth_score, 3),
            strategy="Foundation (Easiest Mix - Start Here)",
            replacement_opportunity="Focus on getting stable hourly clients first, then add 1-2 small projects"
        )
    
    def print_allocation(self, result: OptimizationResult):
        """Print a human-readable allocation report."""
        print("\n" + "="*60)
        print("WORK ALLOCATION OPTIMIZATION RESULTS")
        print("="*60)
        print(f"\n📊 WEEKLY ALLOCATION:")
        print(f"   Baseline Client 1: {result.baseline_client_1_hours:.1f} hrs/week")
        print(f"   Baseline Client 2: {result.baseline_client_2_hours:.1f} hrs/week")
        print(f"   System Building:   {result.system_building_hours:.1f} hrs/week (FIXED)")
        print(f"   High-Rate Hourly:  {result.high_rate_hours:.1f} hrs/week")
        print(f"   Project Work:      {result.project_hours:.1f} hrs/week")
        print(f"   ────────────────────────────────────────")
        print(f"   Total Billable:    {result.total_billable_hours:.1f} hrs/week")
        print(f"   Total Hours:       {result.total_billable_hours + result.system_building_hours:.1f} hrs/week")
        
        print(f"\n💰 INCOME PROJECTION:")
        print(f"   Weekly Income:     ${result.weekly_income:,.2f}")
        print(f"   Monthly Income:    ${result.monthly_income:,.2f}")
        print(f"   Baseline Target:   ${self.BASELINE_INCOME_PER_MONTH:,.2f}")
        print(f"   Status:            {'✅ MEETS TARGET' if result.monthly_income >= self.BASELINE_INCOME_PER_MONTH else '❌ BELOW TARGET'}")
        
        print(f"\n🚀 BUSINESS GROWTH SCORE: {result.business_growth_score:.3f}/1.0")
        growth_percentage = result.business_growth_score * 100
        if growth_percentage >= 0.7:
            print(f"   Status: ✅ EXCELLENT - Strong focus on compounding work")
        elif growth_percentage >= 0.5:
            print(f"   Status: ⚠️  MODERATE - Some growth work, but could improve")
        else:
            print(f"   Status: ❌ LOW - Too much hourly work, not enough business building")
        
        print(f"\n📈 STRATEGIC BREAKDOWN:")
        baseline_pct = ((result.baseline_client_1_hours + result.baseline_client_2_hours) / 
                       (result.total_billable_hours + result.system_building_hours) * 100)
        growth_pct = ((result.system_building_hours + result.project_hours) / 
                     (result.total_billable_hours + result.system_building_hours) * 100)
        print(f"   Baseline Work:     {baseline_pct:.1f}% (pays bills, stable)")
        print(f"   Growth Work:       {growth_pct:.1f}% (builds business, compounds)")
        
        print(f"\n✅ FEASIBILITY: {'FEASIBLE' if result.is_feasible else 'CHECK CONSTRAINTS'}")
        if result.message:
            print(f"   Note: {result.message}")
        print("="*60 + "\n")


def main():
    """
    Example usage of the optimization algorithm.
    
    Run this to see the optimal allocation based on current parameters.
    Shows growth trajectory planning from December to November next year.
    """
    # Initialize optimizer with default rates (40, 40, 50, 40)
    optimizer = WorkAllocationOptimizer()
    
    # Show December starting plan (easiest mix)
    print("\n" + "🎯" * 40)
    print("DECEMBER STARTING PLAN (Easiest Mix to Crack)")
    print("="*80)
    december_plan = optimizer.get_december_starting_plan()
    optimizer.print_growth_trajectory([december_plan])
    
    # Show full growth trajectory
    print("\n" + "🚀" * 40)
    print("12-MONTH GROWTH TRAJECTORY: 5K → 100K")
    print("Strategy: Start easy, replace with better opportunities")
    print("="*80)
    growth_plans = optimizer.plan_growth_trajectory(
        start_month="December",
        start_income=5000.0,
        target_month="November",
        target_income=100000.0,
        months_to_target=12,
        growth_type="exponential"  # Compounding growth
    )
    optimizer.print_growth_trajectory(growth_plans)
    
    return growth_plans, december_plan


if __name__ == "__main__":
    main()

