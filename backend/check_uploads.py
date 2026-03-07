"""
Check what uploads exist and filter out shadow test uploads.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv('.env')

DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)

with Session(engine) as session:
    # Get all uploads for this month
    uploads = session.execute(text("""
        SELECT 
            id, 
            user_id::text, 
            filename, 
            status,
            created_at
        FROM uploads 
        WHERE created_at >= date_trunc('month', CURRENT_DATE)
        ORDER BY created_at DESC
    """)).fetchall()
    
    print("📋 All uploads this month:\n")
    
    # Group by user
    user_uploads = {}
    shadow_user_id = session.execute(text("""
        SELECT user_id::text FROM uploads 
        WHERE filename LIKE '43.csv' AND id > 43
        LIMIT 1
    """)).fetchone()
    
    shadow_user = shadow_user_id[0] if shadow_user_id else None
    
    for upload in uploads:
        id, user_id, filename, status, created_at = upload
        is_shadow = "(SHADOW)" if user_id == shadow_user else ""
        print(f"ID {id}: User {user_id[:20]}... | {filename:30} | {status:20} | {created_at} {is_shadow}")
        
        if user_id == shadow_user:
            continue  # Skip shadow uploads
        
        if user_id not in user_uploads:
            user_uploads[user_id] = 0
        user_uploads[user_id] += 1
    
    print("\n" + "="*80)
    print("\n📊 Real user upload counts (excluding shadow tests):\n")
    
    for user_id, count in user_uploads.items():
        print(f"User {user_id[:20]}...: {count} uploads")
