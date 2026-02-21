"""
Database models for bulk review processing (optimized system).
Uses the 'uploads' and 'clusters' tables created in Supabase.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel, create_engine, Session, select
from sqlalchemy import Column, DateTime, func, Integer


class Upload(SQLModel, table=True):
    """Represents a CSV upload job."""
    
    __tablename__ = "uploads"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    user_id: UUID = Field(foreign_key="profiles.id")
    filename: str
    file_size_bytes: Optional[int] = Field(default=None)
    total_reviews: Optional[int] = Field(default=None)
    status: str = Field(default="pending")  # pending, processing, completed, failed
    error_message: Optional[str] = Field(default=None)
    processed_reviews: Optional[int] = Field(default=None)
    filtered_noise: Optional[int] = Field(default=None)
    clusters_created: Optional[int] = Field(default=None)
    ai_analyzed_count: Optional[int] = Field(default=None)
    processing_time_ms: Optional[int] = Field(default=None)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    completed_at: Optional[datetime] = Field(default=None)


class Cluster(SQLModel, table=True):
    """Represents a group of similar reviews (issue cluster/ticket)."""
    
    __tablename__ = "clusters"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    upload_id: int = Field(foreign_key="uploads.id", index=True)
    cluster_uuid: str = Field(unique=True, index=True)
    
    title: str
    severity: str  # critical, high, medium, low
    status: str = Field(default="fresh_roast")  # fresh_roast, in_progress, resolved
    rca_title: Optional[str] = Field(default=None)
    rca_hypothesis: Optional[str] = Field(default=None)
    rca_steps: Optional[str] = Field(default=None)
    rca_fix: Optional[str] = Field(default=None)
    ai_analyzed: Optional[bool] = Field(default=None)
    affected_versions: Optional[str] = Field(default=None)  # JSON string
    affected_devices: Optional[str] = Field(default=None)   # JSON string
    keywords: Optional[str] = Field(default=None)           # JSON string
    review_count: int = Field(default=0)
    assigned_to: Optional[str] = Field(default=None)
    assigned_at: Optional[datetime] = Field(default=None)
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)


class Review(SQLModel, table=True):
    """Individual review records (optional - not used in optimized bulk processor)."""
    
    __tablename__ = "reviews"
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    cluster_id: int = Field(foreign_key="clusters.id", index=True)
    original_text: str
    rating: Optional[int] = Field(default=None)
    version: Optional[str] = Field(default=None)
    device: Optional[str] = Field(default=None)
    review_date: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


# Database setup
def get_engine(database_url: str):
    """
    Create SQLAlchemy engine.
    
    Args:
        database_url: PostgreSQL connection string
    
    Returns:
        Engine instance
    """
    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )
    return engine


def init_db(engine):
    """
    Initialize database tables.
    Tables should already exist from setup scripts.
    This just ensures SQLModel is aware of them.
    
    Args:
        engine: SQLAlchemy engine
    """
    # Tables are created via setup_all_tables.py
    # This just validates the connection
    pass


def get_session(engine):
    """
    Create a new database session.
    
    Args:
        engine: SQLAlchemy engine
    
    Yields:
        Session instance
    """
    with Session(engine) as session:
        yield session
