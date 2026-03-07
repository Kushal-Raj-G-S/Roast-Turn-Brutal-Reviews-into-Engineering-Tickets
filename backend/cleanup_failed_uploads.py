"""
Delete the 5 failed/stuck uploads from earlier.
This will clean up the database and ensure accurate counting.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv('.env')

DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)

user_email = "1by23ai072@bmsit.in"

with Session(engine) as session:
    # Get user ID
    user_id = session.execute(text("""
        SELECT id::text FROM profiles WHERE email = :email
    """), {"email": user_email}).fetchone()[0]
    
    print(f"User: {user_email}")
    print(f"User ID: {user_id}\n")
    
    # Find failed/stuck uploads
    failed = session.execute(text("""
        SELECT id, filename, status, created_at 
        FROM uploads 
        WHERE user_id = :user_id 
        AND status IN ('shadow_processing', 'pending', 'failed')
        ORDER BY created_at
    """), {"user_id": user_id}).fetchall()
    
    if not failed:
        print("✅ No failed uploads to clean up!")
    else:
        print(f"Found {len(failed)} failed/stuck uploads:\n")
        for upload in failed:
            print(f"  ID {upload[0]}: {upload[1]} | {upload[2]} | {upload[3]}")
        
        confirm = input(f"\n⚠️  Delete these {len(failed)} uploads? (yes/no): ")
        
        if confirm.lower() == 'yes':
            for upload in failed:
                session.execute(text("DELETE FROM uploads WHERE id = :id"), {"id": upload[0]})
            session.commit()
            print(f"\n✅ Deleted {len(failed)} failed uploads!")
        else:
            print("\n❌ Cancelled")
