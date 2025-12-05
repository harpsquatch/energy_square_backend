from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Don't import MongoDB at module level - import lazily when needed
MONGO_AVAILABLE = None  # Will be set when first checked
AsyncIOMotorClient = None
AsyncIOMotorDatabase = None


def _ensure_mongo_imported():
    """Lazy import MongoDB - only when actually needed"""
    global MONGO_AVAILABLE, AsyncIOMotorClient, AsyncIOMotorDatabase
    
    if MONGO_AVAILABLE is not None:
        return  # Already checked
    
    try:
        from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
        MONGO_AVAILABLE = True
        logger.debug("MongoDB (motor) imported successfully")
    except ImportError:
        logger.warning("MongoDB (motor) not available - MongoDB features will be disabled")
        MONGO_AVAILABLE = False
    except Exception as e:
        logger.warning(f"MongoDB import failed: {e} - MongoDB features will be disabled")
        MONGO_AVAILABLE = False


class Database:
    client = None
    database = None
    connected = False


db = Database()


async def get_database():
    """Get database instance"""
    _ensure_mongo_imported()
    if not MONGO_AVAILABLE:
        raise RuntimeError("MongoDB is not available (motor not installed)")
    if not db.connected:
        logger.error("MongoDB is not connected. Ensure connect_to_mongo() ran at startup and MONGODB_URI/DATABASE_NAME are set.")
        raise RuntimeError("MongoDB not connected")
    return db.database


async def connect_to_mongo():
    """Create database connection (optional - gracefully handles failures)"""
    _ensure_mongo_imported()
    
    if not MONGO_AVAILABLE:
        logger.warning("MongoDB (motor) not available - skipping MongoDB connection")
        return
    
    try:
        # Match exactly what model_service does - simple connection, let Motor parse URI
        # The URI already has tlsAllowInvalidCertificates=true, Motor will handle it
        db.client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=2000  # Same as model_service uses
        )
        db.database = db.client[settings.DATABASE_NAME]
        
        # Test the connection
        await db.client.admin.command('ping')
        db.connected = True
        logger.info("Connected to MongoDB successfully")
        
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        db.connected = False
        raise RuntimeError(f"Failed to connect to MongoDB: {e}")


async def close_mongo_connection():
    """Close database connection"""
    if db.client:
        db.client.close()
        logger.info("Disconnected from MongoDB")


# Database collections
class Collections:
    """Database collection names"""
    ENERGY_ANALYTICS = "energy_analytics"
    COMMUNITY_MODELS = "community_models"  # Store community model configurations
    SYSTEM_NOTICES = "system_notices"
    DEMAND_RESPONSE_EVENTS = "demand_response_events"  # Store DR events and participation
    USERS = "users"  # Store user accounts and authentication
    P2P_TRANSACTIONS = "p2p_transactions"  # Store P2P energy trading transactions
    P2P_PRICE_HISTORY = "p2p_price_history"  # Store price snapshots for 24h stats
    P2P_OFFERS = "p2p_offers"  # Store P2P trade offers
    P2P_REQUESTS = "p2p_requests"  # Store P2P trade requests
    ENERGY_CREDITS = "energy_credits"  # Store energy credit balances and transactions
