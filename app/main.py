from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.database import connect_to_mongo, close_mongo_connection
from app.routers.main import api_router
import logging

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

# Set up CORS
cors_origins = settings.BACKEND_CORS_ORIGINS
if settings.ENVIRONMENT == "development":
    # In development, allow all origins for easier testing
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True if cors_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting up Energy Square API...")
    await connect_to_mongo()
    logger.info("Energy Square API started successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Energy Square API...")
    await close_mongo_connection()
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

