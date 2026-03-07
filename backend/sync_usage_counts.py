"""
Sync user_monthly_usage with actual uploads from uploads table.
This fixes the count for existing uploads that weren't tracked.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv('.env')

DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)

print("🔄 Syncing usage counts...\n")

with Session(engine) as session:
    # Get all users with COMPLETED uploads this month (exclude failed/stuck uploads)
    users = session.execute(text("""
        SELECT user_id::text, COUNT(*) as upload_count
        FROM uploads 
        WHERE created_at >= date_trunc('month', CURRENT_DATE)
        AND status = 'completed'
        GROUP BY user_id
    """)).fetchall()
    
    current_month = session.execute(text("SELECT TO_CHAR(CURRENT_DATE, 'YYYY-MM')")).fetchone()[0]
    
    for user_id, actual_count in users:
        # Get current count in usage table
        current = session.execute(text("""
            SELECT uploads_used FROM user_monthly_usage 
            WHERE user_id = :user_id AND year_month = :month
        """), {"user_id": user_id, "month": current_month}).fetchone()
        
        recorded_count = current[0] if current else 0
        
        print(f"User {user_id[:20]}...")
        print(f"  Actual uploads: {actual_count}")
        print(f"  Recorded in usage table: {recorded_count}")
        
        if actual_count != recorded_count:
            print(f"  ⚠️  Syncing {recorded_count} → {actual_count}")
            
            # Upsert with correct count
            session.execute(text("""
                INSERT INTO user_monthly_usage (user_id, year_month, uploads_used, created_at, updated_at)
                VALUES (:user_id, :month, :count, NOW(), NOW())
                ON CONFLICT (user_id, year_month) 
                DO UPDATE SET 
                    uploads_used = :count,
                    updated_at = NOW()
            """), {"user_id": user_id, "month": current_month, "count": actual_count})
            
            session.commit()
            print(f"  ✅ Synced!")
        else:
            print(f"  ✅ Already correct")
    
    print("\n" + "="*60)
    print("✅ All counts synced!")
