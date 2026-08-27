"""
Database models for bulk review processing (optimized system).
Uses the 'uploads' and 'clusters' tables created in Supabase.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlmodel import Field, SQLModel, create_engine, Session, select
from sqlalchemy import Column, DateTime, func, Integer, JSON


class Upload(SQLModel, table=True):
    """Represents a CSV upload job."""
    
    __tablename__ = "uploads"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    user_id: UUID
    filename: str
    file_size_bytes: Optional[int] = Field(default=None)
    total_reviews: Optional[int] = Field(default=None)
    status: str = Field(default="pending")  # pending, shadow_processing, processing, completed, failed
    error_message: Optional[str] = Field(default=None)
    processed_reviews: Optional[int] = Field(default=None)
    filtered_noise: Optional[int] = Field(default=None)
    clusters_created: Optional[int] = Field(default=None)
    ai_analyzed_count: Optional[int] = Field(default=None)
    processing_time_ms: Optional[int] = Field(default=None)
    processing_time_seconds: Optional[float] = Field(default=None)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    completed_at: Optional[datetime] = Field(default=None)


class Cluster(SQLModel, table=True):
    """Represents a group of similar reviews (issue cluster/ticket)."""
    
    __tablename__ = "clusters"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    upload_id: int = Field(index=True)
    cluster_uuid: str = Field(unique=True, index=True)
    
    title: str
    severity: str  # critical, high, medium, low
    status: str = Field(default="fresh_roast")  # fresh_roast, in_progress, resolved
    rca_title: Optional[str] = Field(default=None)
    rca_hypothesis: Optional[str] = Field(default=None)
    rca_steps: Optional[str] = Field(default=None)
    rca_fix: Optional[str] = Field(default=None)
    ai_analyzed: Optional[bool] = Field(default=None)
    affected_versions: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    affected_devices: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    keywords: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    sample_reviews: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    review_count: int = Field(default=0)

    # Structured output from the LangGraph RCA agent — set by
    # explanation_pregenerate.py alongside rca_hypothesis/rca_steps/rca_fix.
    # Kept separate (rather than parsed out of the markdown text) so the
    # frontend can render real badges/meters instead of regexing prose.
    # Shape: {likelihood, scope, suggested_severity, severity_reason,
    #         confidence, similar_issues: [{title, severity, status}],
    #         eval_scores: {faithfulness, answer_relevancy}, trace_id,
    #         agent_steps: [str]}
    ai_metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    assigned_to: Optional[str] = Field(default=None)
    assigned_at: Optional[datetime] = Field(default=None)

    # Fix Verification Loop — set by shadow_deployment.py after processing.
    # A resolved cluster resurfacing in a later upload means the fix didn't
    # actually hold; regression_confidence/match_method record how sure the
    # detector is and whether it caught it via keyword overlap, semantic
    # similarity, or both (see shadow_deployment.py::_detect_regressions).
    regression_detected: Optional[bool] = Field(default=False)
    regression_of_title: Optional[str] = Field(default=None)
    regression_confidence: Optional[float] = Field(default=None)
    regression_match_method: Optional[str] = Field(default=None)  # keyword | semantic | keyword+semantic
    regression_resolved_at: Optional[datetime] = Field(default=None)  # when the ORIGINAL cluster was marked resolved
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)


class SeverityExplanation(SQLModel, table=True):
    """
    Stores AI-generated category explanations per upload × severity.
    Written by the background pre-generator right after processing finishes.
    Persisted so explanations survive server restarts.
    """

    __tablename__ = "severity_explanations"
    __table_args__ = {'extend_existing': True}

    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    upload_id: int = Field(index=True)
    severity: str           # critical | high | medium | low
    status: str = Field(default="pending")   # pending | generating | done | failed
    explanation: Optional[str] = Field(default=None)
    generated_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class PushSubscription(SQLModel, table=True):
    """
    A browser's Web Push subscription (endpoint + encryption keys), one row
    per browser/device a user has enabled push notifications on -- not one
    per user, since the same account can have push enabled on more than one
    browser. Written by POST /push/subscribe when the frontend registers a
    service worker and calls PushManager.subscribe(); read by
    notifications.send_push() to actually deliver a message.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = {'extend_existing': True}

    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    user_id: UUID = Field(index=True)
    endpoint: str = Field(unique=True)
    p256dh: str
    auth: str
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class Review(SQLModel, table=True):
    """Individual review records (optional - not used in optimized bulk processor)."""
    
    __tablename__ = "reviews"
    __table_args__ = {'extend_existing': True}
    
    id: Optional[int] = Field(default=None, primary_key=True, sa_column_kwargs={"autoincrement": True})
    cluster_id: int = Field(index=True)
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
    # Use Transaction mode port if on Supabase pooler
    database_url = database_url.replace(":5432/", ":6543/")
    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,      # Base pool for steady-state load
        max_overflow=20,   # Additional connections for burst traffic
        pool_recycle=300,
        pool_timeout=10,   # Reduced from 30 to fail faster and avoid hanging connections
    )
    return engine


def init_db(engine):
    """
    Initialize database tables.
    Creates any tables that don't exist yet (e.g. severity_explanations).
    Existing Supabase tables are unaffected (extend_existing=True).

    Args:
        engine: SQLAlchemy engine
    """
    SQLModel.metadata.create_all(engine)
    
    # Note: user_monthly_usage table is created via SQL migration
    # (backend/migrations/create_user_monthly_usage.sql)
    # Don't auto-create it here - FK references profiles table which is in a different Base


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
