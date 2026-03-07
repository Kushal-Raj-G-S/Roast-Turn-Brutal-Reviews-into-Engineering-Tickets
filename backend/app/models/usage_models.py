"""
User usage tracking models.
Separate from bulk_models.py since this is plan-related, not processing-related.
"""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Session, select
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID


class UserMonthlyUsage(SQLModel, table=True):
    """
    Track monthly upload usage per user for plan enforcement.
    
    One record per user per month (YYYY-MM format).
    Auto-created when first upload happens in a new month.
    """
    __tablename__ = "user_monthly_usage"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="profiles.id", nullable=False)
    year_month: str = Field(nullable=False)  # "2026-03" format
    uploads_used: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        # Ensure unique constraint on (user_id, year_month)
        table_args = (
            Index("idx_user_monthly_usage_user_month", "user_id", "year_month", unique=True),
        )


def get_current_month() -> str:
    """Return current year-month as YYYY-MM string."""
    return datetime.utcnow().strftime("%Y-%m")


def get_or_create_usage_record(session: Session, user_id: str) -> UserMonthlyUsage:
    """
    Get or create usage record for user in current month.
    
    Args:
        session: Database session
        user_id: User UUID
        
    Returns:
        UserMonthlyUsage record for current month
    """
    current_month = get_current_month()
    
    # Try to get existing record
    existing = session.exec(
        select(UserMonthlyUsage).where(
            UserMonthlyUsage.user_id == user_id,
            UserMonthlyUsage.year_month == current_month
        )
    ).first()
    
    if existing:
        return existing
    
    # Create new record for this month
    new_record = UserMonthlyUsage(
        user_id=user_id,
        year_month=current_month,
        uploads_used=0
    )
    session.add(new_record)
    session.commit()
    session.refresh(new_record)
    
    return new_record


def increment_upload_count(session: Session, user_id: str) -> int:
    """
    Increment upload count for current month.
    
    Args:
        session: Database session  
        user_id: User UUID
        
    Returns:
        New upload count after increment
    """
    usage = get_or_create_usage_record(session, user_id)
    usage.uploads_used += 1
    usage.updated_at = datetime.utcnow()
    session.add(usage)
    session.commit()
    
    return usage.uploads_used


def get_monthly_usage(session: Session, user_id: str) -> int:
    """
    Get current month upload usage for user.
    
    Args:
        session: Database session
        user_id: User UUID
        
    Returns:
        Number of uploads used this month (0 if no record exists)
    """
    current_month = get_current_month()
    
    usage = session.exec(
        select(UserMonthlyUsage).where(
            UserMonthlyUsage.user_id == user_id,
            UserMonthlyUsage.year_month == current_month
        )
    ).first()
    
    return usage.uploads_used if usage else 0