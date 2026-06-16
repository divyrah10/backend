from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from typing import Generator
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Convert postgresql:// to postgresql+psycopg:// for psycopg3
database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    database_url,
    poolclass=QueuePool,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=settings.DB_POOL_SIZE,  # Base pool size
    max_overflow=settings.DB_MAX_OVERFLOW,  # Extra connections when pool is exhausted
    pool_recycle=settings.DB_POOL_RECYCLE,  # Recycle connections after 1 hour
    pool_timeout=30,  # Wait up to 30s for a connection
    echo=False,  # Set to True for SQL debugging
)


# Connection pool event listeners for monitoring
@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log when a connection is checked out from the pool"""
    logger.debug("Connection checked out from pool")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Log when a connection is returned to the pool"""
    logger.debug("Connection returned to pool")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_pool_status() -> dict:
    """Get current connection pool status"""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "checked_in": pool.checkedin(),
    }
