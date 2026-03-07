"""
Check database tables and their structure via the backend API.
"""

import requests
import sys
from datetime import datetime

BACKEND_URL = "https://roast-ytzqd.ondigitalocean.app"

def check_health():
    """Check if backend is running."""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=10)
        print(f"✅ Backend is running: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ Backend not reachable: {e}")
        return False

def check_database_connection():
    """Try to query something from the database."""
    try:
        # Try to get plan info (this will fail if backend can't connect to DB)
        response = requests.get(
            f"{BACKEND_URL}/user/plan",
            headers={"Authorization": "Bearer dummy-token-for-test"},
            timeout=10
        )
        print(f"\n📊 Database connection test: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
        if response.status_code == 401:
            print("   ✅ Backend reached database (auth check working)")
            return True
        elif response.status_code == 500:
            print("   ❌ Backend has database issues")
            return False
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def check_sql_direct():
    """Check tables directly via Supabase connection."""
    print("\n🔍 To check tables directly, run this in Supabase SQL Editor:")
    print("""
    -- Check if user_monthly_usage table exists
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'user_monthly_usage'
    );
    
    -- List all tables in public schema
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    ORDER BY table_name;
    
    -- Check the profiles table structure
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' 
    AND table_name = 'profiles'
    ORDER BY ordinal_position;
    """)

if __name__ == "__main__":
    print("🔧 Diagnostic Script for Backend DB Issues\n")
    print(f"📍 Target: {BACKEND_URL}")
    print(f"🕒 Time: {datetime.now()}\n")
    print("=" * 60)
    
    # Check 1: Is backend running?
    if not check_health():
        sys.exit(1)
    
    # Check 2: Can backend connect to database?
    check_database_connection()
    
    # Check 3: SQL queries to run manually
    check_sql_direct()
    
    print("\n" + "=" * 60)
    print("\n💡 Next Steps:")
    print("1. Run the SQL queries above in Supabase SQL Editor")
    print("2. If user_monthly_usage table doesn't exist, run:")
    print("   backend/migrations/create_user_monthly_usage.sql")
    print("3. Check backend logs on DigitalOcean for more details")
