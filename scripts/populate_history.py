"""Manually populate historical data"""
import asyncio
import logging
from app.services.infrastructure.background_service import get_background_service
from app.db.database import connect_to_mongo

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def populate():
    try:
        await connect_to_mongo()
        logger.info("✓ MongoDB connected")
        
        service = get_background_service()
        service._running = True
        
        # Check initial cache status
        status = service.get_cache_status()
        logger.info(f"\n=== Before Population ===")
        logger.info(f"Today count: {status['cache_structure']['today_count']} hours")
        logger.info(f"Week count: {status['cache_structure']['week_count']} hours")
        logger.info(f"Month count: {status['cache_structure']['month_count']} hours")
        
        # Run historical population
        logger.info(f"\n=== Starting Historical Data Population ===")
        await service._pre_populate_history()
        
        # Check final cache status
        status = service.get_cache_status()
        logger.info(f"\n=== After Population ===")
        logger.info(f"Today count: {status['cache_structure']['today_count']} hours")
        logger.info(f"Week count: {status['cache_structure']['week_count']} hours")
        logger.info(f"Month count: {status['cache_structure']['month_count']} hours")
        
        logger.info("\n✓ Historical data population complete!")
        
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(populate())

