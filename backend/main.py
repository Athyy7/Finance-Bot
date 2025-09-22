from contextlib import asynccontextmanager
from multiprocessing import get_logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Fixed imports (relative where possible)
from .app.apis.test_route import router as test_router
from .app.apis.streaming_chat_route import router as streaming_chat_router
from .app.config.database import create_db_and_tables, mongodb_database
from .app.repositories.error_repository import ErrorRepo as ErrorRepository
from .app.utils.error_handler import handle_exceptions
from backend.app.services.database_seeding_service import database_seeding_service


# Create FastAPI application
logger = get_logger()
logger.setLevel("INFO")


@asynccontextmanager
async def db_lifespan(app: FastAPI):
    # Connect to MongoDB
    mongodb_database.connect()
    logger.info("Connected to MongoDB")
    
    # Seed financial data collection if needed
    try:
        await database_seeding_service.seed_financial_data_collection()
        logger.info("Database seeding check completed")
    except Exception as e:
        logger.error(f"Error during database seeding: {str(e)}")

        # Don't fail startup if seeding fails - log the error and continue
    
    yield
    
    # Disconnect from MongoDB on shutdown
    mongodb_database.disconnect()
    logger.info("Disconnected from MongoDB")


app = FastAPI(
    title="Finance Bot API",
    description="A streaming agentic chatbot for finance assistance",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=db_lifespan
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(test_router, prefix="/api/v1", tags=["test"])
app.include_router(streaming_chat_router, prefix="/api/v1", tags=["chat"])  # fixed name


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Finance Bot API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "chat_stream": "/api/v1/chat/stream",
            "conversations": "/api/v1/chat/conversations",
            "health": "/api/v1/chat/health",
            "database_status": "/database/status",
            "manual_seed": "/database/seed"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "finance_bot_api"}


@app.get("/database/status")
async def database_status():
    """Check database seeding status."""
    try:
        status = await database_seeding_service.check_collection_status()
        return {
            "status": "success",
            "financial_data_collection": status
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/database/seed")
async def manual_seed():
    """Manually trigger database seeding (useful for testing or manual setup)."""
    try:
        result = await database_seeding_service.seed_financial_data_collection()
        if result:
            status = await database_seeding_service.check_collection_status()
            return {
                "status": "success",
                "message": "Database seeding completed successfully",
                "collection_status": status
            }
        else:
            return {
                "status": "error",
                "message": "Database seeding failed"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error during manual seeding: {str(e)}"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
