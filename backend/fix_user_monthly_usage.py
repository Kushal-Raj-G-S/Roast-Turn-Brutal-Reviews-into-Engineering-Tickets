"""
Fix user_monthly_usage table:
1. Make user_id NOT NULL
2. Ensure FK constraint is correct
"""

import os
from dotenv import load_dotenv
import psycopg2

load_dotenv('.env')

SUPABASE_DB_URL = os.getenv('DATABASE_URL')

if not SUPABASE_DB_URL:
    print("❌ DATABASE_URL not found in .env")
    exit(1)

try:
    print("🔌 Connecting to Supabase...")
    conn = psycopg2.connect(SUPABASE_DB_URL)
    cursor = conn.cursor()
    
    print("\n1️⃣ Checking current state...")
    cursor.execute("""
        SELECT column_name, is_nullable, data_type
        FROM information_schema.columns
        WHERE table_name = 'user_monthly_usage' 
        AND column_name = 'user_id';
    """)
    result = cursor.fetchone()
    print(f"   user_id: {result[2]} nullable={result[1]}")
    
    if result[1] == 'YES':
        print("\n2️⃣ Fixing user_id constraint (making it NOT NULL)...")
        
        # First, check if there are any NULL values
        cursor.execute("SELECT COUNT(*) FROM user_monthly_usage WHERE user_id IS NULL;")
        null_count = cursor.fetchone()[0]
        
        if null_count > 0:
            print(f"   ⚠️  Found {null_count} rows with NULL user_id - deleting them...")
            cursor.execute("DELETE FROM user_monthly_usage WHERE user_id IS NULL;")
            conn.commit()
        
        # Now alter the column to NOT NULL
        cursor.execute("ALTER TABLE user_monthly_usage ALTER COLUMN user_id SET NOT NULL;")
        conn.commit()
        print("   ✅ user_id is now NOT NULL")
    else:
        print("   ✅ user_id is already NOT NULL")
    
    print("\n3️⃣ Checking FK constraint...")
    cursor.execute("""
        SELECT tc.constraint_name, kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.table_name = 'user_monthly_usage' 
        AND tc.constraint_type = 'FOREIGN KEY';
    """)
    fks = cursor.fetchall()
    
    if fks:
        for fk in fks:
            print(f"   ✅ FK: {fk[1]} -> {fk[2]}.{fk[3]} ({fk[0]})")
    else:
        print("   ❌ No FK found! Creating it...")
        cursor.execute("""
            ALTER TABLE user_monthly_usage
            ADD CONSTRAINT fk_user_monthly_usage_user_id 
            FOREIGN KEY (user_id) 
            REFERENCES public.profiles(id) 
            ON DELETE CASCADE;
        """)
        conn.commit()
        print("   ✅ FK created")
    
    print("\n4️⃣ Verifying final state...")
    cursor.execute("""
        SELECT column_name, is_nullable, data_type
        FROM information_schema.columns
        WHERE table_name = 'user_monthly_usage';
    """)
    columns = cursor.fetchall()
    for col in columns:
        print(f"   {col[0]:15} {col[2]:20} nullable={col[1]}")
    
    cursor.close()
    conn.close()
    
    print("\n✅ All fixes applied successfully!")
    print("\n💡 Now try uploading again - it should work!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
