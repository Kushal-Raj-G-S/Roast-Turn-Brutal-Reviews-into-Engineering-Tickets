"""
Database configuration and session management.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

load_dotenv()

# Database URL from environment variable
# Auto-switch port 5432 (Session mode) → 6543 (Transaction mode) for Supabase pooler.
# Transaction mode supports far more concurrent clients on the free tier.
_RAW_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/roast_db"
)
DATABASE_URL = _RAW_DATABASE_URL.replace(":5432/", ":6543/")

# Async Database URL (convert postgresql:// to postgresql+asyncpg://)
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://") if DATABASE_URL.startswith("postgresql://") else DATABASE_URL

# Create SQLAlchemy engine (sync)
# pool_size=2 + max_overflow=2 = max 4 connections from this engine.
# Supabase free tier Transaction mode allows ~100 concurrent connections.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=2,        # reduced from 10 — 4 total connections max
    max_overflow=2,
    pool_recycle=300,
    pool_timeout=30,
    connect_args={
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
)

# Async engine uses NullPool — Transaction mode pooler manages its own pooling.
# Using SQLAlchemy's pool on top of pgbouncer Transaction mode causes double-pooling
# and connection exhaustion. NullPool opens/closes connections per-request (cheap
# with pgbouncer because the underlying PG connection is reused by pgbouncer).
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    poolclass=NullPool,  # let pgbouncer handle pooling
    connect_args={
        "server_settings": {"jit": "off"},
        "command_timeout": 60,
    }
)

# Session factory (sync)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async session factory for v2 architecture
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI routes to get database session (sync).
    
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_session():
    """
    Dependency for FastAPI routes to get async database session.
    
    Usage:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Item))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def init_db():
    """
    Initialize database tables (create all if they don't exist).
    Using Supabase models instead of custom models.
    """
    from app.models.models_supabase import Profile, Upload, Cluster, Review, RoastResult, UserStatistics
    # Tables already exist in Supabase, just verify connection
    # Base.metadata.create_all(bind=engine)  # Disabled - tables already created in Supabase
    pass
