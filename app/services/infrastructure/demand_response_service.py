"""
Demand Response Service

Manages demand response events and member participation.
Integrates with simulation to modify consumption during active events.
Persists events and participation to MongoDB.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo
import threading
import uuid
import asyncio

from app.models.community_model import Member

logger = logging.getLogger(__name__)


class DemandResponseEvent:
    """Represents an active demand response event."""
    
    def __init__(
        self,
        event_id: str,
        title: str,
        start_time: datetime,
        end_time: datetime,
        target_reduction_pct: float = 0.2,  # 20% reduction default
        price_signal: float = 0.15,  # USD per kWh saved
        reason: str = "Peak demand management"
    ):
        self.event_id = event_id
        self.title = title
        self.start_time = start_time
        self.end_time = end_time
        self.target_reduction_pct = target_reduction_pct
        self.price_signal = price_signal
        self.reason = reason
        self.participants: Dict[str, float] = {}  # member_id -> reduction_pct
        
    def is_active(self, current_time: datetime) -> bool:
        """Check if event is currently active."""
        try:
            # Ensure we can compare datetimes (handle timezone-aware vs naive)
            start = self.start_time
            end = self.end_time
            
            # If current_time is aware but event times are naive, make them aware
            if current_time.tzinfo is not None and start.tzinfo is None:
                logger.debug(f"Event {self.event_id}: Converting naive event times to UTC")
                start = start.replace(tzinfo=ZoneInfo("UTC"))
                end = end.replace(tzinfo=ZoneInfo("UTC"))
            # If current_time is naive but event times are aware, make current_time aware
            elif current_time.tzinfo is None and start.tzinfo is not None:
                logger.debug(f"Event {self.event_id}: Converting naive current_time to UTC")
                current_time = current_time.replace(tzinfo=ZoneInfo("UTC"))
            
            is_active = start <= current_time <= end
            return is_active
        except Exception as e:
            logger.warning(f"Error comparing event times for {self.event_id}: {e}")
            return False
    
    def add_participant(self, member_id: str, reduction_pct: float):
        """Add a member to the event."""
        self.participants[member_id] = reduction_pct
        
    def remove_participant(self, member_id: str):
        """Remove a member from the event."""
        self.participants.pop(member_id, None)
        
    def get_participant_count(self) -> int:
        """Get number of participating members."""
        return len(self.participants)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "event_id": self.event_id,
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "target_reduction_pct": self.target_reduction_pct,
            "price_signal_usd_per_kwh": self.price_signal,
            "reason": self.reason,
            "status": "active" if self.is_active(datetime.now(self.start_time.tzinfo)) else "ended",
            "participant_count": self.get_participant_count()
        }


class DemandResponseService:
    """
    Service for managing demand response events and member participation.
    
    This service:
    - Creates and manages DR events
    - Tracks member opt-ins/opt-outs
    - Calculates actual reduction achieved
    - Provides metrics for dashboard
    """
    
    def __init__(self):
        """Initialize the demand response service."""
        self._events: Dict[str, DemandResponseEvent] = {}  # event_id -> event
        self._lock = threading.Lock()
        self._mongodb_available = False
        
        # Try to load events from MongoDB
        try:
            asyncio.create_task(self._load_events_from_db())
        except RuntimeError:
            # No event loop yet, will load when first accessed
            logger.debug("No event loop available, will load DR events on first access")
        
        logger.info("DemandResponseService initialized")
    
    async def _load_events_from_db(self):
        """Load events from MongoDB on startup."""
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.DEMAND_RESPONSE_EVENTS]
            
            # Load all events from MongoDB
            cursor = collection.find({})
            count = 0
            
            async for doc in cursor:
                try:
                    # Convert MongoDB document to DREvent
                    # MongoDB returns timezone-naive datetimes, so we need to add UTC timezone
                    start_time = doc["start_time"]
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=ZoneInfo("UTC"))
                    
                    end_time = doc["end_time"]
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=ZoneInfo("UTC"))
                    
                    event = DemandResponseEvent(
                        event_id=doc["event_id"],
                        title=doc["title"],
                        start_time=start_time,
                        end_time=end_time,
                        target_reduction_pct=doc["target_reduction_pct"],
                        price_signal=doc["price_signal"],
                        reason=doc["reason"]
                    )
                    # Restore participants
                    event.participants = doc.get("participants", {})
                    
                    with self._lock:
                        self._events[event.event_id] = event
                    count += 1
                except Exception as e:
                    logger.error(f"Error loading DR event from DB: {e}")
            
            self._mongodb_available = True
            logger.info(f"Loaded {count} DR events from MongoDB")
            
        except Exception as e:
            logger.warning(f"Could not load DR events from MongoDB: {e}")
            self._mongodb_available = False
    
    async def _save_event_to_db(self, event: DemandResponseEvent):
        """Save or update an event in MongoDB."""
        if not self._mongodb_available:
            return
        
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.DEMAND_RESPONSE_EVENTS]
            
            # Convert event to MongoDB document
            doc = {
                "event_id": event.event_id,
                "title": event.title,
                "start_time": event.start_time,
                "end_time": event.end_time,
                "target_reduction_pct": event.target_reduction_pct,
                "price_signal": event.price_signal,
                "reason": event.reason,
                "participants": event.participants,
                "updated_at": datetime.now(ZoneInfo("UTC"))
            }
            
            # Upsert (update if exists, insert if not)
            await collection.replace_one(
                {"event_id": event.event_id},
                doc,
                upsert=True
            )
            
            logger.debug(f"Saved DR event {event.event_id} to MongoDB")
            
        except Exception as e:
            logger.error(f"Error saving DR event to MongoDB: {e}")
    
    async def _delete_event_from_db(self, event_id: str):
        """Delete an event from MongoDB."""
        if not self._mongodb_available:
            return
        
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.DEMAND_RESPONSE_EVENTS]
            
            await collection.delete_one({"event_id": event_id})
            logger.debug(f"Deleted DR event {event_id} from MongoDB")
            
        except Exception as e:
            logger.error(f"Error deleting DR event from MongoDB: {e}")
    
    def _ensure_loaded(self):
        """Ensure events are loaded from DB (lazy loading)."""
        if not self._mongodb_available and len(self._events) == 0:
            # Try to load now if we haven't yet - use blocking approach
            try:
                # Try to get the running loop
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an async context, can't block. Events should be loaded async
                    logger.warning("DR events not loaded yet, and we're in async context. Use async methods.")
                except RuntimeError:
                    # No running loop, we can create one
                    logger.info("Loading DR events from MongoDB (sync)...")
                    asyncio.run(self._load_events_from_db())
            except Exception as e:
                logger.error(f"Could not load events: {e}", exc_info=True)
    
    def create_event(
        self,
        title: str,
        start_time: datetime,
        duration_hours: float = 2.0,
        target_reduction_pct: float = 0.2,
        price_signal: float = 0.15,
        reason: str = "Peak demand management"
    ) -> str:
        """
        Create a new demand response event.
        
        Args:
            title: Event title
            start_time: When event starts
            duration_hours: How long event lasts
            target_reduction_pct: Target reduction as percentage (0.0-1.0)
            price_signal: Payment per kWh reduced (USD)
            reason: Reason for DR event
            
        Returns:
            Event ID
        """
        event_id = f"dr_{uuid.uuid4().hex[:8]}"
        end_time = start_time + timedelta(hours=duration_hours)
        
        event = DemandResponseEvent(
            event_id=event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            target_reduction_pct=target_reduction_pct,
            price_signal=price_signal,
            reason=reason
        )
        
        with self._lock:
            self._events[event_id] = event
        
        # Persist to MongoDB
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_event_to_db(event))
        except Exception as e:
            logger.debug(f"Could not save DR event to DB: {e}")
        
        logger.info(
            f"Created DR event '{title}' (ID: {event_id}): "
            f"{start_time.isoformat()} to {end_time.isoformat()}, "
            f"target reduction: {target_reduction_pct * 100:.0f}%"
        )
        
        return event_id
    
    def get_active_events(self, current_time: Optional[datetime] = None) -> List[DemandResponseEvent]:
        """
        Get all currently active events.
        
        Args:
            current_time: Time to check (defaults to now)
            
        Returns:
            List of active events
        """
        self._ensure_loaded()  # Lazy load if needed
        
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        with self._lock:
            return [
                event for event in self._events.values()
                if event.is_active(current_time)
            ]
    
    async def get_all_events_async(self) -> List[DemandResponseEvent]:
        """Get all events (active and past), async version that properly loads from DB."""
        if not self._mongodb_available and len(self._events) == 0:
            await self._load_events_from_db()
        
        with self._lock:
            return list(self._events.values())
    
    def get_all_events(self) -> List[DemandResponseEvent]:
        """Get all events (active and past). Sync version, may return empty list if not loaded yet."""
        self._ensure_loaded()  # Lazy load if needed
        
        with self._lock:
            return list(self._events.values())
    
    def opt_in(self, member_id: str, event_id: str, reduction_pct: Optional[float] = None) -> bool:
        """
        Opt a member into a DR event.
        
        Args:
            member_id: Member ID
            event_id: Event ID
            reduction_pct: Custom reduction percentage (uses event default if None)
            
        Returns:
            True if successful
        """
        # Ensure events are loaded before trying to access them
        self._ensure_loaded()
        
        with self._lock:
            event = self._events.get(event_id)
            if event is None:
                logger.warning(f"DR event {event_id} not found in {len(self._events)} loaded events")
                return False
            
            # Use event's target if no custom reduction specified
            if reduction_pct is None:
                reduction_pct = event.target_reduction_pct
            
            event.add_participant(member_id, reduction_pct)
            
            # Persist to MongoDB
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._save_event_to_db(event))
            except Exception as e:
                logger.debug(f"Could not save DR event to DB: {e}")
            
            logger.info(
                f"Member {member_id} opted into DR event {event_id} "
                f"with {reduction_pct * 100:.0f}% reduction"
            )
            
            return True
    
    def opt_out(self, member_id: str, event_id: str) -> bool:
        """
        Opt a member out of a DR event.
        
        Args:
            member_id: Member ID
            event_id: Event ID
            
        Returns:
            True if successful
        """
        # Ensure events are loaded before trying to access them
        self._ensure_loaded()
        
        with self._lock:
            event = self._events.get(event_id)
            if event is None:
                logger.warning(f"DR event {event_id} not found in {len(self._events)} loaded events")
                return False
            
            event.remove_participant(member_id)
            
            # Persist to MongoDB
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._save_event_to_db(event))
            except Exception as e:
                logger.debug(f"Could not save DR event to DB: {e}")
            
            logger.info(f"Member {member_id} opted out of DR event {event_id}")
            
            return True
    
    def get_member_reduction(self, member_id: str, current_time: datetime) -> float:
        """
        Get the current reduction percentage for a member based on active events.
        
        Args:
            member_id: Member ID
            current_time: Current simulation time
            
        Returns:
            Reduction percentage (0.0-1.0), 0 if no active events
        """
        active_events = self.get_active_events(current_time)
        
        # If member is in multiple events, use the highest reduction
        max_reduction = 0.0
        for event in active_events:
            if member_id in event.participants:
                reduction = event.participants[member_id]
                max_reduction = max(max_reduction, reduction)
                logger.debug(
                    f"Member {member_id} participating in {event.event_id} with {reduction*100:.1f}% reduction"
                )
        
        return max_reduction
    
    def calculate_metrics(
        self,
        current_time: datetime,
        simulation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate demand response metrics for dashboard.
        
        Args:
            current_time: Current simulation time
            simulation_result: Current community simulation result
            
        Returns:
            Dictionary with DR metrics
        """
        active_events = self.get_active_events(current_time)
        
        # Count participating members across all active events
        all_participants = set()
        total_target_reduction = 0.0
        
        for event in active_events:
            all_participants.update(event.participants.keys())
            total_target_reduction += event.target_reduction_pct
        
        # Get aggregate values from simulation
        total_generation = simulation_result.get("total_generation_kw", 0.0)
        total_consumption = simulation_result.get("total_consumption_kw", 0.0)
        net_balance = simulation_result.get("total_net_balance_kw", 0.0)
        
        # Estimate potential shed (20% of current consumption as baseline)
        potential_shed_kw = total_consumption * 0.2
        
        # Calculate actual reduction if events are active
        if active_events and all_participants:
            # Actual reduction would need baseline comparison
            # For now, estimate based on participation
            avg_reduction = total_target_reduction / len(active_events) if active_events else 0.0
            actual_reduction_kw = total_consumption * avg_reduction * (len(all_participants) / max(len(simulation_result.get("members", [])), 1))
        else:
            actual_reduction_kw = 0.0
        
        # Get price signal from first active event
        price_signal = active_events[0].price_signal if active_events else 0.0
        
        return {
            "active_event_count": len(active_events),
            "participating_member_count": len(all_participants),
            "aggregate_generation_kw": total_generation,
            "aggregate_consumption_kw": total_consumption,
            "net_balance_kw": net_balance,
            "potential_shed_kw": potential_shed_kw,
            "actual_reduction_kw": actual_reduction_kw,
            "price_signal_usd_per_kwh": price_signal,
            "active_events": [event.to_dict() for event in active_events]
        }
    
    def cleanup_old_events(self, current_time: datetime, hours_to_keep: int = 168):
        """
        Remove events older than specified hours (default 7 days).
        
        Args:
            current_time: Current time
            hours_to_keep: How many hours of history to keep (default: 168 = 7 days)
        """
        cutoff_time = current_time - timedelta(hours=hours_to_keep)
        
        with self._lock:
            to_remove = [
                event_id for event_id, event in self._events.items()
                if event.end_time < cutoff_time
            ]
            
            for event_id in to_remove:
                del self._events[event_id]
                
                # Delete from MongoDB
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._delete_event_from_db(event_id))
                except Exception as e:
                    logger.debug(f"Could not delete DR event from DB: {e}")
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old DR events")


# Global singleton instance
_dr_service: Optional[DemandResponseService] = None


def get_demand_response_service() -> DemandResponseService:
    """Get the global demand response service instance."""
    global _dr_service
    if _dr_service is None:
        _dr_service = DemandResponseService()
    return _dr_service

