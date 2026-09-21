from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.cache import cache
from app.api.v1 import api_router
from app.db.session import engine, get_pool_status
from sqlalchemy import text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up NOT JUST DARK API...")

    # Check Redis connection
    if cache.is_available():
        logger.info("Redis connection established")
    else:
        logger.warning("Redis is not available - caching disabled")

    # Log database pool config
    logger.info(f"Database pool: size={settings.DB_POOL_SIZE}, max_overflow={settings.DB_MAX_OVERFLOW}")

    yield

    # Shutdown
    logger.info("Shutting down NOT JUST DARK API...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Luxury E-Commerce API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """Basic health check"""
    return {"status": "healthy"}


@app.get("/health/detailed")
def detailed_health_check():
    """Detailed health check with service status"""
    redis_status = "healthy" if cache.is_available() else "unavailable"
    db_pool = get_pool_status()
    database_status = "healthy"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    return {
        "status": "healthy",
        "services": {
            "database": {
                "status": database_status,
                "pool": db_pool
            },
            "redis": {
                "status": redis_status
            }
        }
    }
