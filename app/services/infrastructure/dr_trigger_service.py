"""
DR Trigger Service

Monitors simulation data and recommends DR events when conditions warrant.
Provides auto-filled suggestions for community managers to approve.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo
import threading

logger = logging.getLogger(__name__)


class DRRecommendation:
    """Represents a recommended DR event based on detected conditions."""
    
    def __init__(
        self,
        recommendation_id: str,
        trigger_type: str,
        title: str,
        reason: str,
        duration_hours: float,
        target_reduction_pct: float,
        price_signal: float,
        severity: str,
        detected_at: datetime,
        metrics: Dict[str, float]
    ):
        self.recommendation_id = recommendation_id
        self.trigger_type = trigger_type  # peak_demand, grid_stress, peak_hours, low_battery
        self.title = title
        self.reason = reason
        self.duration_hours = duration_hours
        self.target_reduction_pct = target_reduction_pct
        self.price_signal = price_signal
        self.severity = severity  # low, medium, high, critical
        self.detected_at = detected_at
        self.metrics = metrics
        self.dismissed = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "recommendation_id": self.recommendation_id,
            "trigger_type": self.trigger_type,
            "title": self.title,
            "reason": self.reason,
            "duration_hours": self.duration_hours,
            "target_reduction_pct": self.target_reduction_pct,
            "price_signal": self.price_signal,
            "severity": self.severity,
            "detected_at": self.detected_at.isoformat(),
            "metrics": self.metrics,
            "dismissed": self.dismissed
        }


class DRTriggerService:
    """
    Service that monitors simulation data and recommends DR events.
    
    Checks conditions every hour and generates recommendations for managers.
    Does NOT auto-create events - requires manager approval.
    """
    
    def __init__(self):
        """Initialize the DR trigger service."""
        self._recommendations: List[DRRecommendation] = []
        self._lock = threading.Lock()
        self._last_check: Optional[datetime] = None
        self._cooldown_until: Optional[datetime] = None  # Prevent spam
        
        # Configurable thresholds
        self.config = {
            # Peak demand trigger
            "peak_demand_threshold": 1.5,  # Consumption > 1.5x generation
            "peak_demand_reduction": 0.25,  # 25% reduction
            "peak_demand_duration": 2.0,    # 2 hours
            "peak_demand_price": 0.20,      # $0.20/kWh
            
            # Grid stress trigger
            "grid_import_threshold": 50.0,   # > 50 kW import
            "grid_stress_reduction": 0.20,   # 20% reduction
            "grid_stress_duration": 1.5,     # 1.5 hours
            "grid_stress_price": 0.18,       # $0.18/kWh
            
            # Peak hours trigger
            "peak_hours_start": 17,          # 5 PM
            "peak_hours_end": 21,            # 9 PM
            "peak_hours_reduction": 0.15,    # 15% reduction
            "peak_hours_duration": 3.0,      # 3 hours
            "peak_hours_price": 0.15,        # $0.15/kWh
            
            # Low battery trigger
            "low_battery_threshold": 0.20,   # < 20% average SOC
            "low_battery_reduction": 0.20,   # 20% reduction
            "low_battery_duration": 2.0,     # 2 hours
            "low_battery_price": 0.15,       # $0.15/kWh
            
            # Stability trigger
            "stability_threshold": 70.0,     # < 70 stability index
            "stability_reduction": 0.25,     # 25% reduction
            "stability_duration": 1.0,       # 1 hour
            "stability_price": 0.25,         # $0.25/kWh (critical)
            
            # General
            "cooldown_minutes": 120,         # 2 hours between recommendations
            "max_active_recommendations": 3  # Max recommendations at once
        }
        
        logger.info("DRTriggerService initialized")
    
    def check_conditions(
        self,
        simulation_result: Dict[str, Any],
        current_time: datetime
    ) -> Optional[DRRecommendation]:
        """
        Check if current conditions warrant a DR event recommendation.
        
        Args:
            simulation_result: Current community simulation result
            current_time: Current time
            
        Returns:
            DRRecommendation if conditions met, None otherwise
        """
        self._last_check = current_time
        
        # Check cooldown
        if self._cooldown_until and current_time < self._cooldown_until:
            logger.debug(f"In cooldown until {self._cooldown_until}, skipping trigger check")
            return None
        
        # Check if we already have too many active recommendations
        with self._lock:
            active_count = len([r for r in self._recommendations if not r.dismissed])
            if active_count >= self.config["max_active_recommendations"]:
                logger.debug(f"Max active recommendations ({active_count}) reached, skipping")
                return None
        
        # Check each trigger condition (in priority order)
        recommendation = None
        
        # 1. CRITICAL: Grid stability
        recommendation = self._check_stability_trigger(simulation_result, current_time)
        if recommendation and recommendation.severity == "critical":
            return self._add_recommendation(recommendation, current_time)
        
        # 2. HIGH: Peak demand
        if not recommendation:
            recommendation = self._check_peak_demand_trigger(simulation_result, current_time)
        
        # 3. MEDIUM: Grid stress
        if not recommendation:
            recommendation = self._check_grid_stress_trigger(simulation_result, current_time)
        
        # 4. MEDIUM: Low battery
        if not recommendation:
            recommendation = self._check_low_battery_trigger(simulation_result, current_time)
        
        # 5. LOW: Peak hours
        if not recommendation:
            recommendation = self._check_peak_hours_trigger(simulation_result, current_time)
        
        if recommendation:
            return self._add_recommendation(recommendation, current_time)
        
        return None
    
    def _check_peak_demand_trigger(
        self,
        result: Dict[str, Any],
        current_time: datetime
    ) -> Optional[DRRecommendation]:
        """Check if consumption significantly exceeds generation."""
        consumption = result.get("total_consumption_kw", 0)
        generation = result.get("total_generation_kw", 0)
        
        if generation == 0:
            return None
        
        ratio = consumption / generation
        threshold = self.config["peak_demand_threshold"]
        
        if ratio > threshold:
            severity = "critical" if ratio > 2.0 else "high"
            
            return DRRecommendation(
                recommendation_id=f"peak_demand_{int(current_time.timestamp())}",
                trigger_type="peak_demand",
                title="Peak Demand Alert",
                reason=f"Consumption is {ratio:.1f}x higher than generation. Grid import at {result.get('total_grid_import_kw', 0):.1f} kW.",
                duration_hours=self.config["peak_demand_duration"],
                target_reduction_pct=self.config["peak_demand_reduction"],
                price_signal=self.config["peak_demand_price"],
                severity=severity,
                detected_at=current_time,
                metrics={
                    "consumption_kw": consumption,
                    "generation_kw": generation,
                    "ratio": ratio,
                    "grid_import_kw": result.get("total_grid_import_kw", 0)
                }
            )
        
        return None
    
    def _check_grid_stress_trigger(
        self,
        result: Dict[str, Any],
        current_time: datetime
    ) -> Optional[DRRecommendation]:
        """Check if grid import is too high."""
        grid_import = result.get("total_grid_import_kw", 0)
        threshold = self.config["grid_import_threshold"]
        
        if grid_import > threshold:
            severity = "critical" if grid_import > threshold * 2 else "high"
            
            return DRRecommendation(
                recommendation_id=f"grid_stress_{int(current_time.timestamp())}",
                trigger_type="grid_stress",
                title="High Grid Import",
                reason=f"Community importing {grid_import:.1f} kW from grid. Reduce demand to lower costs and grid dependency.",
                duration_hours=self.config["grid_stress_duration"],
                target_reduction_pct=self.config["grid_stress_reduction"],
                price_signal=self.config["grid_stress_price"],
                severity=severity,
                detected_at=current_time,
                metrics={
                    "grid_import_kw": grid_import,
                    "threshold": threshold,
                    "consumption_kw": result.get("total_consumption_kw", 0),
                    "generation_kw": result.get("total_generation_kw", 0)
                }
            )
        
        return None
    
    def _check_peak_hours_trigger(
        self,
        result: Dict[str, Any],
        current_time: datetime
    ) -> Optional[DRRecommendation]:
        """Check if we're in peak hours (evening)."""
        hour = current_time.hour
        start_hour = self.config["peak_hours_start"]
        end_hour = self.config["peak_hours_end"]
        
        # Only trigger at the start of peak hours
        if hour == start_hour:
            consumption = result.get("total_consumption_kw", 0)
            
            return DRRecommendation(
                recommendation_id=f"peak_hours_{current_time.date().isoformat()}",
                trigger_type="peak_hours",
                title="Evening Peak Hours",
                reason=f"Entering peak demand period ({start_hour}:00-{end_hour}:00). Reduce consumption during high-cost hours.",
                duration_hours=self.config["peak_hours_duration"],
                target_reduction_pct=self.config["peak_hours_reduction"],
                price_signal=self.config["peak_hours_price"],
                severity="medium",
                detected_at=current_time,
                metrics={
                    "hour": hour,
                    "consumption_kw": consumption,
                    "peak_hours_start": start_hour,
                    "peak_hours_end": end_hour
                }
            )
        
        return None
    
    def _check_low_battery_trigger(
        self,
        result: Dict[str, Any],
        current_time: datetime
    ) -> Optional[DRRecommendation]:
        """Check if battery storage is critically low."""
        avg_soc = result.get("storage_avg_soc", 1.0)
        threshold = self.config["low_battery_threshold"]
        
        if avg_soc < threshold:
            severity = "critical" if avg_soc < 0.1 else "high"
            
            return DRRecommendation(
                recommendation_id=f"low_battery_{int(current_time.timestamp())}",
                trigger_type="low_battery",
                title="Low Battery Storage",
                reason=f"Community battery storage at {avg_soc*100:.0f}%. Reduce consumption to preserve backup capacity.",
                duration_hours=self.config["low_battery_duration"],
                target_reduction_pct=self.config["low_battery_reduction"],
                price_signal=self.config["low_battery_price"],
                severity=severity,
                detected_at=current_time,
                metrics={
                    "avg_soc": avg_soc,
                    "threshold": threshold,
                    "consumption_kw": result.get("total_consumption_kw", 0)
                }
            )
        
        return None
    
    def _check_stability_trigger(
        self,
        result: Dict[str, Any],
        current_time: datetime
    ) -> Optional[DRRecommendation]:
        """Check if grid stability is at risk."""
        # Get stability metrics from simulation
        stability_index = result.get("total_grid_stability_index", 100.0)
        threshold = self.config["stability_threshold"]
        
        if stability_index < threshold:
            severity = "critical" if stability_index < 50 else "high"
            
            return DRRecommendation(
                recommendation_id=f"stability_{int(current_time.timestamp())}",
                trigger_type="grid_stability",
                title="Grid Stability Risk",
                reason=f"Grid stability index at {stability_index:.0f}. Immediate demand reduction needed to prevent issues.",
                duration_hours=self.config["stability_duration"],
                target_reduction_pct=self.config["stability_reduction"],
                price_signal=self.config["stability_price"],
                severity=severity,
                detected_at=current_time,
                metrics={
                    "stability_index": stability_index,
                    "threshold": threshold,
                    "grid_frequency_hz": result.get("total_grid_frequency_hz", 0),
                    "grid_voltage_v": result.get("total_grid_voltage_v", 0)
                }
            )
        
        return None
    
    def _add_recommendation(
        self,
        recommendation: DRRecommendation,
        current_time: datetime
    ) -> DRRecommendation:
        """Add recommendation and set cooldown."""
        with self._lock:
            self._recommendations.append(recommendation)
            
            # Set cooldown
            cooldown_minutes = self.config["cooldown_minutes"]
            self._cooldown_until = current_time + timedelta(minutes=cooldown_minutes)
        
        logger.info(
            f"DR Recommendation created: {recommendation.trigger_type} "
            f"(severity: {recommendation.severity})"
        )
        
        return recommendation
    
    def get_active_recommendations(self) -> List[DRRecommendation]:
        """Get all active (non-dismissed) recommendations."""
        with self._lock:
            return [r for r in self._recommendations if not r.dismissed]
    
    def dismiss_recommendation(self, recommendation_id: str) -> bool:
        """Dismiss a recommendation (manager chose not to create event)."""
        with self._lock:
            for rec in self._recommendations:
                if rec.recommendation_id == recommendation_id:
                    rec.dismissed = True
                    logger.info(f"Recommendation {recommendation_id} dismissed")
                    return True
        return False
    
    def clear_old_recommendations(self, current_time: datetime, hours_to_keep: int = 24):
        """Remove old recommendations."""
        cutoff = current_time - timedelta(hours=hours_to_keep)
        
        with self._lock:
            original_count = len(self._recommendations)
            self._recommendations = [
                r for r in self._recommendations
                if r.detected_at > cutoff
            ]
            removed = original_count - len(self._recommendations)
            
            if removed > 0:
                logger.info(f"Cleared {removed} old DR recommendations")


# Global singleton
_trigger_service: Optional[DRTriggerService] = None


def get_trigger_service() -> DRTriggerService:
    """Get the global DR trigger service instance."""
    global _trigger_service
    if _trigger_service is None:
        _trigger_service = DRTriggerService()
    return _trigger_service

