from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class Database:
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None


db = Database()


async def get_database() -> AsyncIOMotorDatabase:
    """Get database instance"""
    if db.database is None:
        logger.error("MongoDB is not connected. Ensure connect_to_mongo() ran at startup and MONGODB_URI/DATABASE_NAME are set.")
        raise RuntimeError("MongoDB not connected")
    return db.database


async def connect_to_mongo():
    """Create database connection"""
    try:
        db.client = AsyncIOMotorClient(settings.MONGODB_URI)
        db.database = db.client[settings.DATABASE_NAME]
        
        # Test the connection
        await db.client.admin.command('ping')
        logger.info("Connected to MongoDB successfully")
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


async def close_mongo_connection():
    """Close database connection"""
    if db.client:
        db.client.close()
        logger.info("Disconnected from MongoDB")


# Database collections
class Collections:
    """Database collection names - only keeping what's actually used"""
    ENERGY_ANALYTICS = "energy_analytics"
