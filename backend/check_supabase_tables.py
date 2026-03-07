"""
Direct Supabase DB check using psycopg2.
Run this to see what tables exist and identify the FK issue.
"""

import os
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv('.env')

SUPABASE_DB_URL = os.getenv('DATABASE_URL')

if not SUPABASE_DB_URL:
    print("❌ DATABASE_URL not found in backend/.env")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("⚠️  psycopg2 not installed. Install with: pip install psycopg2-binary")
    print("\nAlternatively, run these SQL queries in Supabase SQL Editor:")
    print("\n" + "=" * 60)
    print("""
-- 1. Check if user_monthly_usage table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'user_monthly_usage'
) as table_exists;

-- 2. List all public tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;

-- 3. Check profiles table columns
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'profiles'
ORDER BY ordinal_position;

-- 4. Check if user_monthly_usage columns exist
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'user_monthly_usage'
ORDER BY ordinal_position;

-- 5. Check foreign key constraints
SELECT
    tc.table_name, 
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
AND tc.table_name='user_monthly_usage';
    """)
    sys.exit(0)

# Try to connect and query
try:
    print("🔌 Connecting to Supabase...")
    conn = psycopg2.connect(SUPABASE_DB_URL)
    cursor = conn.cursor()
    
    # Check if user_monthly_usage exists
    print("\n1️⃣ Checking if user_monthly_usage table exists...")
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'user_monthly_usage'
        );
    """)
    exists = cursor.fetchone()[0]
    print(f"   user_monthly_usage table exists: {exists}")
    
    # List all tables
    print("\n2️⃣ All public tables:")
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()
    for table in tables:
        print(f"   - {table[0]}")
    
    # Check profiles table structure
    print("\n3️⃣ Profiles table columns:")
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' 
        AND table_name = 'profiles'
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()
    for col in columns:
        print(f"   {col[0]:15} {col[1]:20} nullable={col[2]} default={col[3]}")
    
    # Check user_monthly_usage if it exists
    if exists:
        print("\n4️⃣ user_monthly_usage table columns:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'user_monthly_usage'
            ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        for col in columns:
            print(f"   {col[0]:15} {col[1]:20} nullable={col[2]}")
        
        print("\n5️⃣ Foreign key constraints on user_monthly_usage:")
        cursor.execute("""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' 
            AND tc.table_name='user_monthly_usage';
        """)
        fks = cursor.fetchall()
        if fks:
            for fk in fks:
                print(f"   {fk[1]} -> {fk[2]}.{fk[3]} (constraint: {fk[0]})")
        else:
            print("   ❌ No foreign keys found!")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    if not exists:
        print("❌ user_monthly_usage table does NOT exist!")
        print("\n💡 Solution: Run this SQL in Supabase SQL Editor:")
        print("   backend/migrations/create_user_monthly_usage.sql")
    else:
        print("✅ Table exists - check foreign key configuration above")
    
except Exception as e:
    print(f"❌ Database error: {e}")
    print("\nRun the SQL queries manually in Supabase SQL Editor (see above)")
    sys.exit(1)
