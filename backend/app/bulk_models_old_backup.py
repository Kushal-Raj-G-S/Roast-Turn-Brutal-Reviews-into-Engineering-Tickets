"""
Database models for bulk review processing.
Uses SQLModel for type-safe ORM with Pydantic integration.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, create_engine, Session, select
from sqlalchemy import Column, DateTime, func


class BulkJob(SQLModel, table=True):
    """Represents a bulk CSV upload job."""
    
    __tablename__ = "bulk_jobs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: str = Field(default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    filename: Optional[str] = Field(default=None)
    total_rows: Optional[int] = Field(default=None)
    processed_rows: Optional[int] = Field(default=None)
    kept_rows: Optional[int] = Field(default=None)  # After noise filtering
    cluster_count: Optional[int] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )


class Review(SQLModel, table=True):
    """Represents a single review from the CSV."""
    
    __tablename__ = "reviews"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="bulk_jobs.id", index=True)
    app_id: Optional[UUID] = Field(default=None)  # Can be set later
    
    # Raw CSV data
    review_id: str = Field(index=True)  # Original reviewId from CSV
    user_name: Optional[str] = Field(default=None)
    content: str
    score: int  # Rating 1-5
    thumbs_up_count: Optional[int] = Field(default=None)
    app_version: Optional[str] = Field(default=None)
    created_at_store: Optional[datetime] = Field(default=None)
    
    # Processing metadata
    is_noise: bool = Field(default=False)
    processed_at: Optional[datetime] = Field(default=None)
    cluster_id: Optional[UUID] = Field(default=None, foreign_key="clusters.id", index=True)
    
    # Extracted metadata (from processor)
    version: Optional[str] = Field(default=None)  # Extracted version (v2.4)
    device: Optional[str] = Field(default=None)   # Extracted device (Pixel, iPhone)


class Cluster(SQLModel, table=True):
    """Represents a group of similar reviews (issue cluster/ticket)."""
    
    __tablename__ = "clusters"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="bulk_jobs.id", index=True)
    app_id: Optional[UUID] = Field(default=None)
    
    title: str
    severity: str  # critical, high, medium, low
    status: str = Field(default="freshroast")  # freshroast, fixing, done
    review_count: int = Field(default=0)
    
    # Representative review
    sample_review_id: Optional[UUID] = Field(default=None, foreign_key="reviews.id")
    sample_content: Optional[str] = Field(default=None)  # Store for quick display
    
    # RCA fields (optional, can be populated later by LLM)
    rca_title: Optional[str] = Field(default=None)
    rca_hypothesis: Optional[str] = Field(default=None)
    rca_steps: Optional[str] = Field(default=None)
    rca_fix: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )


# Database setup
def get_engine(database_url: str):
    """Create SQLAlchemy engine."""
    from app.config import config
    
    # For SQLite, add check_same_thread=False
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    
    # PostgreSQL optimizations
    pool_config = {}
    if database_url.startswith("postgresql"):
        pool_config = {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_pre_ping": True,
        }
    
    return create_engine(
        database_url,
        echo=False,  # Set to True for SQL debugging
        connect_args=connect_args,
        **pool_config
    )


def init_db(engine):
    """Create all tables."""
    SQLModel.metadata.create_all(engine)


def get_session(engine):
    """Get a database session."""
    return Session(engine)
