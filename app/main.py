from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.cache import cache
from app.api.v1 import api_router
from app.db.session import engine, get_pool_status
from app.db.base import Base
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]


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
    allow_origins=origins,
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

    return {
        "status": "healthy",
        "services": {
            "database": {
                "status": "healthy",
                "pool": db_pool
            },
            "redis": {
                "status": redis_status
            }
        }
    }
