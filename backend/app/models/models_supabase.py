"""
SQLAlchemy models for Supabase database schema.
Uses existing tables: profiles, uploads, clusters, reviews, roast_results, user_statistics
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer, Numeric, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from app.database.database import Base


# =============================================================================
# PROFILE MODEL (links to auth.users)
# =============================================================================

class Profile(Base):
    """
    User profile linked to Supabase Auth.
    Primary key is UUID from auth.users table.
    """
    __tablename__ = "profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False, unique=True)
    full_name = Column(Text, nullable=True)
    avatar_url = Column(Text, nullable=True)
    provider = Column(Text, nullable=True)  # 'email', 'google', 'github'
    plan = Column(Text, nullable=False, server_default="free")  # free | starter | pro | business | enterprise
    # Proactive alerting — a Slack incoming-webhook or Discord webhook URL.
    # Format (Slack {"text":...} vs Discord {"content":...}) is auto-detected
    # from the URL at send time (notifications.py), so one field covers both.
    alert_webhook_url = Column(Text, nullable=True)
    alerts_enabled = Column(Boolean, nullable=False, server_default="true")
    # Email is a separate channel from the webhook/push alerts_enabled flag
    # above -- a user can want Discord/push on but email off, or vice versa.
    email_alerts_enabled = Column(Boolean, nullable=False, server_default="true")
    weekly_digest_enabled = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    uploads = relationship("Upload", back_populates="user", cascade="all, delete-orphan")
    roast_results = relationship("RoastResult", back_populates="user", cascade="all, delete-orphan")
    statistics = relationship("UserStatistics", back_populates="user", uselist=False, cascade="all, delete-orphan")


# =============================================================================
# UPLOAD MODEL
# =============================================================================

class Upload(Base):
    """CSV upload tracking."""
    __tablename__ = "uploads"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    total_reviews = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default='pending')  # pending, shadow_processing, processing, completed, failed
    error_message = Column(Text, nullable=True)
    processed_reviews = Column(Integer, nullable=True)
    filtered_noise = Column(Integer, nullable=True)
    clusters_created = Column(Integer, nullable=True)
    ai_analyzed_count = Column(Integer, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("Profile", back_populates="uploads")
    clusters = relationship("Cluster", back_populates="upload", cascade="all, delete-orphan")


# =============================================================================
# CLUSTER MODEL
# =============================================================================

class Cluster(Base):
    """Issue clusters with RCA."""
    __tablename__ = "clusters"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    upload_id = Column(Integer, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False)
    cluster_uuid = Column(String, nullable=False, unique=True)
    title = Column(String, nullable=False)
    severity = Column(String, nullable=False)  # Using String instead of ENUM
    status = Column(String, nullable=False, default='fresh_roast')  # Using String instead of ENUM
    rca_title = Column(String, nullable=True)
    rca_hypothesis = Column(Text, nullable=True)
    rca_steps = Column(Text, nullable=True)
    rca_fix = Column(Text, nullable=True)
    ai_analyzed = Column(Boolean, nullable=True)
    affected_versions = Column(JSON, nullable=True)
    affected_devices = Column(JSON, nullable=True)
    keywords = Column(JSON, nullable=True)
    review_count = Column(Integer, nullable=True)
    assigned_to = Column(String, nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    upload = relationship("Upload", back_populates="clusters")
    reviews = relationship("Review", back_populates="cluster", cascade="all, delete-orphan")


# =============================================================================
# REVIEW MODEL
# =============================================================================

class Review(Base):
    """Individual review records."""
    __tablename__ = "reviews"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)
    original_text = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)
    version = Column(String, nullable=True)
    device = Column(String, nullable=True)
    review_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    cluster = relationship("Cluster", back_populates="reviews")


# =============================================================================
# ROAST RESULT MODEL
# =============================================================================

class RoastResult(Base):
    """AI-generated roast analysis results."""
    __tablename__ = "roast_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True)
    review_text = Column(Text, nullable=False)
    original_rating = Column(Numeric, nullable=True)
    reviewer_name = Column(Text, nullable=True)
    review_date = Column(DateTime(timezone=True), nullable=True)
    roast_summary = Column(Text, nullable=True)
    sentiment_score = Column(Numeric, nullable=True)
    toxicity_level = Column(Text, nullable=True)
    key_issues = Column(JSONB, nullable=True)
    ai_response = Column(Text, nullable=True)
    suggested_reply = Column(Text, nullable=True)
    improvement_suggestions = Column(JSONB, nullable=True)
    status = Column(Text, nullable=True, default='pending')
    ticket_number = Column(Text, nullable=True)
    is_resolved = Column(Boolean, nullable=True, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("Profile", back_populates="roast_results")


# =============================================================================
# USER STATISTICS MODEL
# =============================================================================

class UserStatistics(Base):
    """Analytics dashboard data."""
    __tablename__ = "user_statistics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True, unique=True)
    total_reviews_analyzed = Column(Integer, nullable=True, default=0)
    total_issues_found = Column(Integer, nullable=True, default=0)
    total_issues_resolved = Column(Integer, nullable=True, default=0)
    average_sentiment_score = Column(Numeric, nullable=True)
    rating_1_count = Column(Integer, nullable=True, default=0)
    rating_2_count = Column(Integer, nullable=True, default=0)
    rating_3_count = Column(Integer, nullable=True, default=0)
    rating_4_count = Column(Integer, nullable=True, default=0)
    rating_5_count = Column(Integer, nullable=True, default=0)
    average_resolution_time_hours = Column(Numeric, nullable=True)
    satisfaction_improvement_percentage = Column(Numeric, nullable=True)
    last_analysis_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("Profile", back_populates="statistics")
