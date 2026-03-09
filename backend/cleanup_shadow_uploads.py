"""
Automatic Shadow Upload Cleanup
=================================
Deletes shadow test uploads older than 30 days to prevent database bloat.
Only affects shadow test user's data - never touches real user uploads.

Run this as a scheduled job (daily/weekly):
  Windows: Task Scheduler
  Linux: cron job
  Cloud: DigitalOcean App Platform scheduled job
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Get database URL from environment or settings
try:
    from app.core.config import settings
    DATABASE_URL = settings.DATABASE_URL
except (ImportError, AttributeError):
    # Fallback to environment variable (for GitHub Actions)
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment or settings")

# Auto-switch to transaction mode (port 6543) for Supabase pooler
if ":5432/" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace(":5432/", ":6543/")
    print(f"ℹ️  Switched to transaction mode (port 6543)")
print()

# Shadow test user UUID (dedicated account for shadow testing)
SHADOW_USER_ID = "6a0a2e2b-ed83-434e-b71d-3d89125127dd"

# Retention period in days
RETENTION_DAYS = 30


def cleanup_old_shadow_uploads():
    """Delete shadow uploads older than RETENTION_DAYS."""
    
    # Use Supabase connection (transaction mode)
    engine = create_engine(DATABASE_URL)
    
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    
    print(f"🧹 Shadow Upload Cleanup")
    print(f"=" * 50)
    print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"Target user: {SHADOW_USER_ID}")
    print()
    
    with Session(engine) as session:
        try:
            # Count how many shadow uploads will be deleted
            count_query = text("""
                SELECT COUNT(*) as total
                FROM uploads
                WHERE user_id = :user_id
                AND created_at < :cutoff_date
            """)
            
            result = session.execute(
                count_query,
                {"user_id": SHADOW_USER_ID, "cutoff_date": cutoff_date}
            ).fetchone()
            
            total_to_delete = result[0] if result else 0
            
            if total_to_delete == 0:
                print("✅ No old shadow uploads found. Database is clean!")
                return
            
            print(f"Found {total_to_delete} shadow upload(s) older than {RETENTION_DAYS} days")
            
            # Delete old shadow uploads (cascading deletes handle clusters & reviews)
            delete_query = text("""
                DELETE FROM uploads
                WHERE user_id = :user_id
                AND created_at < :cutoff_date
            """)
            
            session.execute(
                delete_query,
                {"user_id": SHADOW_USER_ID, "cutoff_date": cutoff_date}
            )
            session.commit()
            
            print(f"✅ Successfully deleted {total_to_delete} shadow upload(s)")
            print(f"   (Cascading deletes removed associated clusters & reviews)")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error during cleanup: {e}")
            raise
        finally:
            print()
            print("Cleanup complete.")


if __name__ == "__main__":
    try:
        cleanup_old_shadow_uploads()
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)
