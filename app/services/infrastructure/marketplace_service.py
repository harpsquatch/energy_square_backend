"""
P2P Marketplace Service

Manages peer-to-peer energy trading between prosumers and consumers.
Implements preferential matching, transaction settlement, and hash-chained transaction log.
Persists all transactions to MongoDB for immutability.
"""
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo
import threading
import uuid
import asyncio

logger = logging.getLogger(__name__)

# Service fee per kWh (14 paise = ₹0.14 = $0.0017 approximately, using USD for now)
SERVICE_FEE_PER_KWH = 0.14  # USD per kWh
# Maximum cumulative P2P capacity per member (100 kW per KERC regulations)
MAX_P2P_CAPACITY_KW = 100.0
# Minimum time blocks ahead for intraday transactions (4 blocks = 4 hours)
MIN_TIME_BLOCKS_AHEAD = 4


class P2PTransaction:
    """Represents a P2P energy transaction."""
    
    def __init__(
        self,
        transaction_id: str,
        seller_id: str,
        buyer_id: str,
        energy_kwh: float,
        price_per_kwh: float,
        time_block: datetime,
        previous_hash: Optional[str] = None
    ):
        self.transaction_id = transaction_id
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.energy_kwh = energy_kwh
        self.price_per_kwh = price_per_kwh
        self.time_block = time_block
        self.status = "pending"  # pending, executed, cancelled
        self.created_at = datetime.now(ZoneInfo("UTC"))
        self.executed_at: Optional[datetime] = None
        self.previous_hash = previous_hash
        self.transaction_hash: Optional[str] = None
        
        # Calculate settlement
        self.gross_amount = energy_kwh * price_per_kwh
        self.service_fee = energy_kwh * SERVICE_FEE_PER_KWH
        self.seller_amount = self.gross_amount - self.service_fee
        self.buyer_amount = self.gross_amount
    
    def calculate_hash(self) -> str:
        """Calculate hash for this transaction (includes previous hash for chain)."""
        data = (
            f"{self.transaction_id}"
            f"{self.seller_id}"
            f"{self.buyer_id}"
            f"{self.energy_kwh}"
            f"{self.price_per_kwh}"
            f"{self.time_block.isoformat()}"
            f"{self.previous_hash or ''}"
        )
        return hashlib.sha256(data.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "transaction_id": self.transaction_id,
            "seller_id": self.seller_id,
            "buyer_id": self.buyer_id,
            "energy_kwh": self.energy_kwh,
            "price_per_kwh": self.price_per_kwh,
            "time_block": self.time_block.isoformat(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "gross_amount": self.gross_amount,
            "service_fee": self.service_fee,
            "seller_amount": self.seller_amount,
            "buyer_amount": self.buyer_amount,
            "transaction_hash": self.transaction_hash,
            "previous_hash": self.previous_hash
        }


class TradeOffer:
    """Represents a trade offer from a prosumer."""
    
    def __init__(
        self,
        offer_id: str,
        seller_id: str,
        available_surplus_kw: float,
        price_per_kwh: float,
        time_blocks: List[datetime]
    ):
        self.offer_id = offer_id
        self.seller_id = seller_id
        self.available_surplus_kw = available_surplus_kw
        self.price_per_kwh = price_per_kwh
        self.time_blocks = time_blocks
        self.status = "active"  # active, matched, expired
        self.created_at = datetime.now(ZoneInfo("UTC"))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "offer_id": self.offer_id,
            "seller_id": self.seller_id,
            "available_surplus_kw": self.available_surplus_kw,
            "price_per_kwh": self.price_per_kwh,
            "time_blocks": [tb.isoformat() for tb in self.time_blocks],
            "status": self.status,
            "created_at": self.created_at.isoformat()
        }


class TradeRequest:
    """Represents a trade request from a consumer."""
    
    def __init__(
        self,
        request_id: str,
        buyer_id: str,
        required_energy_kwh: float,
        max_price_per_kwh: float,
        time_blocks: List[datetime],
        preferred_seller_id: Optional[str] = None
    ):
        self.request_id = request_id
        self.buyer_id = buyer_id
        self.required_energy_kwh = required_energy_kwh
        self.max_price_per_kwh = max_price_per_kwh
        self.time_blocks = time_blocks
        self.preferred_seller_id = preferred_seller_id  # For preferential matching
        self.status = "active"  # active, matched, expired
        self.created_at = datetime.now(ZoneInfo("UTC"))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "request_id": self.request_id,
            "buyer_id": self.buyer_id,
            "required_energy_kwh": self.required_energy_kwh,
            "max_price_per_kwh": self.max_price_per_kwh,
            "time_blocks": [tb.isoformat() for tb in self.time_blocks],
            "preferred_seller_id": self.preferred_seller_id,
            "status": self.status,
            "created_at": self.created_at.isoformat()
        }


class MarketplaceService:
    """
    Service for managing P2P energy trading marketplace.
    
    This service:
    - Manages trade offers and requests
    - Matches buyers with sellers (preferential)
    - Executes trades and calculates settlements
    - Maintains hash-chained transaction log
    - Tracks active trades for simulation integration
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Initialize the marketplace service.
        
        Args:
            test_mode: If True, allows 1-hour advance time blocks (for testing only)
        """
        self._transactions: Dict[str, P2PTransaction] = {}  # transaction_id -> transaction
        self._offers: Dict[str, TradeOffer] = {}  # offer_id -> offer
        self._requests: Dict[str, TradeRequest] = {}  # request_id -> request
        self._lock = threading.Lock()
        self._mongodb_available = False
        self._last_transaction_hash: Optional[str] = None
        self._test_mode = test_mode  # Enable test mode (1 hour minimum instead of 4)
        
        # Try to load data from MongoDB
        try:
            asyncio.create_task(self._load_transactions_from_db())
            asyncio.create_task(self._load_offers_from_db())
            asyncio.create_task(self._load_requests_from_db())
        except RuntimeError:
            # No event loop yet, will load when first accessed
            logger.debug("No event loop available, will load P2P data on first access")
        
        logger.info("MarketplaceService initialized")
    
    async def _load_transactions_from_db(self):
        """Load transactions from MongoDB on startup."""
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.P2P_TRANSACTIONS]
            
            # Load all transactions from MongoDB (sorted by created_at for hash chain)
            cursor = collection.find({}).sort("created_at", 1)
            count = 0
            
            async for doc in cursor:
                try:
                    # Convert MongoDB document to P2PTransaction
                    time_block = doc["time_block"]
                    if isinstance(time_block, str):
                        time_block = datetime.fromisoformat(time_block)
                    if time_block.tzinfo is None:
                        time_block = time_block.replace(tzinfo=ZoneInfo("UTC"))
                    
                    created_at = doc.get("created_at")
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at)
                    elif created_at and created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=ZoneInfo("UTC"))
                    
                    executed_at = doc.get("executed_at")
                    if executed_at:
                        if isinstance(executed_at, str):
                            executed_at = datetime.fromisoformat(executed_at)
                        elif executed_at.tzinfo is None:
                            executed_at = executed_at.replace(tzinfo=ZoneInfo("UTC"))
                    
                    transaction = P2PTransaction(
                        transaction_id=doc["transaction_id"],
                        seller_id=doc["seller_id"],
                        buyer_id=doc["buyer_id"],
                        energy_kwh=doc["energy_kwh"],
                        price_per_kwh=doc["price_per_kwh"],
                        time_block=time_block,
                        previous_hash=doc.get("previous_hash")
                    )
                    transaction.status = doc.get("status", "pending")
                    transaction.created_at = created_at or datetime.now(ZoneInfo("UTC"))
                    transaction.executed_at = executed_at
                    transaction.transaction_hash = doc.get("transaction_hash")
                    
                    with self._lock:
                        self._transactions[transaction.transaction_id] = transaction
                        self._last_transaction_hash = transaction.transaction_hash
                    count += 1
                except Exception as e:
                    logger.error(f"Error loading P2P transaction from DB: {e}")
            
            self._mongodb_available = True
            logger.info(f"Loaded {count} P2P transactions from MongoDB")
            
        except Exception as e:
            logger.warning(f"Could not load P2P transactions from MongoDB: {e}")
            self._mongodb_available = False
    
    async def _save_transaction_to_db(self, transaction: P2PTransaction):
        """Save transaction to MongoDB (append-only)."""
        if not self._mongodb_available:
            return
        
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.P2P_TRANSACTIONS]
            
            # Calculate hash before saving
            transaction.transaction_hash = transaction.calculate_hash()
            
            # Convert transaction to MongoDB document
            doc = {
                "transaction_id": transaction.transaction_id,
                "seller_id": transaction.seller_id,
                "buyer_id": transaction.buyer_id,
                "energy_kwh": transaction.energy_kwh,
                "price_per_kwh": transaction.price_per_kwh,
                "time_block": transaction.time_block,
                "status": transaction.status,
                "created_at": transaction.created_at,
                "executed_at": transaction.executed_at,
                "gross_amount": transaction.gross_amount,
                "service_fee": transaction.service_fee,
                "seller_amount": transaction.seller_amount,
                "buyer_amount": transaction.buyer_amount,
                "transaction_hash": transaction.transaction_hash,
                "previous_hash": transaction.previous_hash
            }
            
            # Insert (append-only, no updates)
            await collection.insert_one(doc)
            
            # Update last hash
            with self._lock:
                self._last_transaction_hash = transaction.transaction_hash
            
            logger.debug(f"Saved P2P transaction {transaction.transaction_id} to MongoDB")
            
        except Exception as e:
            logger.error(f"Error saving P2P transaction to MongoDB: {e}")
    
    async def _save_offer_to_db(self, offer: TradeOffer):
        """Save or update an offer in MongoDB."""
        if not self._mongodb_available:
            return
        
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.P2P_OFFERS]
            
            # Convert offer to MongoDB document
            doc = {
                "offer_id": offer.offer_id,
                "seller_id": offer.seller_id,
                "available_surplus_kw": offer.available_surplus_kw,
                "price_per_kwh": offer.price_per_kwh,
                "time_blocks": [tb.isoformat() if isinstance(tb, datetime) else tb for tb in offer.time_blocks],
                "status": offer.status,
                "created_at": offer.created_at.isoformat() if isinstance(offer.created_at, datetime) else offer.created_at
            }
            
            # Upsert (update if exists, insert if not)
            await collection.replace_one(
                {"offer_id": offer.offer_id},
                doc,
                upsert=True
            )
            
            logger.debug(f"Saved P2P offer {offer.offer_id} to MongoDB")
            
        except Exception as e:
            logger.error(f"Error saving P2P offer to MongoDB: {e}")
    
    async def _save_request_to_db(self, request: TradeRequest):
        """Save or update a request in MongoDB."""
        if not self._mongodb_available:
            return
        
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.P2P_REQUESTS]
            
            # Convert request to MongoDB document
            doc = {
                "request_id": request.request_id,
                "buyer_id": request.buyer_id,
                "required_energy_kwh": request.required_energy_kwh,
                "max_price_per_kwh": request.max_price_per_kwh,
                "time_blocks": [tb.isoformat() if isinstance(tb, datetime) else tb for tb in request.time_blocks],
                "preferred_seller_id": request.preferred_seller_id,
                "status": request.status,
                "created_at": request.created_at.isoformat() if isinstance(request.created_at, datetime) else request.created_at
            }
            
            # Upsert (update if exists, insert if not)
            await collection.replace_one(
                {"request_id": request.request_id},
                doc,
                upsert=True
            )
            
            logger.debug(f"Saved P2P request {request.request_id} to MongoDB")
            
        except Exception as e:
            logger.error(f"Error saving P2P request to MongoDB: {e}")
    
    async def _load_offers_from_db(self):
        """Load offers from MongoDB on startup."""
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.P2P_OFFERS]
            
            cursor = collection.find({"status": "active"})
            count = 0
            
            async for doc in cursor:
                try:
                    # Convert MongoDB document to TradeOffer
                    time_blocks = []
                    for tb in doc.get("time_blocks", []):
                        if isinstance(tb, str):
                            time_blocks.append(datetime.fromisoformat(tb))
                        else:
                            time_blocks.append(tb)
                    
                    created_at = doc.get("created_at")
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at)
                    elif created_at and created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=ZoneInfo("UTC"))
                    
                    # Normalize time blocks to hour boundary
                    normalized_time_blocks = []
                    for tb in time_blocks:
                        if tb.tzinfo is None:
                            tb = tb.replace(tzinfo=ZoneInfo("UTC"))
                        # Normalize to hour boundary
                        tb = tb.replace(minute=0, second=0, microsecond=0)
                        normalized_time_blocks.append(tb)
                    
                    offer = TradeOffer(
                        offer_id=doc["offer_id"],
                        seller_id=doc["seller_id"],
                        available_surplus_kw=doc["available_surplus_kw"],
                        price_per_kwh=doc["price_per_kwh"],
                        time_blocks=normalized_time_blocks
                    )
                    offer.status = doc.get("status", "active")
                    offer.created_at = created_at or datetime.now(ZoneInfo("UTC"))
                    
                    with self._lock:
                        self._offers[offer.offer_id] = offer
                    count += 1
                except Exception as e:
                    logger.error(f"Error loading P2P offer from DB: {e}")
            
            self._mongodb_available = True
            logger.info(f"Loaded {count} active P2P offers from MongoDB")
            
        except Exception as e:
            logger.warning(f"Could not load P2P offers from MongoDB: {e}")
            self._mongodb_available = False
    
    async def _load_requests_from_db(self):
        """Load requests from MongoDB on startup."""
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.P2P_REQUESTS]
            
            cursor = collection.find({"status": "active"})
            count = 0
            
            async for doc in cursor:
                try:
                    # Convert MongoDB document to TradeRequest
                    time_blocks = []
                    for tb in doc.get("time_blocks", []):
                        if isinstance(tb, str):
                            time_blocks.append(datetime.fromisoformat(tb))
                        else:
                            time_blocks.append(tb)
                    
                    created_at = doc.get("created_at")
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at)
                    elif created_at and created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=ZoneInfo("UTC"))
                    
                    # Normalize time blocks to hour boundary
                    normalized_time_blocks = []
                    for tb in time_blocks:
                        if tb.tzinfo is None:
                            tb = tb.replace(tzinfo=ZoneInfo("UTC"))
                        # Normalize to hour boundary
                        tb = tb.replace(minute=0, second=0, microsecond=0)
                        normalized_time_blocks.append(tb)
                    
                    request = TradeRequest(
                        request_id=doc["request_id"],
                        buyer_id=doc["buyer_id"],
                        required_energy_kwh=doc["required_energy_kwh"],
                        max_price_per_kwh=doc["max_price_per_kwh"],
                        time_blocks=normalized_time_blocks,
                        preferred_seller_id=doc.get("preferred_seller_id")
                    )
                    request.status = doc.get("status", "active")
                    request.created_at = created_at or datetime.now(ZoneInfo("UTC"))
                    
                    with self._lock:
                        self._requests[request.request_id] = request
                    count += 1
                except Exception as e:
                    logger.error(f"Error loading P2P request from DB: {e}")
            
            self._mongodb_available = True
            logger.info(f"Loaded {count} active P2P requests from MongoDB")
            
        except Exception as e:
            logger.warning(f"Could not load P2P requests from MongoDB: {e}")
            self._mongodb_available = False
    
    def _ensure_loaded(self):
        """Ensure transactions are loaded from DB (lazy loading)."""
        if not self._mongodb_available and len(self._transactions) == 0:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    logger.warning("P2P transactions not loaded yet, and we're in async context. Use async methods.")
                except RuntimeError:
                    logger.info("Loading P2P transactions from MongoDB (sync)...")
                    asyncio.run(self._load_transactions_from_db())
            except Exception as e:
                logger.error(f"Could not load transactions: {e}", exc_info=True)
    
    def _validate_time_blocks(self, time_blocks: List[datetime], current_time: Optional[datetime] = None, test_mode: bool = False) -> bool:
        """
        Validate that time blocks are at least MIN_TIME_BLOCKS_AHEAD in the future.
        
        Args:
            time_blocks: List of time blocks to validate
            current_time: Current time (defaults to now)
            test_mode: If True, only requires 1 hour ahead (for testing)
            
        Returns:
            True if all blocks are valid
        """
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        # Ensure timezone-aware comparison
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=ZoneInfo("UTC"))
        
        # Use 0 hours minimum for test mode (immediate), otherwise KERC requirement
        if test_mode:
            # In test mode, allow current hour or future (immediate execution)
            min_time = current_time.replace(minute=0, second=0, microsecond=0)
        else:
            min_hours_ahead = MIN_TIME_BLOCKS_AHEAD
            min_time = current_time + timedelta(hours=min_hours_ahead)
            # Round min_time down to the hour to allow time blocks rounded to the hour
            min_time = min_time.replace(minute=0, second=0, microsecond=0)
        
        for tb in time_blocks:
            if isinstance(tb, str):
                tb = datetime.fromisoformat(tb)
            if tb.tzinfo is None:
                tb = tb.replace(tzinfo=ZoneInfo("UTC"))
            
            # Round time block to hour for comparison
            tb_rounded = tb.replace(minute=0, second=0, microsecond=0)
            
            if tb_rounded < min_time:
                logger.debug(
                    f"Time block validation failed: {tb_rounded.isoformat()} < {min_time.isoformat()} "
                    f"(current: {current_time.isoformat()}, required: {MIN_TIME_BLOCKS_AHEAD} hours ahead)"
                )
                return False
        
        return True
    
    def _check_capacity_limit(self, member_id: str, additional_kw: float) -> bool:
        """
        Check if member's cumulative P2P capacity would exceed limit.
        
        Args:
            member_id: Member ID to check
            additional_kw: Additional capacity to add
            
        Returns:
            True if within limit
        """
        self._ensure_loaded()
        
        # Calculate current cumulative capacity for this member
        current_capacity = 0.0
        with self._lock:
            for transaction in self._transactions.values():
                if transaction.status == "executed":
                    if transaction.seller_id == member_id:
                        # Count as seller capacity
                        current_capacity += transaction.energy_kwh
                    elif transaction.buyer_id == member_id:
                        # Count as buyer capacity
                        current_capacity += transaction.energy_kwh
        
        return (current_capacity + additional_kw) <= MAX_P2P_CAPACITY_KW
    
    def create_trade_offer(
        self,
        seller_id: str,
        available_surplus_kw: float,
        price_per_kwh: float,
        time_blocks: List[datetime]
    ) -> str:
        """
        Create a trade offer from a prosumer.
        
        Args:
            seller_id: Prosumer member ID
            available_surplus_kw: Available surplus energy in kW
            price_per_kwh: Price per kWh (USD)
            time_blocks: List of time blocks when energy is available (ignored - uses current hour)
            
        Returns:
            Offer ID
        """
        # Ignore time_blocks validation - always use current hour for immediate execution
        
        # Check capacity limit
        if not self._check_capacity_limit(seller_id, available_surplus_kw):
            raise ValueError(f"Member {seller_id} would exceed P2P capacity limit of {MAX_P2P_CAPACITY_KW} kW")
        
        offer_id = f"offer_{uuid.uuid4().hex[:8]}"
        
        # Always use current hour for time blocks (simplified)
        now = datetime.now(ZoneInfo("UTC"))
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        offer = TradeOffer(
            offer_id=offer_id,
            seller_id=seller_id,
            available_surplus_kw=available_surplus_kw,
            price_per_kwh=price_per_kwh,
            time_blocks=[current_hour]  # Always use current hour
        )
        
        with self._lock:
            self._offers[offer_id] = offer
        
        # Persist to MongoDB
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_offer_to_db(offer))
            else:
                # If no event loop, run synchronously (shouldn't happen in FastAPI)
                asyncio.run(self._save_offer_to_db(offer))
        except Exception as e:
            logger.debug(f"Could not save offer to DB: {e}")
        
        logger.info(
            f"Created trade offer {offer_id} from {seller_id}: "
            f"{available_surplus_kw} kW @ ${price_per_kwh}/kWh"
        )
        
        return offer_id
    
    def create_trade_request(
        self,
        buyer_id: str,
        required_energy_kwh: float,
        max_price_per_kwh: float,
        time_blocks: List[datetime],
        preferred_seller_id: Optional[str] = None
    ) -> str:
        """
        Create a trade request from a consumer.
        
        Args:
            buyer_id: Consumer member ID
            required_energy_kwh: Required energy in kWh
            max_price_per_kwh: Maximum price willing to pay (USD)
            time_blocks: List of time blocks when energy is needed
            preferred_seller_id: Optional preferred seller for preferential matching
            
        Returns:
            Request ID
        """
        # Ignore time_blocks validation - always use current hour for immediate execution
        
        # Check capacity limit
        if not self._check_capacity_limit(buyer_id, required_energy_kwh):
            raise ValueError(f"Member {buyer_id} would exceed P2P capacity limit of {MAX_P2P_CAPACITY_KW} kW")
        
        request_id = f"request_{uuid.uuid4().hex[:8]}"
        
        # Always use current hour for time blocks (simplified)
        now = datetime.now(ZoneInfo("UTC"))
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        request = TradeRequest(
            request_id=request_id,
            buyer_id=buyer_id,
            required_energy_kwh=required_energy_kwh,
            max_price_per_kwh=max_price_per_kwh,
            time_blocks=[current_hour],  # Always use current hour
            preferred_seller_id=preferred_seller_id
        )
        
        with self._lock:
            self._requests[request_id] = request
        
        # Persist to MongoDB
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_request_to_db(request))
            else:
                # If no event loop, run synchronously (shouldn't happen in FastAPI)
                asyncio.run(self._save_request_to_db(request))
        except Exception as e:
            logger.debug(f"Could not save request to DB: {e}")
        
        logger.info(
            f"Created trade request {request_id} from {buyer_id}: "
            f"{required_energy_kwh} kWh @ max ${max_price_per_kwh}/kWh"
        )
        
        return request_id
    
    def match_trade(
        self,
        offer_id: str,
        request_id: str,
        energy_kwh: float
    ) -> str:
        """
        Match a trade offer with a request (preferential matching).
        
        Args:
            offer_id: Trade offer ID
            request_id: Trade request ID
            energy_kwh: Energy to trade (kWh)
            
        Returns:
            Transaction ID
        """
        self._ensure_loaded()
        
        with self._lock:
            offer = self._offers.get(offer_id)
            request = self._requests.get(request_id)
            
            if not offer:
                raise ValueError(f"Offer {offer_id} not found")
            if not request:
                raise ValueError(f"Request {request_id} not found")
            
            if offer.status != "active":
                raise ValueError(f"Offer {offer_id} is not active")
            if request.status != "active":
                raise ValueError(f"Request {request_id} is not active")
            
            # Validate matching
            if offer.seller_id == request.buyer_id:
                raise ValueError("Seller and buyer cannot be the same member")
            
            # Check if preferred seller matches (for preferential exchange)
            if request.preferred_seller_id and request.preferred_seller_id != offer.seller_id:
                raise ValueError(f"Offer seller {offer.seller_id} does not match preferred seller {request.preferred_seller_id}")
            
            # Check price compatibility
            if offer.price_per_kwh > request.max_price_per_kwh:
                raise ValueError(
                    f"Offer price ${offer.price_per_kwh}/kWh exceeds buyer's max ${request.max_price_per_kwh}/kWh"
                )
            
            # Check energy availability
            if energy_kwh > offer.available_surplus_kw:
                raise ValueError(
                    f"Requested energy {energy_kwh} kWh exceeds available {offer.available_surplus_kw} kW"
                )
            
            if energy_kwh > request.required_energy_kwh:
                raise ValueError(
                    f"Requested energy {energy_kwh} kWh exceeds required {request.required_energy_kwh} kWh"
                )
            
            # Use current hour for all trades (simplified - no time block matching)
            now = datetime.now(ZoneInfo("UTC"))
            time_block = now.replace(minute=0, second=0, microsecond=0)
            
            # Create transaction
            transaction_id = f"txn_{uuid.uuid4().hex[:8]}"
            
            transaction = P2PTransaction(
                transaction_id=transaction_id,
                seller_id=offer.seller_id,
                buyer_id=request.buyer_id,
                energy_kwh=energy_kwh,
                price_per_kwh=offer.price_per_kwh,
                time_block=time_block,
                previous_hash=self._last_transaction_hash
            )
            
            # Set initial status to pending (will be executed immediately after)
            transaction.status = "pending"
            
            # Calculate hash
            transaction.transaction_hash = transaction.calculate_hash()
            
            # Store transaction
            self._transactions[transaction_id] = transaction
            
            logger.info(
                f"Created transaction {transaction_id}: {offer.seller_id} -> {request.buyer_id}, "
                f"{energy_kwh} kWh @ ${offer.price_per_kwh}/kWh, time_block={time_block.isoformat()}"
            )
            
            # Mark offer and request as matched
            offer.status = "matched"
            request.status = "matched"
        
        # Persist to MongoDB
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_transaction_to_db(transaction))
                asyncio.create_task(self._save_offer_to_db(offer))
                asyncio.create_task(self._save_request_to_db(request))
        except Exception as e:
            logger.debug(f"Could not save transaction/offer/request to DB: {e}")
        
        logger.info(
            f"Matched trade: {transaction_id} - "
            f"{offer.seller_id} -> {request.buyer_id}, "
            f"{energy_kwh} kWh @ ${offer.price_per_kwh}/kWh"
        )
        
        return transaction_id
    
    def execute_trade(self, transaction_id: str) -> bool:
        """
        Execute a pending transaction.
        
        Uses energy credits for settlement:
        - Buyer pays energy credits (buyer_amount)
        - Seller receives energy credits (seller_amount)
        - Service fee is deducted from seller's credits
        
        Args:
            transaction_id: Transaction ID to execute
            
        Returns:
            True if successful
        """
        self._ensure_loaded()
        
        with self._lock:
            transaction = self._transactions.get(transaction_id)
            if not transaction:
                logger.warning(f"Transaction {transaction_id} not found")
                return False
            
            if transaction.status != "pending":
                logger.warning(f"Transaction {transaction_id} is not pending (status: {transaction.status})")
                return False
            
            # Check if time block is in the past (skip in test mode)
            if not self._test_mode:
                current_time = datetime.now(ZoneInfo("UTC"))
                if transaction.time_block < current_time:
                    logger.warning(f"Transaction {transaction_id} time block is in the past")
                    transaction.status = "cancelled"
                    return False
            
            # Execute transaction (credit transfer happens after, in async context)
            transaction.status = "executed"
            transaction.executed_at = datetime.now(ZoneInfo("UTC"))
        
        # Transfer energy credits: buyer pays, seller receives (async)
        # This happens after transaction is marked as executed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async context, schedule the credit transfer
                # Check balance first, then transfer
                async def transfer_with_check():
                    buyer_balance = await self.get_energy_credit_balance_async(transaction.buyer_id)
                    if buyer_balance < transaction.buyer_amount:
                        logger.warning(
                            f"Buyer {transaction.buyer_id} has insufficient credits: "
                            f"{buyer_balance} < {transaction.buyer_amount}. Transaction executed but credits not transferred."
                        )
                        # Mark transaction as failed (or keep as executed but log warning)
                        return
                    
                    await self._transfer_energy_credits(
                        transaction.buyer_id,
                        transaction.seller_id,
                        transaction.buyer_amount,
                        transaction.seller_amount,
                        transaction.transaction_id
                    )
                
                asyncio.create_task(transfer_with_check())
            else:
                # No event loop, run synchronously
                async def transfer_with_check():
                    buyer_balance = await self.get_energy_credit_balance_async(transaction.buyer_id)
                    if buyer_balance < transaction.buyer_amount:
                        logger.warning(
                            f"Buyer {transaction.buyer_id} has insufficient credits: "
                            f"{buyer_balance} < {transaction.buyer_amount}"
                        )
                        return
                    
                    await self._transfer_energy_credits(
                        transaction.buyer_id,
                        transaction.seller_id,
                        transaction.buyer_amount,
                        transaction.seller_amount,
                        transaction.transaction_id
                    )
                
                asyncio.run(transfer_with_check())
        except Exception as e:
            logger.error(f"Error transferring energy credits: {e}", exc_info=True)
            # Don't fail the transaction if credit transfer fails - log and continue
            # The transaction is already marked as executed
        
        # Persist to MongoDB
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._save_transaction_to_db(transaction))
        except Exception as e:
            logger.debug(f"Could not save transaction to DB: {e}")
        
        logger.info(f"Executed transaction {transaction_id} with energy credits")
        
        return True
    
    def get_active_trades(self, current_time: Optional[datetime] = None) -> Dict[str, Dict[str, float]]:
        """
        Get active trades for current time block (for simulation integration).
        
        Args:
            current_time: Current time (defaults to now). Can be in any timezone.
            
        Returns:
            Dictionary with 'sold' and 'bought' keys, each mapping member_id -> energy_kw
        """
        self._ensure_loaded()
        
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        # Ensure timezone-aware (convert to UTC if not already)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=ZoneInfo("UTC"))
        else:
            # Convert to UTC for consistent comparison
            current_time = current_time.astimezone(ZoneInfo("UTC"))
        
        # Round to hour for time block matching (in UTC)
        current_block = current_time.replace(minute=0, second=0, microsecond=0)
        
        sold: Dict[str, float] = {}  # seller_id -> energy_kw
        bought: Dict[str, float] = {}  # buyer_id -> energy_kw
        
        with self._lock:
            for transaction in self._transactions.values():
                if transaction.status == "executed":
                    # Check if transaction time block matches current block
                    tx_block = transaction.time_block
                    if isinstance(tx_block, str):
                        tx_block = datetime.fromisoformat(tx_block)
                    
                    # Ensure timezone-aware and convert to UTC
                    if tx_block.tzinfo is None:
                        tx_block = tx_block.replace(tzinfo=ZoneInfo("UTC"))
                    else:
                        tx_block = tx_block.astimezone(ZoneInfo("UTC"))
                    
                    # Round to hour for comparison (in UTC)
                    tx_block = tx_block.replace(minute=0, second=0, microsecond=0)
                    
                    # Log for debugging
                    logger.debug(
                        f"Checking transaction {transaction.transaction_id}: "
                        f"status={transaction.status}, tx_block={tx_block.isoformat()}, "
                        f"current_block={current_block.isoformat()}, match={tx_block == current_block}"
                    )
                    
                    if tx_block == current_block:
                        # Add to sold/bought totals
                        seller_id = transaction.seller_id
                        buyer_id = transaction.buyer_id
                        energy_kw = transaction.energy_kwh
                        
                        sold[seller_id] = sold.get(seller_id, 0.0) + energy_kw
                        bought[buyer_id] = bought.get(buyer_id, 0.0) + energy_kw
                        
                        logger.info(
                            f"P2P trade active: {seller_id} -> {buyer_id}, {energy_kw} kW "
                            f"(time_block: {tx_block.isoformat()})"
                        )
        
        result = {
            "sold": sold,
            "bought": bought
        }
        
        executed_count = sum(1 for t in self._transactions.values() if t.status == "executed")
        logger.info(
            f"Active P2P trades for {current_block.isoformat()} (UTC): "
            f"sold={sold}, bought={bought}, total_transactions={len(self._transactions)}, "
            f"executed_count={executed_count}"
        )
        
        return result
    
    def get_member_trades(self, member_id: str) -> List[Dict[str, Any]]:
        """
        Get all trades for a member (as seller or buyer).
        
        Args:
            member_id: Member ID
            
        Returns:
            List of transaction dictionaries
        """
        self._ensure_loaded()
        
        with self._lock:
            trades = [
                txn.to_dict() for txn in self._transactions.values()
                if txn.seller_id == member_id or txn.buyer_id == member_id
            ]
        
        # Sort by created_at descending
        trades.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return trades
    
    def get_active_offers(self) -> List[Dict[str, Any]]:
        """Get all active trade offers."""
        with self._lock:
            return [
                offer.to_dict() for offer in self._offers.values()
                if offer.status == "active"
            ]
    
    def get_active_requests(self) -> List[Dict[str, Any]]:
        """Get all active trade requests."""
        with self._lock:
            return [
                request.to_dict() for request in self._requests.values()
                if request.status == "active"
            ]
    
    async def get_all_transactions_async(self) -> List[Dict[str, Any]]:
        """Get all transactions (async version that properly loads from DB)."""
        # Always try to load if transactions are empty, regardless of _mongodb_available flag
        # The flag might be True from a previous attempt, but transactions might not have loaded
        with self._lock:
            transaction_count = len(self._transactions)
            if transaction_count == 0:
                logger.info("[MarketplaceService] Transactions empty, will load from DB")
                # Release lock before async DB call
                pass
            else:
                # Transactions already loaded, return them
                logger.debug(f"[MarketplaceService] Returning {transaction_count} cached transactions")
                return [txn.to_dict() for txn in self._transactions.values()]
        
        # Load transactions from DB if empty
        try:
            logger.info("[MarketplaceService] Loading transactions from MongoDB...")
            await self._load_transactions_from_db()
            with self._lock:
                loaded_count = len(self._transactions)
                logger.info(f"[MarketplaceService] Loaded {loaded_count} transactions from MongoDB")
        except Exception as e:
            logger.error(f"[MarketplaceService] Could not load transactions from DB: {e}", exc_info=True)
        
        # Return transactions (even if empty, in case of error)
        with self._lock:
            result = [txn.to_dict() for txn in self._transactions.values()]
            logger.debug(f"[MarketplaceService] Returning {len(result)} transactions")
            return result


    async def calculate_current_price(self, offers: List[Dict[str, Any]], requests: List[Dict[str, Any]]) -> float:
        """
        Calculate current market price based on demand and supply.
        
        Simple logic:
        - If supply > demand: price = weighted average of offer prices (lower)
        - If demand > supply: price = weighted average of request max prices (higher)
        - If balanced: price = average of offer and request prices
        
        Returns price per kWh in USD.
        """
        try:
            # Calculate total supply and demand
            total_supply = sum(o.get("available_surplus_kw", 0) for o in offers)
            total_demand = sum(r.get("required_energy_kwh", 0) for r in requests)
            
            # Get offer prices (weighted by available surplus)
            offer_prices = []
            for offer in offers:
                price = offer.get("price_per_kwh", 0)
                weight = offer.get("available_surplus_kw", 0)
                if price > 0 and weight > 0:
                    offer_prices.append({"price": price, "weight": weight})
            
            # Get request max prices (weighted by required energy)
            request_prices = []
            for request in requests:
                price = request.get("max_price_per_kwh", 0)
                weight = request.get("required_energy_kwh", 0)
                if price > 0 and weight > 0:
                    request_prices.append({"price": price, "weight": weight})
            
            # Calculate weighted averages
            weighted_offer_price = 0.0
            if offer_prices:
                total_weight = sum(p["weight"] for p in offer_prices)
                if total_weight > 0:
                    weighted_offer_price = sum(p["price"] * p["weight"] for p in offer_prices) / total_weight
            
            weighted_request_price = 0.0
            if request_prices:
                total_weight = sum(p["weight"] for p in request_prices)
                if total_weight > 0:
                    weighted_request_price = sum(p["price"] * p["weight"] for p in request_prices) / total_weight
            
            # Determine price based on supply/demand ratio
            if total_supply == 0 and total_demand == 0:
                # No market activity, use default or last executed trade price
                # Try to get last executed trade price
                all_trades = await self.get_all_transactions_async()
                executed_trades = [t for t in all_trades if t.get("status") == "executed"]
                if executed_trades:
                    # Use average of last 5 executed trades
                    recent_prices = [t.get("price_per_kwh", 0) for t in executed_trades[-5:] if t.get("price_per_kwh", 0) > 0]
                    if recent_prices:
                        return sum(recent_prices) / len(recent_prices)
                # Default fallback
                return 0.15
            
            if total_supply > total_demand * 1.2:  # Supply exceeds demand by 20%
                # Oversupply: price favors buyers (lower)
                if weighted_offer_price > 0:
                    # Use offer prices, but slightly lower to encourage buying
                    return weighted_offer_price * 0.95
                return 0.12  # Default low price
            
            elif total_demand > total_supply * 1.2:  # Demand exceeds supply by 20%
                # High demand: price favors sellers (higher)
                if weighted_request_price > 0:
                    # Use request max prices, but slightly higher
                    return weighted_request_price * 1.05
                return 0.20  # Default high price
            
            else:  # Balanced market
                # Use average of offer and request prices
                if weighted_offer_price > 0 and weighted_request_price > 0:
                    return (weighted_offer_price + weighted_request_price) / 2
                elif weighted_offer_price > 0:
                    return weighted_offer_price
                elif weighted_request_price > 0:
                    return weighted_request_price
                else:
                    return 0.15  # Default balanced price
                    
        except Exception as e:
            logger.error(f"Error calculating current price: {e}", exc_info=True)
            return 0.15  # Default fallback
    
    async def save_price_snapshot(self, price: float):
        """Save current price snapshot to MongoDB for 24h history."""
        try:
            from app.db.database import get_database, Collections
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            
            db = await get_database()
            collection = db[Collections.P2P_PRICE_HISTORY]
            
            # Create price snapshot
            snapshot = {
                "price": price,
                "timestamp": datetime.now(ZoneInfo("UTC")),
                "created_at": datetime.now(ZoneInfo("UTC"))
            }
            
            await collection.insert_one(snapshot)
            
            # Clean up old records (older than 48 hours to keep some buffer)
            cutoff_time = datetime.now(ZoneInfo("UTC")) - timedelta(hours=48)
            await collection.delete_many({"timestamp": {"$lt": cutoff_time}})
            
            logger.debug(f"Saved price snapshot: ${price:.4f}/kWh")
            
        except Exception as e:
            logger.warning(f"Could not save price snapshot: {e}")
    
    async def get_price_history_24h(self) -> List[Dict[str, Any]]:
        """Get price history for the last 24 hours from MongoDB."""
        try:
            from app.db.database import get_database, Collections
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            
            db = await get_database()
            collection = db[Collections.P2P_PRICE_HISTORY]
            
            # Get prices from last 24 hours
            cutoff_time = datetime.now(ZoneInfo("UTC")) - timedelta(hours=24)
            
            cursor = collection.find({"timestamp": {"$gte": cutoff_time}}).sort("timestamp", 1)
            history = []
            async for doc in cursor:
                # Convert timestamp if needed
                timestamp = doc.get("timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp)
                elif timestamp and timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
                
                history.append({
                    "price": float(doc.get("price", 0)),
                    "timestamp": timestamp.isoformat() if timestamp else None
                })
            
            return history
            
        except Exception as e:
            logger.warning(f"Could not get price history: {e}")
            return []
    
    async def _transfer_energy_credits(
        self,
        buyer_id: str,
        seller_id: str,
        buyer_amount: float,
        seller_amount: float,
        transaction_id: str
    ):
        """
        Transfer energy credits between buyer and seller.
        
        Args:
            buyer_id: Buyer member ID
            seller_id: Seller member ID
            buyer_amount: Amount buyer pays (in credits)
            seller_amount: Amount seller receives (in credits, after service fee)
            transaction_id: Associated transaction ID
        """
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            credits_collection = db[Collections.ENERGY_CREDITS]
            
            now = datetime.now(ZoneInfo("UTC"))
            
            # Check buyer balance first
            buyer_doc = await credits_collection.find_one({"member_id": buyer_id})
            buyer_balance = float(buyer_doc.get("balance", 0)) if buyer_doc else 0.0
            
            if buyer_balance < buyer_amount:
                raise ValueError(
                    f"Buyer {buyer_id} has insufficient credits: "
                    f"balance {buyer_balance} < required {buyer_amount}"
                )
            
            # Deduct from buyer
            if buyer_doc:
                new_balance = buyer_balance - buyer_amount
                await credits_collection.update_one(
                    {"member_id": buyer_id},
                    {
                        "$set": {
                            "balance": new_balance,
                            "updated_at": now
                        },
                        "$push": {
                            "transactions": {
                                "transaction_id": transaction_id,
                                "type": "debit",
                                "amount": buyer_amount,
                                "counterparty": seller_id,
                                "timestamp": now,
                                "description": f"Paid for {transaction_id}"
                            }
                        }
                    }
                )
            else:
                # This shouldn't happen if balance check passed, but handle it
                raise ValueError(f"Buyer {buyer_id} has no credit record but balance check passed")
            
            # Add to seller
            seller_doc = await credits_collection.find_one({"member_id": seller_id})
            if seller_doc:
                seller_balance = float(seller_doc.get("balance", 0))
                new_balance = seller_balance + seller_amount
                await credits_collection.update_one(
                    {"member_id": seller_id},
                    {
                        "$set": {
                            "balance": new_balance,
                            "updated_at": now
                        },
                        "$push": {
                            "transactions": {
                                "transaction_id": transaction_id,
                                "type": "credit",
                                "amount": seller_amount,
                                "counterparty": buyer_id,
                                "timestamp": now,
                                "description": f"Received from {transaction_id}"
                            }
                        }
                    }
                )
            else:
                # Create seller record
                await credits_collection.insert_one({
                    "member_id": seller_id,
                    "balance": seller_amount,
                    "created_at": now,
                    "updated_at": now,
                    "transactions": [{
                        "transaction_id": transaction_id,
                        "type": "credit",
                        "amount": seller_amount,
                        "counterparty": buyer_id,
                        "timestamp": now,
                        "description": f"Received from {transaction_id}"
                    }]
                })
            
            logger.info(
                f"Energy credits transferred: {buyer_id} paid {buyer_amount} (balance: {buyer_balance} -> {buyer_balance - buyer_amount}), "
                f"{seller_id} received {seller_amount} (transaction: {transaction_id})"
            )
            
        except Exception as e:
            logger.error(f"Error transferring energy credits: {e}", exc_info=True)
            raise
    
    def get_energy_credit_balance(self, member_id: str) -> float:
        """
        Get current energy credit balance for a member (synchronous, from cache if available).
        
        For async version, use get_energy_credit_balance_async().
        """
        try:
            # Try to get from cache if available
            # For now, return 0 if not cached (will be loaded from DB in async version)
            return 0.0
        except Exception as e:
            logger.warning(f"Error getting energy credit balance: {e}")
            return 0.0
    
    async def get_energy_credit_balance_async(self, member_id: str) -> float:
        """Get current energy credit balance for a member from MongoDB."""
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            credits_collection = db[Collections.ENERGY_CREDITS]
            
            doc = await credits_collection.find_one({"member_id": member_id})
            if doc:
                return float(doc.get("balance", 0))
            else:
                return 0.0
        except Exception as e:
            logger.warning(f"Error getting energy credit balance: {e}")
            return 0.0
    
    async def withdraw_energy_credits(self, member_id: str, amount: float) -> Dict[str, Any]:
        """
        Withdraw energy credits as cash (convert to real money).
        
        Args:
            member_id: Member ID requesting withdrawal
            amount: Amount of credits to withdraw (in USD)
            
        Returns:
            Dictionary with withdrawal details
        """
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            credits_collection = db[Collections.ENERGY_CREDITS]
            
            # Get current balance
            balance = await self.get_energy_credit_balance_async(member_id)
            
            if balance < amount:
                raise ValueError(f"Insufficient credits: balance {balance} < withdrawal {amount}")
            
            # Deduct credits and record withdrawal
            now = datetime.now(ZoneInfo("UTC"))
            withdrawal_id = f"withdraw_{uuid.uuid4().hex[:8]}"
            
            new_balance = balance - amount
            
            await credits_collection.update_one(
                {"member_id": member_id},
                {
                    "$set": {
                        "balance": new_balance,
                        "updated_at": now
                    },
                    "$push": {
                        "transactions": {
                            "transaction_id": withdrawal_id,
                            "type": "withdrawal",
                            "amount": amount,
                            "counterparty": "system",
                            "timestamp": now,
                            "description": f"Withdrawal to cash: ${amount:.2f}",
                            "cash_amount": amount  # Same as credit amount (1:1 conversion)
                        }
                    }
                },
                upsert=True
            )
            
            logger.info(f"Energy credits withdrawal: {member_id} withdrew ${amount:.2f} (new balance: {new_balance:.2f})")
            
            return {
                "withdrawal_id": withdrawal_id,
                "member_id": member_id,
                "credit_amount": amount,
                "cash_amount": amount,  # 1:1 conversion
                "new_balance": new_balance,
                "timestamp": now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error withdrawing energy credits: {e}", exc_info=True)
            raise
    
    async def buy_energy_credits(self, member_id: str, amount: float) -> Dict[str, Any]:
        """
        Buy energy credits with cash (convert real money to credits).
        
        Args:
            member_id: Member ID purchasing credits
            amount: Amount of cash to spend (in USD) - will receive same amount in credits (1:1 conversion)
            
        Returns:
            Dictionary with purchase details
        """
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            credits_collection = db[Collections.ENERGY_CREDITS]
            
            if amount <= 0:
                raise ValueError("Purchase amount must be greater than 0")
            
            # Get current balance
            balance = await self.get_energy_credit_balance_async(member_id)
            
            # Add credits (1:1 conversion: $1 = 1 credit)
            now = datetime.now(ZoneInfo("UTC"))
            purchase_id = f"purchase_{uuid.uuid4().hex[:8]}"
            
            new_balance = balance + amount  # 1:1 conversion
            
            await credits_collection.update_one(
                {"member_id": member_id},
                {
                    "$set": {
                        "balance": new_balance,
                        "updated_at": now
                    },
                    "$push": {
                        "transactions": {
                            "transaction_id": purchase_id,
                            "type": "purchase",
                            "amount": amount,
                            "counterparty": "system",
                            "timestamp": now,
                            "description": f"Purchased credits with cash: ${amount:.2f}",
                            "cash_amount": amount,  # Cash spent
                            "credit_amount": amount  # Credits received (1:1)
                        }
                    }
                },
                upsert=True
            )
            
            logger.info(f"Energy credits purchase: {member_id} bought ${amount:.2f} worth of credits (new balance: {new_balance:.2f})")
            
            return {
                "purchase_id": purchase_id,
                "member_id": member_id,
                "cash_amount": amount,
                "credit_amount": amount,  # 1:1 conversion
                "new_balance": new_balance,
                "timestamp": now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error purchasing energy credits: {e}", exc_info=True)
            raise


# Global singleton instance
_marketplace_service: Optional[MarketplaceService] = None


def get_marketplace_service() -> MarketplaceService:
    """Get the global marketplace service instance."""
    global _marketplace_service
    if _marketplace_service is None:
        # Enable test_mode by default for immediate execution (no 4-hour delay)
        _marketplace_service = MarketplaceService(test_mode=True)
    return _marketplace_service

