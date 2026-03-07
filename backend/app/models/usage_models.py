"""
User usage tracking - uses raw SQL to avoid FK resolution issues.
Table exists in Supabase via migration (create_user_monthly_usage.sql).
"""

from datetime import datetime
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_current_month() -> str:
    """Return current year-month as YYYY-MM string."""
    return datetime.utcnow().strftime("%Y-%m")


def get_or_create_usage_record(session: Session, user_id: str) -> dict:
    """
    Get or create usage record for user in current month using raw SQL.
    
    Args:
        session: Database session
        user_id: User UUID string
        
    Returns:
        Dict with id, user_id, year_month, uploads_used
    """
    current_month = get_current_month()
    
    logger.info(f"📊 Getting/creating usage record for user {user_id[:8]}... month {current_month}")
    
    # Use INSERT ... ON CONFLICT (upsert) to atomically get or create
    query = text("""
        INSERT INTO user_monthly_usage (user_id, year_month, uploads_used, created_at, updated_at)
        VALUES (:user_id, :year_month, 0, NOW(), NOW())
        ON CONFLICT (user_id, year_month) 
        DO UPDATE SET updated_at = NOW()
        RETURNING id, user_id::text, year_month, uploads_used
    """)
    
    result = session.execute(
        query,
        {"user_id": user_id, "year_month": current_month}
    ).fetchone()
    
    session.commit()
    
    logger.info(f"📊 Usage record: uploads_used={result[3]}")
    
    return {
        "id": result[0],
        "user_id": result[1],
        "year_month": result[2],
        "uploads_used": result[3]
    }


def increment_upload_count(session: Session, user_id: str) -> int:
    """
    Increment upload count for current month using raw SQL.
    
    Args:
        session: Database session  
        user_id: User UUID string
        
    Returns:
        New upload count after increment
    """
    current_month = get_current_month()
    
    logger.info(f"⬆️  Incrementing upload count for user {user_id[:8]}... month {current_month}")
    
    try:
        # Upsert with increment
        query = text("""
            INSERT INTO user_monthly_usage (user_id, year_month, uploads_used, created_at, updated_at)
            VALUES (:user_id, :year_month, 1, NOW(), NOW())
            ON CONFLICT (user_id, year_month) 
            DO UPDATE SET 
                uploads_used = user_monthly_usage.uploads_used + 1,
                updated_at = NOW()
            RETURNING uploads_used
        """)
        
        result = session.execute(
            query,
            {"user_id": user_id, "year_month": current_month}
        ).fetchone()
        
        session.commit()
        
        new_count = result[0]
        logger.info(f"✅ Upload count incremented to {new_count} for user {user_id[:8]}...")
        
        return new_count
    except Exception as e:
        logger.error(f"❌ Failed to increment upload count for user {user_id[:8]}...: {e}")
        session.rollback()
        raise


def get_monthly_usage(session: Session, user_id: str) -> int:
    """
    Get current month upload usage for user using raw SQL.
    
    Args:
        session: Database session
        user_id: User UUID string
        
    Returns:
        Number of uploads used this month (0 if no record exists)
    """
    current_month = get_current_month()
    
    logger.debug(f"📊 Getting monthly usage for user {user_id[:8]}... month {current_month}")
    
    query = text("""
        SELECT uploads_used 
        FROM user_monthly_usage 
        WHERE user_id = :user_id 
        AND year_month = :year_month
    """)
    
    result = session.execute(
        query,
        {"user_id": user_id, "year_month": current_month}
    ).fetchone()
    
    count = result[0] if result else 0
    logger.debug(f"📊 Monthly usage for user {user_id[:8]}...: {count}")
    
    return count