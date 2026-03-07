"""Check user's plan and usage in database"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv('.env')

DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)

with Session(engine) as session:
    # Get your user profile
    profile = session.execute(text("""
        SELECT id::text, email, plan 
        FROM profiles 
        WHERE email = '1by23ai072@bmsit.in'
        ORDER BY created_at DESC
        LIMIT 1
    """)).fetchone()
    
    if not profile:
        print("❌ Profile not found!")
        exit(1)
    
    user_id, email, plan = profile
    print(f"👤 User Profile:")
    print(f"   ID: {user_id}")
    print(f"   Email: {email}")
    print(f"   Plan: {plan}")
    
    # Get current usage
    current_month = "2026-03"
    usage = session.execute(text("""
        SELECT uploads_used 
        FROM user_monthly_usage 
        WHERE user_id = :user_id AND year_month = :month
    """), {"user_id": user_id, "month": current_month}).fetchone()
    
    uploads_used = usage[0] if usage else 0
    
    print(f"\n📊 Current Usage:")
    print(f"   Month: {current_month}")
    print(f"   Uploads used: {uploads_used}")
    
    # Check plan limits
    plan_limits = {
        "free": 5,
        "starter": 10,
        "pro": 50,
        "business": 100,
        "enterprise": None  # unlimited
    }
    
    if plan in plan_limits:
        limit = plan_limits[plan]
        if limit is None:
            print(f"   Upload limit: Unlimited")
            print(f"   Status: {uploads_used}/∞")
        else:
            print(f"   Upload limit: {limit}")
            print(f"   Status: {uploads_used}/{limit}")
        
        if limit and uploads_used >= limit:
            print(f"\n⚠️  LIMIT REACHED! {uploads_used} >= {limit}")
        else:
            print(f"\n✅ Under limit")
    else:
        print(f"\n❌ Invalid plan: {plan}")
