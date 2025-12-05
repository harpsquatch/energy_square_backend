import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
# Lazy import MongoDB to avoid hanging on Windows
from app.routers.main import api_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set up CORS - Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "*"  # Allow all origins in development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting up Energy Square API...")
    try:
        # Lazy import to avoid hanging on Windows during module import
        from app.db.database import connect_to_mongo
        await connect_to_mongo()
    except KeyboardInterrupt:
        raise
    except Exception as e:
        logger.warning(f"MongoDB connection skipped: {e}. App will continue with CSV-based services.")
    
    # Initialize Demand Response Service and load events
    try:
        from app.services.infrastructure.demand_response_service import get_demand_response_service
        dr_service = get_demand_response_service()
        await dr_service._load_events_from_db()
        logger.info("Demand Response service initialized")
    except Exception as e:
        logger.warning(f"Could not initialize DR service: {e}")
    
    # Initialize Marketplace Service and load data
    try:
        from app.services.infrastructure.marketplace_service import get_marketplace_service
        marketplace_service = get_marketplace_service()
        await marketplace_service._load_transactions_from_db()
        await marketplace_service._load_offers_from_db()
        await marketplace_service._load_requests_from_db()
        logger.info("Marketplace service initialized (transactions, offers, requests loaded)")
    except Exception as e:
        logger.warning(f"Could not initialize Marketplace service: {e}")
    
    # Verify MongoDB connection and model availability
    # Note: Services are now lazily initialized in routers to avoid startup failures
    # We just verify MongoDB is connected here
    try:
        from app.db.database import get_database, Collections
        
        database = await get_database()
        collection = database[Collections.COMMUNITY_MODELS]
        
        # Test query to see if any documents exist
        test_doc = await collection.find_one({})
        if test_doc:
            logger.info(f"MongoDB connected - found at least one document in '{Collections.COMMUNITY_MODELS}' collection")
            # Log document structure for debugging
            community_data = test_doc.get("community", {})
            doc_community_id = community_data.get("community_id") if isinstance(community_data, dict) else None
            logger.info(f"Sample document has community_id: {doc_community_id}")
        else:
            logger.warning(f"MongoDB connected but no documents found in '{Collections.COMMUNITY_MODELS}' collection")
    except Exception as e:
        logger.error(f"Could not verify MongoDB connection: {e}", exc_info=True)
        # Don't raise - let the app continue, services will fail gracefully with better error messages
    
    # Start background simulation service
    try:
        from app.services.infrastructure.background_service import get_background_service
        background_service = get_background_service()
        
        # Properly start the service (this will trigger historical data population)
        if not background_service._running:
            background_service._running = True
            
            # Create the background update loop task
            logger.info("Creating background update loop task...")
            loop = asyncio.get_event_loop()
            background_service._update_task = loop.create_task(background_service._background_update_loop())
            logger.info("Background update loop task created")
            
            # Trigger historical data population
            logger.info("Creating historical data population task...")
            history_task = loop.create_task(background_service._pre_populate_history())
            logger.info(f"Historical data population task created: {history_task}")
            
            logger.info("Background simulation service started - both tasks initiated")
        else:
            logger.info("Background simulation service already running")
    except Exception as e:
        logger.error(f"Failed to start background simulation service: {e}", exc_info=True)
    
    logger.info("Energy Square API started successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Energy Square API...")
    
    # Stop background simulation service
    try:
        from app.services.infrastructure.background_service import get_background_service
        background_service = get_background_service()
        background_service.stop()
        logger.info("Background simulation service stopped")
    except Exception as e:
        logger.warning(f"Error stopping background simulation service: {e}")
    
    try:
        from app.db.database import close_mongo_connection
        await close_mongo_connection()
    except Exception:
        pass  # MongoDB might not be available
    logger.info("Energy Square API shut down successfully!")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Energy Square API",
        "version": settings.VERSION,
        "docs": f"{settings.API_V1_STR}/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/cors-test")
async def cors_test():
    """CORS test endpoint"""
    return {
        "message": "CORS is working!",
        "cors_origins": cors_origins,
        "environment": settings.ENVIRONMENT
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.ENVIRONMENT == "development" else False
    )

