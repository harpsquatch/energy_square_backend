"""
Community Model Service
Loads, validates, and manages the community model configuration with hot-reload support.
MongoDB only - no file fallback.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
import threading
import time
import asyncio

from app.models.community_model import CommunityModel, Member, MemberType

logger = logging.getLogger(__name__)


class CommunityModelService:
    """Service for loading and managing community model configuration."""
    
    def __init__(
        self, 
        watch_for_changes: bool = False,
        community_id: str = "community_001"
    ):
        """
        Initialize the community model service.
        
        Args:
            watch_for_changes: If True, watch for changes and reload automatically.
            community_id: Community ID to load from MongoDB.
        """
        self.watch_for_changes = watch_for_changes
        self.community_id = community_id
        
        # Cached model
        self._model: Optional[CommunityModel] = None
        self._last_modified: Optional[float] = None
        self._lock = threading.Lock()
        
        # MongoDB state
        self._mongodb_available = False
        self._check_mongodb()
        
        if not self._mongodb_available:
            raise RuntimeError(
                f"MongoDB is not available or not connected. "
                f"Cannot load community model '{self.community_id}'. "
                f"Please ensure MongoDB is running and connected."
            )
        
        # Change watching thread (checks MongoDB for updates)
        self._watch_thread: Optional[threading.Thread] = None
        self._stop_watching = threading.Event()
        
        # Load initial model from MongoDB
        if not self.reload_model():
            raise RuntimeError(
                f"Failed to load community model '{self.community_id}' from MongoDB. "
                f"Please ensure the model exists in the database."
            )
        
        # Start watcher if requested
        if self.watch_for_changes:
            self.start_watching()
    
    def _check_mongodb(self):
        """Check if MongoDB is available."""
        try:
            from app.db.database import MONGO_AVAILABLE, db, _ensure_mongo_imported
            _ensure_mongo_imported()
            self._mongodb_available = MONGO_AVAILABLE and db.connected
            if self._mongodb_available:
                logger.debug("MongoDB is available and connected")
            else:
                logger.debug("MongoDB is not available or not connected, will use file fallback")
        except Exception as e:
            logger.debug(f"MongoDB check failed: {e}")
            self._mongodb_available = False
    
    def refresh_mongodb_status(self):
        """Refresh MongoDB availability status (call after MongoDB connection is established)."""
        self._check_mongodb()
    
    def reload_model(self) -> bool:
        """
        Reload the community model from MongoDB.
        
        Returns:
            True if reload was successful, False otherwise
            
        Raises:
            RuntimeError: If MongoDB is not available or model not found
        """
        if not self._mongodb_available:
            logger.error(f"Cannot reload model: MongoDB is not available or not connected")
            return False
        
        try:
            if self._load_from_mongodb():
                return True
            else:
                logger.error(
                    f"Community model '{self.community_id}' not found in MongoDB. "
                    f"Please ensure the model has been migrated to MongoDB."
                )
                return False
        except Exception as e:
            logger.error(f"Error reloading community model from MongoDB: {e}", exc_info=True)
            return False
    
    def _load_from_mongodb(self) -> bool:
        """Load community model from MongoDB (synchronous wrapper)."""
        try:
            # Always run in a separate thread with its own event loop
            # This avoids conflicts with existing event loops (like FastAPI's)
            import concurrent.futures
            
            # Run async function in a new event loop in a separate thread
            # This avoids conflicts with existing event loops
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._run_async_load)
                return future.result(timeout=10.0)
        except Exception as e:
            logger.error(f"Error in MongoDB load wrapper: {e}", exc_info=True)
            return False
    
    def _run_async_load(self) -> bool:
        """Run async load in a new event loop (for use in thread)."""
        # Create a completely new event loop in this thread
        # We need a fresh MongoDB client for this loop since Motor clients are loop-bound
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Create a fresh async load function that creates its own DB connection
                return loop.run_until_complete(self._load_from_mongodb_async_fresh_loop())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Error in _run_async_load: {e}", exc_info=True)
            return False
    
    async def _load_from_mongodb_async_fresh_loop(self) -> bool:
        """Load from MongoDB with a fresh connection (for use in separate event loop)."""
        try:
            from app.db.database import AsyncIOMotorClient, Collections
            from app.core.config import settings
            
            # Create a new MongoDB client for this event loop
            client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
            database = client[settings.DATABASE_NAME]
            collection = database[Collections.COMMUNITY_MODELS]
            
            # Try multiple query patterns to find the model
            # Pattern 1: nested community.community_id (this should work with dot notation)
            logger.info(f"Querying MongoDB for community_id '{self.community_id}' using pattern 1: community.community_id")
            doc = await collection.find_one({"community.community_id": self.community_id})
            
            # Pattern 2: top-level community_id
            if doc is None:
                logger.info(f"Pattern 1 failed, trying pattern 2: top-level community_id")
                doc = await collection.find_one({"community_id": self.community_id})
            
            # Pattern 3: _id field (if community_id is used as _id)
            if doc is None:
                logger.info(f"Pattern 2 failed, trying pattern 3: _id field")
                doc = await collection.find_one({"_id": self.community_id})
            
            # Pattern 4: search in any field containing community_id (manual search)
            if doc is None:
                logger.info(f"All direct queries failed, searching all documents manually...")
                all_docs = await collection.find({}).limit(5).to_list(length=5)
                logger.info(f"DEBUG: Found {len(all_docs)} documents in collection '{Collections.COMMUNITY_MODELS}'")
                if all_docs:
                    # Log the structure of the first document
                    first_doc = all_docs[0]
                    logger.info(f"DEBUG: First document keys: {list(first_doc.keys())}")
                    logger.info(f"DEBUG: First document _id: {first_doc.get('_id')} (type: {type(first_doc.get('_id'))})")
                    logger.info(f"DEBUG: First document community: {first_doc.get('community')}")
                    
                    # Try to find by any community_id field
                    for idx, check_doc in enumerate(all_docs):
                        community_data = check_doc.get("community", {})
                        doc_community_id = community_data.get("community_id") if isinstance(community_data, dict) else None
                        logger.info(f"DEBUG: Document {idx} community_id: {doc_community_id}, looking for: {self.community_id}")
                        
                        # Check various possible locations
                        if doc_community_id == self.community_id:
                            doc = check_doc
                            logger.info(f"DEBUG: ✓ Found matching document at index {idx} via community.community_id")
                            break
                        if check_doc.get("community_id") == self.community_id:
                            doc = check_doc
                            logger.info(f"DEBUG: ✓ Found matching document (top-level community_id) at index {idx}")
                            break
                        doc_id = check_doc.get("_id")
                        if doc_id and str(doc_id) == self.community_id:
                            doc = check_doc
                            logger.info(f"DEBUG: ✓ Found matching document (_id match) at index {idx}")
                            break
            
            # Close client
            client.close()
            
            if doc is None:
                logger.error(
                    f"No model found in MongoDB for community_id '{self.community_id}' "
                    f"in collection '{Collections.COMMUNITY_MODELS}'. "
                    f"Queried: community.community_id, community_id, _id"
                )
                return False
            
            # Remove MongoDB _id field
            doc.pop('_id', None)
            
            with self._lock:
                # Validate and create model
                self._model = CommunityModel.model_validate(doc)
                self._last_modified = datetime.now().timestamp()
                
                logger.info(
                    f"Loaded community model from MongoDB: {self._model.community.community_id} "
                    f"({len(self._model.members)} members, version {self._model.community.version})"
                )
                
                # Log configuration source info
                self._log_configuration_source()
                
                return True
                
        except Exception as e:
            logger.error(f"Error loading from MongoDB (fresh loop): {e}", exc_info=True)
            return False
    
    async def _load_from_mongodb_async(self) -> bool:
        """Load community model from MongoDB (async)."""
        try:
            from app.db.database import get_database, Collections
            
            database = await get_database()
            collection = database[Collections.COMMUNITY_MODELS]
            
            # Try multiple query patterns to find the model
            # Pattern 1: nested community.community_id (this should work with dot notation)
            logger.info(f"Querying MongoDB for community_id '{self.community_id}' using pattern 1: community.community_id")
            doc = await collection.find_one({"community.community_id": self.community_id})
            
            # Pattern 2: top-level community_id (if structure is different)
            if doc is None:
                logger.info(f"Pattern 1 failed, trying pattern 2: top-level community_id")
                doc = await collection.find_one({"community_id": self.community_id})
            
            # Pattern 3: _id field (if community_id is used as _id)
            if doc is None:
                logger.info(f"Pattern 2 failed, trying pattern 3: _id field")
                doc = await collection.find_one({"_id": self.community_id})
            
            # Pattern 4: search in any field containing community_id (manual search)
            if doc is None:
                logger.info(f"All direct queries failed, searching all documents manually...")
                all_docs = await collection.find({}).limit(5).to_list(length=5)
                logger.info(f"DEBUG: Found {len(all_docs)} documents in collection '{Collections.COMMUNITY_MODELS}'")
                if all_docs:
                    # Log the structure of the first document
                    first_doc = all_docs[0]
                    logger.info(f"DEBUG: First document keys: {list(first_doc.keys())}")
                    logger.info(f"DEBUG: First document _id: {first_doc.get('_id')} (type: {type(first_doc.get('_id'))})")
                    logger.info(f"DEBUG: First document community: {first_doc.get('community')}")
                    
                    # Try to find by any community_id field
                    for idx, check_doc in enumerate(all_docs):
                        community_data = check_doc.get("community", {})
                        doc_community_id = community_data.get("community_id") if isinstance(community_data, dict) else None
                        logger.info(f"DEBUG: Document {idx} community_id: {doc_community_id}, looking for: {self.community_id}")
                        
                        # Check various possible locations
                        if doc_community_id == self.community_id:
                            doc = check_doc
                            logger.info(f"DEBUG: ✓ Found matching document at index {idx} via community.community_id")
                            break
                        if check_doc.get("community_id") == self.community_id:
                            doc = check_doc
                            logger.info(f"DEBUG: ✓ Found matching document (top-level community_id) at index {idx}")
                            break
                        doc_id = check_doc.get("_id")
                        if doc_id and str(doc_id) == self.community_id:
                            doc = check_doc
                            logger.info(f"DEBUG: ✓ Found matching document (_id match) at index {idx}")
                            break
            
            if doc is None:
                logger.error(
                    f"No model found in MongoDB for community_id '{self.community_id}' "
                    f"in collection '{Collections.COMMUNITY_MODELS}'. "
                    f"Queried: community.community_id, community_id, _id"
                )
                return False
            
            # Remove MongoDB _id field
            doc.pop('_id', None)
            
            with self._lock:
                # Validate and create model
                self._model = CommunityModel.model_validate(doc)
                self._last_modified = datetime.now().timestamp()
                
                logger.info(
                    f"Loaded community model from MongoDB: {self._model.community.community_id} "
                    f"({len(self._model.members)} members, version {self._model.community.version})"
                )
                
                # Log configuration source info
                self._log_configuration_source()
                
                return True
                
        except Exception as e:
            logger.error(f"Error loading from MongoDB: {e}", exc_info=True)
            return False
    
    def _log_configuration_source(self):
        """Log which configuration values are using defaults."""
        if not self._model:
            return
        
        cc = self._model.community_control
        defaults_check = {
            "import_rate": (cc.import_rate_usd_per_kwh == 0.12),
            "export_rate": (cc.export_rate_usd_per_kwh == 0.08),
            "carbon_offset": (cc.carbon_offset_factor_kg_per_kwh == 0.5),
            "grid_voltage": (cc.grid_voltage_v == 480.0),
            "grid_frequency": (cc.grid_frequency_hz == 60.0),
        }
        using_defaults = [k for k, v in defaults_check.items() if v]
        
        if using_defaults:
            logger.warning(
                f"Model loaded but using Pydantic defaults for: {', '.join(using_defaults)}. "
                f"Check MongoDB document to ensure these are explicitly set in 'community_control' section."
            )
        else:
            logger.info("All key configuration values appear to be set in MongoDB (not using defaults)")
    
    def get_model(self) -> Optional[CommunityModel]:
        """Get the current community model."""
        with self._lock:
            return self._model
    
    def get_model_status(self) -> Dict[str, Any]:
        """
        Get status information about the loaded model, including which values are defaults.
        
        Returns:
            Dictionary with model status, source info, and configuration details
        """
        with self._lock:
            model = self._model
            
            if not model:
                return {
                    "model_loaded": False,
                    "mongodb_available": self._mongodb_available,
                    "community_id": self.community_id,
                    "source": "none",
                    "message": "Model not loaded"
                }
            
            cc = model.community_control
            
            # Check if values match Pydantic defaults (indicating they might be defaults)
            # Note: This is an approximation - we compare against known defaults
            defaults_map = {
                "grid_import_limit_kw": 10000.0,
                "grid_export_limit_kw": 5000.0,
                # Note: battery_min_soc and battery_max_soc are per-member constraints, not community config
                "import_rate_usd_per_kwh": 0.12,
                "export_rate_usd_per_kwh": 0.08,
                "carbon_offset_factor_kg_per_kwh": 0.5,
                "grid_voltage_v": 480.0,
                "grid_frequency_hz": 60.0,
                # grid_stability_index: calculated dynamically by simulator (not config)
                # grid_load_reference_kw: calculated dynamically by simulator (not config)
                # battery_max_power_rate: per-chemistry (not community config)
                # tier multipliers: removed (will be implemented with leaderboards)
                # outside_active_hours_factor: per-member based on customer_category
                # temperature_normalization_divisor: per-member based on customer_category
                # routine_drift: removed (dead code, not integrated in simulation)
                "temperature_base_celsius": 20.0,
            }
            
            config_values = {
                "grid_import_limit_kw": {"value": cc.grid_import_limit_kw, "is_default": cc.grid_import_limit_kw == defaults_map["grid_import_limit_kw"]},
                "grid_export_limit_kw": {"value": cc.grid_export_limit_kw, "is_default": cc.grid_export_limit_kw == defaults_map["grid_export_limit_kw"]},
                # Note: battery_min_soc and battery_max_soc are per-member constraints, not community config
                "import_rate_usd_per_kwh": {"value": cc.import_rate_usd_per_kwh, "is_default": cc.import_rate_usd_per_kwh == defaults_map["import_rate_usd_per_kwh"]},
                "export_rate_usd_per_kwh": {"value": cc.export_rate_usd_per_kwh, "is_default": cc.export_rate_usd_per_kwh == defaults_map["export_rate_usd_per_kwh"]},
                "carbon_offset_factor_kg_per_kwh": {"value": cc.carbon_offset_factor_kg_per_kwh, "is_default": cc.carbon_offset_factor_kg_per_kwh == defaults_map["carbon_offset_factor_kg_per_kwh"]},
                "grid_voltage_v": {"value": cc.grid_voltage_v, "is_default": cc.grid_voltage_v == defaults_map["grid_voltage_v"]},
                "grid_frequency_hz": {"value": cc.grid_frequency_hz, "is_default": cc.grid_frequency_hz == defaults_map["grid_frequency_hz"]},
                # grid_stability_index: calculated dynamically by simulator (not config)
                # grid_load_reference_kw: calculated dynamically by simulator (not config)
                # battery_max_power_rate: per-chemistry (not community config)
                # tier multipliers: removed (will be implemented with leaderboards)
                # outside_active_hours_factor: per-member based on customer_category
                # temperature_normalization_divisor: per-member based on customer_category
                # routine_drift: removed (dead code, not integrated in simulation)
                "temperature_base_celsius": {"value": cc.temperature_base_celsius, "is_default": cc.temperature_base_celsius == defaults_map["temperature_base_celsius"]},
            }
            
            # Count how many are defaults
            default_count = sum(1 for v in config_values.values() if v["is_default"])
            total_count = len(config_values)
            
            return {
                "model_loaded": True,
                "mongodb_available": self._mongodb_available,
                "source": "MongoDB" if self._mongodb_available else "unknown",
                "community_id": model.community.community_id,
                "model_version": model.community.version,
                "members_count": len(model.members),
                "last_modified": self._last_modified,
                "configuration": {
                    "summary": {
                        "total_settings": total_count,
                        "using_defaults": default_count,
                        "from_mongodb": total_count - default_count,
                        "defaults_percentage": round((default_count / total_count) * 100, 1) if total_count > 0 else 0.0
                    },
                    "values": config_values
                }
            }
    
    def get_member(self, member_id: str) -> Optional[Member]:
        """Get a member by ID."""
        model = self.get_model()
        if model is None:
            return None
        return model.get_member(member_id)
    
    def get_members_by_type(self, member_type: MemberType) -> List[Member]:
        """Get all members of a specific type."""
        model = self.get_model()
        if model is None:
            return []
        return model.get_members_by_type(member_type)
    
    def get_members_by_group(self, group_id: str) -> List[Member]:
        """Get all members in a group."""
        model = self.get_model()
        if model is None:
            return []
        return model.get_members_by_group(group_id)
    
    def add_member(self, member: Member) -> bool:
        """
        Add a new member to the model.
        
        Args:
            member: Member to add
            
        Returns:
            True if successful, False otherwise
        """
        model = self.get_model()
        if model is None:
            logger.error("Cannot add member: model not loaded")
            return False
        
        # Check if member already exists
        if model.get_member(member.member_id) is not None:
            logger.warning(f"Member {member.member_id} already exists")
            return False
        
        try:
            with self._lock:
                model.members.append(member)
                self._save_model(model)
                logger.info(f"Added member: {member.member_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding member: {e}", exc_info=True)
            return False
    
    def remove_member(self, member_id: str) -> bool:
        """
        Remove a member from the model.
        
        Args:
            member_id: ID of member to remove
            
        Returns:
            True if successful, False otherwise
        """
        model = self.get_model()
        if model is None:
            logger.error("Cannot remove member: model not loaded")
            return False
        
        member = model.get_member(member_id)
        if member is None:
            logger.warning(f"Member {member_id} not found")
            return False
        
        try:
            with self._lock:
                model.members = [m for m in model.members if m.member_id != member_id]
                self._save_model(model)
                logger.info(f"Removed member: {member_id}")
                return True
        except Exception as e:
            logger.error(f"Error removing member: {e}", exc_info=True)
            return False
    
    def update_member(self, member_id: str, updates: Dict) -> bool:
        """
        Update a member's configuration.
        
        Args:
            member_id: ID of member to update
            updates: Dictionary of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        model = self.get_model()
        if model is None:
            logger.error("Cannot update member: model not loaded")
            return False
        
        member = model.get_member(member_id)
        if member is None:
            logger.warning(f"Member {member_id} not found")
            return False
        
        try:
            with self._lock:
                # Create updated member dict
                member_dict = member.model_dump()
                member_dict.update(updates)
                
                # Validate updated member
                updated_member = Member.model_validate(member_dict)
                
                # Replace in list
                for i, m in enumerate(model.members):
                    if m.member_id == member_id:
                        model.members[i] = updated_member
                        break
                
                self._save_model(model)
                logger.info(f"Updated member: {member_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating member: {e}", exc_info=True)
            return False
    
    def _save_model(self, model: CommunityModel):
        """Save model to MongoDB only."""
        if not self._mongodb_available:
            raise RuntimeError(
                f"Cannot save model: MongoDB is not available or not connected. "
                f"Model changes cannot be persisted."
            )
        
        # Update version timestamp
        model.community.version = f"{model.community.version.split('.')[0]}.{int(time.time())}"
        
        # Save to MongoDB (async, non-blocking)
        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule async save
                    asyncio.create_task(self._save_to_mongodb(model))
                else:
                    loop.run_until_complete(self._save_to_mongodb(model))
            except RuntimeError:
                # No loop, create one
                asyncio.run(self._save_to_mongodb(model))
        except Exception as e:
            logger.error(f"Failed to save to MongoDB: {e}", exc_info=True)
            raise RuntimeError(f"Failed to save model to MongoDB: {e}") from e
    
    async def _save_to_mongodb(self, model: CommunityModel):
        """Save model to MongoDB (async)."""
        try:
            from app.db.database import get_database, Collections
            
            database = await get_database()
            collection = database[Collections.COMMUNITY_MODELS]
            
            # Convert to dict
            model_dict = model.model_dump(mode='json')
            
            # Upsert by community_id
            result = await collection.update_one(
                {"community.community_id": model.community.community_id},
                {"$set": {
                    **model_dict,
                    "updated_at": datetime.now().isoformat()
                }},
                upsert=True
            )
            
            logger.info(f"Saved model to MongoDB: {model.community.community_id}")
            
        except Exception as e:
            logger.error(f"Error saving to MongoDB: {e}", exc_info=True)
            raise
    
    
    def start_watching(self):
        """Start watching for MongoDB changes."""
        if self._watch_thread is not None and self._watch_thread.is_alive():
            return
        
        if not self._mongodb_available:
            logger.warning("Cannot start watcher: MongoDB is not available")
            return
        
        self._stop_watching.clear()
        self._watch_thread = threading.Thread(target=self._watch_file, daemon=True)
        self._watch_thread.start()
        logger.info("Started MongoDB watcher for community model")
    
    def stop_watching(self):
        """Stop watching for MongoDB changes."""
        if hasattr(self, '_stop_watching'):
            self._stop_watching.set()
            if self._watch_thread is not None:
                self._watch_thread.join(timeout=2.0)
            logger.info("Stopped MongoDB watcher for community model")
    
    def _watch_file(self):
        """Watch for MongoDB changes and reload model."""
        check_interval = 5.0  # Check every 5 seconds
        
        while not self._stop_watching.is_set():
            try:
                # Check MongoDB for changes
                if self._mongodb_available:
                    try:
                        # Try to check MongoDB for changes
                        # Create new event loop in thread (watcher runs in separate thread)
                        try:
                            asyncio.run(self._check_mongodb_changes())
                        except RuntimeError:
                            # If loop exists, use it
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                loop.run_until_complete(self._check_mongodb_changes())
                            finally:
                                loop.close()
                    except Exception as e:
                        logger.debug(f"MongoDB check failed: {e}")
                
                time.sleep(check_interval)
            except Exception as e:
                logger.error(f"Error in MongoDB watcher: {e}", exc_info=True)
                time.sleep(check_interval)
    
    async def _check_mongodb_changes(self):
        """Check MongoDB for model changes."""
        try:
            from app.db.database import get_database, Collections
            
            database = await get_database()
            collection = database[Collections.COMMUNITY_MODELS]
            
            # Get latest updated_at timestamp
            doc = await collection.find_one(
                {"community.community_id": self.community_id},
                {"updated_at": 1}
            )
            
            if doc and doc.get('updated_at'):
                # Parse updated_at timestamp
                updated_str = doc.get('updated_at')
                if isinstance(updated_str, str):
                    updated_dt = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                    updated_ts = updated_dt.timestamp()
                    
                    # Reload if newer
                    if self._last_modified is None or updated_ts > self._last_modified:
                        logger.info("Detected community model change in MongoDB, reloading...")
                        await self._load_from_mongodb_async()
                        with self._lock:
                            self._last_modified = updated_ts
        except Exception as e:
            logger.debug(f"Error checking MongoDB changes: {e}")
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            if hasattr(self, '_stop_watching'):
                self.stop_watching()
        except Exception:
            pass

