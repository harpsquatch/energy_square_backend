"""
Background Simulation Service

Runs simulation continuously in the background, updating data at regular intervals.
Provides cached simulation data for fast API responses.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo
import threading
from collections import defaultdict

from app.services.infrastructure.model_service import CommunityModelService
from app.services.infrastructure.simulation_engine import CommunitySimulationEngine

logger = logging.getLogger(__name__)


class BackgroundSimulationService:
    """
    Background service that continuously runs simulation and caches results.
    
    Updates simulation data at regular intervals based on the current hour.
    """
    
    def __init__(
        self,
        update_interval_seconds: int = 3600,  # Update every hour
        initial_update: bool = True
    ):
        """
        Initialize background simulation service.
        
        Args:
            update_interval_seconds: How often to update simulation (default: 3600 = 1 hour)
            initial_update: Whether to run initial update immediately
        """
        # Lazy initialization - services will be created when first needed
        self._model_service: Optional[CommunityModelService] = None
        self._simulation_engine: Optional[CommunitySimulationEngine] = None
        
        self.update_interval_seconds = update_interval_seconds
        self._running = False
        self._update_task: Optional[asyncio.Task] = None
        
        # Structured cache for instant API access
        # Organized by timeframe: current, today, this_week, this_month
        self._structured_cache: Dict[str, Any] = {
            "current": None,  # Latest simulation data
            "today": [],      # All hours from midnight to now
            "this_week": [],  # Last 7 days (168 hours)
            "this_month": []  # Last 30 days (720 hours)
        }
        self._cache_lock = threading.Lock()
        
        logger.info(f"BackgroundSimulationService initialized (update_interval: {update_interval_seconds}s)")
        
        # Run initial simulation immediately for instant dashboard data
        if initial_update:
            try:
                logger.info("Running initial simulation for immediate dashboard availability...")
            self._update_simulation_sync()
                logger.info("Initial simulation complete - dashboard data available")
            except Exception as e:
                logger.warning(f"Initial simulation failed (services not ready yet): {e}")
        
        logger.info("Background loop will align to wall-clock hour boundaries")
        logger.info("Historical data will be populated asynchronously in the background")
    
    def _get_model_service(self) -> CommunityModelService:
        """Get or create model service (lazy initialization)."""
        if self._model_service is None:
            try:
                self._model_service = CommunityModelService(watch_for_changes=True)
                logger.info("Model service initialized in background service")
            except Exception as e:
                logger.error(f"Failed to initialize model service in background service: {e}", exc_info=True)
                raise
        return self._model_service
    
    def _get_simulation_engine(self) -> CommunitySimulationEngine:
        """Get or create simulation engine (lazy initialization)."""
        if self._simulation_engine is None:
            try:
                model_service = self._get_model_service()
                self._simulation_engine = CommunitySimulationEngine(model_service=model_service)
                logger.info("Simulation engine initialized in background service")
            except Exception as e:
                logger.error(f"Failed to initialize simulation engine in background service: {e}", exc_info=True)
                raise
        return self._simulation_engine
    
    def _add_to_structured_cache(self, timestamp: datetime, community_data: Dict[str, Any]):
        """
        Add simulation data to structured cache, organizing by timeframe.
        
        Args:
            timestamp: Simulation timestamp (hour boundary)
            community_data: Complete community simulation result including members
        """
        model_service = self._get_model_service()
        model = model_service.get_model()
        if not model:
            return
        
        tz = ZoneInfo(model.community.timezone)
        now = datetime.now(tz)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        today_start = current_hour.replace(hour=0)
        week_start = current_hour - timedelta(days=7)
        month_start = current_hour - timedelta(days=30)
        
        data_point = {
            'timestamp': timestamp.isoformat(),
            'data': community_data
        }
        
        with self._cache_lock:
            # Determine which timeframes this data belongs to
            if timestamp >= today_start:
                # Today's data
                self._structured_cache['today'].append(data_point)
            
            if timestamp >= week_start:
                # This week's data
                self._structured_cache['this_week'].append(data_point)
            
            if timestamp >= month_start:
                # This month's data
                self._structured_cache['this_month'].append(data_point)
            
            # Cleanup: Remove old data outside timeframes
            self._structured_cache['today'] = [
                d for d in self._structured_cache['today']
                if datetime.fromisoformat(d['timestamp']) >= today_start
            ]
            self._structured_cache['this_week'] = [
                d for d in self._structured_cache['this_week']
                if datetime.fromisoformat(d['timestamp']) >= week_start
            ]
            self._structured_cache['this_month'] = [
                d for d in self._structured_cache['this_month']
                if datetime.fromisoformat(d['timestamp']) >= month_start
            ]
    
    def start(self):
        """Start the background simulation task."""
        if self._running:
            logger.warning("Background simulation service is already running")
            return
        
        self._running = True
        # Create async task for background updates
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._update_task = asyncio.create_task(self._background_update_loop())
                # Start historical data population in background
                asyncio.create_task(self._pre_populate_history())
            else:
                # If no event loop is running, we'll start it when the loop exists
                loop.run_until_complete(self._start_background_loop())
        except RuntimeError:
            # No event loop exists yet, will be started by FastAPI
            pass
        
        logger.info("Background simulation service started")
    
    async def _start_background_loop(self):
        """Start the background loop in an async context."""
        self._update_task = asyncio.create_task(self._background_update_loop())
        asyncio.create_task(self._pre_populate_history())
    
    def stop(self):
        """Stop the background simulation task."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            logger.info("Background simulation service stopped")
    
    async def _pre_populate_history(self):
        """
        Pre-populate cache with historical simulation data.
        Runs in background to avoid blocking startup.
        
        Populates:
        - Today's past hours (midnight to now)
        - Last 7 days (168 hours)
        - Last 30 days (720 hours)
        """
        try:
            logger.info("Starting historical data population in background...")
            
            # Small delay to ensure initial simulation completes
            await asyncio.sleep(1)
            
            model_service = self._get_model_service()
            model = model_service.get_model()
            if model is None:
                logger.warning("Model not loaded, skipping historical data population")
                return
            
            tz = ZoneInfo(model.community.timezone)
            now = datetime.now(tz)
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            
            # Phase 1: Today's past hours (midnight to current hour)
            logger.info("Phase 1/3: Populating today's past hours...")
            today_start = current_hour.replace(hour=0)
            today_hours = []
            hour = today_start
            while hour < current_hour:
                today_hours.append(hour)
                hour += timedelta(hours=1)
            
            logger.info(f"Simulating {len(today_hours)} hours for today...")
            await self._simulate_hours_batch(today_hours, batch_size=6)
            logger.info(f"Today's data complete ({len(today_hours)} hours)")
            
            # Phase 2: Last 7 days (168 hours)
            logger.info("Phase 2/3: Populating last 7 days...")
            week_start = current_hour - timedelta(days=7)
            week_hours = []
            hour = week_start
            while hour < today_start:
                week_hours.append(hour)
                hour += timedelta(hours=1)
            
            logger.info(f"Simulating {len(week_hours)} hours for last 7 days...")
            await self._simulate_hours_batch(week_hours, batch_size=12)
            logger.info(f"Last 7 days complete ({len(week_hours)} hours)")
            
            # Phase 3: Last 30 days (720 hours)
            logger.info("Phase 3/3: Populating last 30 days...")
            month_start = current_hour - timedelta(days=30)
            month_hours = []
            hour = month_start
            while hour < week_start:
                month_hours.append(hour)
                hour += timedelta(hours=1)
            
            logger.info(f"Simulating {len(month_hours)} hours for last 30 days...")
            await self._simulate_hours_batch(month_hours, batch_size=24)
            logger.info(f"Last 30 days complete ({len(month_hours)} hours)")
            
            logger.info("Historical data population complete!")
            logger.info(f"Total hours simulated: {len(today_hours) + len(week_hours) + len(month_hours)}")
            
        except Exception as e:
            logger.error(f"Error populating historical data: {e}", exc_info=True)
    
    async def _simulate_hours_batch(self, hours: list, batch_size: int = 12):
        """
        Simulate multiple hours in batches to avoid overwhelming the system.
        
        Args:
            hours: List of datetime objects representing hours to simulate
            batch_size: Number of hours to simulate in parallel
        """
        loop = asyncio.get_event_loop()
        
        for i in range(0, len(hours), batch_size):
            batch = hours[i:i + batch_size]
            
            # Run batch in parallel using thread pool
            tasks = [
                loop.run_in_executor(None, self._simulate_single_hour, hour)
                for hour in batch
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Small delay between batches to avoid CPU spikes
            if i + batch_size < len(hours):
                await asyncio.sleep(0.1)
    
    def _simulate_single_hour(self, hour: datetime):
        """
        Simulate a single hour and store in structured cache.
        
        Args:
            hour: Hour to simulate (datetime with minute=0, second=0)
        """
        try:
            simulation_engine = self._get_simulation_engine()
            # Historical simulations should NOT apply demand response events
            community_result = simulation_engine.simulate_community(hour, apply_demand_response=False)
            
            if community_result:
                # Add to structured cache
                self._add_to_structured_cache(hour, community_result)
                
        except Exception as e:
            logger.debug(f"Error simulating hour {hour}: {e}")
    
    async def _background_update_loop(self):
        """
        Background loop that updates simulation at regular intervals.
        Aligns to wall-clock hour boundaries for deterministic timing.
        """
        try:
            # Get timezone from model
            model_service = self._get_model_service()
            model = model_service.get_model()
            if model is None:
                logger.error("Model not loaded, cannot start background simulation loop")
                return
            
            tz = ZoneInfo(model.community.timezone)
            logger.info(f"Background simulation loop starting (timezone: {model.community.timezone})")
            
            # Calculate time until next hour boundary
            now = datetime.now(tz)
            next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            seconds_until_next_hour = (next_hour - now).total_seconds()
            
            logger.info(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"Next simulation will run at: {next_hour.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"Waiting {seconds_until_next_hour:.1f} seconds until next hour boundary...")
            
            # Wait until next hour boundary
            await asyncio.sleep(seconds_until_next_hour)
            
        except Exception as e:
            logger.error(f"Error calculating initial wait time: {e}", exc_info=True)
            # Fall back to immediate start if calculation fails
            pass
        
        # Main simulation loop - runs on exact hour boundaries
        while self._running:
            try:
                # Update simulation at current hour
                await self._update_simulation()
                
                # Calculate time until next hour boundary
                # This ensures we stay aligned even if simulation takes time
                model_service = self._get_model_service()
                model = model_service.get_model()
                if model:
                    tz = ZoneInfo(model.community.timezone)
                    now = datetime.now(tz)
                    next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                    seconds_until_next_hour = (next_hour - now).total_seconds()
                    
                    # Ensure we wait at least 1 second to avoid tight loops
                    if seconds_until_next_hour < 1:
                        seconds_until_next_hour = 3600  # Full hour if we're already past the boundary
                    
                    logger.info(f"Next simulation at {next_hour.strftime('%Y-%m-%d %H:%M:%S %Z')} "
                               f"(waiting {seconds_until_next_hour:.1f}s)")
                    
                    await asyncio.sleep(seconds_until_next_hour)
                else:
                    # Fallback to fixed interval if model unavailable
                await asyncio.sleep(self.update_interval_seconds)
                
            except asyncio.CancelledError:
                logger.info("Background simulation update loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in background simulation update: {e}", exc_info=True)
                # Wait a bit before retrying
                await asyncio.sleep(60)  # Retry after 1 minute on error
    
    async def _update_simulation(self):
        """Update simulation data asynchronously."""
        # Run simulation in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._update_simulation_sync)
    
    def _update_simulation_sync(self):
        """Update simulation data synchronously (called from thread pool)."""
        try:
            model_service = self._get_model_service()
            model = model_service.get_model()
            if model is None:
                logger.warning("Model not loaded, skipping simulation update")
                return
            
            # Get current time (rounded to current hour)
            now = datetime.now(ZoneInfo(model.community.timezone))
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            
            # Skip if we already have data for this hour
            with self._cache_lock:
                current_cached = self._structured_cache.get('current')
                if current_cached and current_cached.get('timestamp'):
                    cached_ts = datetime.fromisoformat(current_cached['timestamp'])
                    if cached_ts.replace(minute=0, second=0, microsecond=0) == current_hour:
                    logger.debug(f"Simulation data already cached for {current_hour}")
                    return
            
            logger.info(f"Updating simulation for {current_hour}")
            
            # Run community simulation
            simulation_engine = self._get_simulation_engine()
            community_result = simulation_engine.simulate_community(current_hour)
            
            # Update structured cache
            with self._cache_lock:
                # Set as current data
                self._structured_cache['current'] = {
                    'timestamp': current_hour.isoformat(),
                    'data': community_result
                }
            
            # Add to historical timeframes
            self._add_to_structured_cache(current_hour, community_result)
            
            # Check for DR trigger conditions
            try:
                from app.services.infrastructure.dr_trigger_service import get_trigger_service
                trigger_service = get_trigger_service()
                recommendation = trigger_service.check_conditions(community_result, current_hour)
                if recommendation:
                    logger.info(f"DR Recommendation generated: {recommendation.trigger_type} ({recommendation.severity})")
            except Exception as e:
                logger.debug(f"Could not check DR triggers: {e}")
            
            logger.info(f"Simulation updated successfully for {current_hour}")
            
        except Exception as e:
            logger.error(f"Error updating simulation: {e}", exc_info=True)
    
    def trigger_immediate_update(self, reason: str = "manual") -> bool:
        """
        Force an immediate simulation update, bypassing cache checks.
        Used when configuration changes that affect current simulation (e.g., DR participation).
        
        Args:
            reason: Reason for the immediate update (for logging)
            
        Returns:
            True if update was triggered successfully, False otherwise
        """
        if not self._running:
            logger.warning(f"Cannot trigger immediate update: service not running")
            return False
        
        try:
            model_service = self._get_model_service()
            model = model_service.get_model()
            if model is None:
                logger.warning("Model not loaded, cannot trigger immediate update")
                return False
            
            # Get current time (rounded to current hour)
            now = datetime.now(ZoneInfo(model.community.timezone))
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            
            logger.info(f"Triggering immediate simulation update: {reason}")
            
            # Ensure DR service has events loaded before simulation
            try:
                from app.services.infrastructure.demand_response_service import get_demand_response_service
                dr_service = get_demand_response_service()
                # Force load events if not already loaded
                if len(dr_service._events) == 0:
                    logger.info("DR service has no events, loading from MongoDB...")
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in async context, but need to load sync
                        # Create a task to load (won't block, but at least attempts to load)
                        asyncio.create_task(dr_service._load_events_from_db())
                        logger.warning("DR events will load asynchronously, simulation may run before events load")
                    except RuntimeError:
                        # No running loop, can load sync
                        asyncio.run(dr_service._load_events_from_db())
                        logger.info(f"Loaded {len(dr_service._events)} DR events")
            except Exception as e:
                logger.warning(f"Could not ensure DR events loaded: {e}")
            
            # Run community simulation (force update, bypass cache check)
            simulation_engine = self._get_simulation_engine()
            community_result = simulation_engine.simulate_community(current_hour)
            
            # Update structured cache
            with self._cache_lock:
                # Set as current data
                self._structured_cache['current'] = {
                    'timestamp': current_hour.isoformat(),
                    'data': community_result
                }
            
            # Update historical timeframes (will replace existing entry for this hour)
            self._add_to_structured_cache(current_hour, community_result)
            
            logger.info(f"Immediate simulation update completed for {current_hour} (reason: {reason})")
            return True
            
        except Exception as e:
            logger.error(f"Error in immediate simulation update: {e}", exc_info=True)
            return False
    
    def get_current_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current simulation data (latest hour).
        
        Returns:
            Dict with 'timestamp' and 'data' keys, or None if not available
        """
        with self._cache_lock:
            current = self._structured_cache.get('current')
            return current.copy() if current else None
    
    def get_today_data(self) -> list:
        """
        Get all simulation data for today (midnight to now).
        
        Returns:
            List of data points, each with 'timestamp' and 'data' keys
        """
        with self._cache_lock:
            return [d.copy() for d in self._structured_cache.get('today', [])]
    
    def get_week_data(self) -> list:
        """
        Get all simulation data for the last 7 days.
        
        Returns:
            List of data points, each with 'timestamp' and 'data' keys
        """
        with self._cache_lock:
            return [d.copy() for d in self._structured_cache.get('this_week', [])]
    
    def get_month_data(self) -> list:
        """
        Get all simulation data for the last 30 days.
        
        Returns:
            List of data points, each with 'timestamp' and 'data' keys
        """
        with self._cache_lock:
            return [d.copy() for d in self._structured_cache.get('this_month', [])]
    
    def get_community_data(self, timestamp: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Get cached community simulation data (backward compatibility).
        
        Args:
            timestamp: Optional timestamp (ignored in structured cache, returns current)
            
        Returns:
            Community simulation result or None if not available
        """
        current = self.get_current_data()
        return current['data'] if current else None
    
    def get_member_data(self, member_id: str, timestamp: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Get cached member simulation data (backward compatibility).
        
        Args:
            member_id: Member ID
            timestamp: Optional timestamp (ignored in structured cache, returns current)
            
        Returns:
            Member simulation result or None if not available
        """
        current = self.get_current_data()
        if not current or not current.get('data'):
            return None
        
        members = current['data'].get('members', [])
        for member in members:
            if member.get('member_id') == member_id:
                return member.copy()
        return None
    
    def get_hourly_history(self, member_id: Optional[str] = None, hours: int = 24) -> list:
        """
        Get hourly historical data (backward compatibility).
        
        Args:
            member_id: Optional member ID to filter by
            hours: Number of hours to return (default: 24)
            
        Returns:
            List of historical data points with member-specific data
        """
        # Get all today's data
        all_data = self.get_today_data()[-hours:] if hours else self.get_today_data()
        
        # If member_id specified, extract member data from each hour
            if member_id:
            member_history = []
            for entry in all_data:
                community_data = entry.get('data', {})
                members = community_data.get('members', [])
                
                # Find this member in the hour's data
                for member in members:
                    if member.get('member_id') == member_id:
                        # Create entry with member data
                        member_history.append({
                            'timestamp': entry.get('timestamp'),
                            'data': member.copy()
                        })
                        break
            return member_history
        
        # Return community-level data
        return all_data
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get status information about the structured cache."""
        with self._cache_lock:
            current = self._structured_cache.get('current')
            return {
                'running': self._running,
                'current_timestamp': current['timestamp'] if current else None,
                'has_current_data': current is not None,
                'update_interval_seconds': self.update_interval_seconds,
                'cache_structure': {
                    'today_count': len(self._structured_cache.get('today', [])),
                    'week_count': len(self._structured_cache.get('this_week', [])),
                    'month_count': len(self._structured_cache.get('this_month', []))
                }
            }
    
    def force_update(self):
        """Force an immediate simulation update (useful for testing or manual triggers)."""
        logger.info("Forcing simulation update")
        self._update_simulation_sync()


# Global singleton instance
_background_service: Optional[BackgroundSimulationService] = None


def get_background_service() -> BackgroundSimulationService:
    """Get the global background simulation service instance."""
    global _background_service
    if _background_service is None:
        _background_service = BackgroundSimulationService()
    return _background_service

