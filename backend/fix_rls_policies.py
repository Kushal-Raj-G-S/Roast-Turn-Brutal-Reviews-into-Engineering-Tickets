"""Fix RLS policies to allow users to read/write their own data."""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DATABASE_URL = "postgresql://postgres.ouxdpbbmvazmtaxeueko:roastgooglereviewproject@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

conn = psycopg2.connect(DATABASE_URL)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cursor = conn.cursor()

print("Fixing RLS policies...")

# Drop and recreate profiles policies with INSERT permission
cursor.execute("""
    DROP POLICY IF EXISTS "Users can view their own profile" ON profiles;
    DROP POLICY IF EXISTS "Users can update their own profile" ON profiles;
    DROP POLICY IF EXISTS "Users can insert their own profile" ON profiles;
    
    CREATE POLICY "Users can view their own profile" 
        ON profiles FOR SELECT 
        USING (auth.uid() = id);
    
    CREATE POLICY "Users can insert their own profile" 
        ON profiles FOR INSERT 
        WITH CHECK (auth.uid() = id);
    
    CREATE POLICY "Users can update their own profile" 
        ON profiles FOR UPDATE 
        USING (auth.uid() = id);
""")
print("✅ Fixed profiles policies")

# Drop and recreate user_statistics policies with INSERT permission
cursor.execute("""
    DROP POLICY IF EXISTS "Users can view their own statistics" ON user_statistics;
    DROP POLICY IF EXISTS "Users can update their own statistics" ON user_statistics;
    DROP POLICY IF EXISTS "Users can insert their own statistics" ON user_statistics;
    
    CREATE POLICY "Users can view their own statistics" 
        ON user_statistics FOR SELECT 
        USING (auth.uid() = user_id);
    
    CREATE POLICY "Users can insert their own statistics" 
        ON user_statistics FOR INSERT 
        WITH CHECK (auth.uid() = user_id);
    
    CREATE POLICY "Users can update their own statistics" 
        ON user_statistics FOR UPDATE 
        USING (auth.uid() = user_id);
""")
print("✅ Fixed user_statistics policies")

# Make sure the trigger function has SECURITY DEFINER
cursor.execute("""
    CREATE OR REPLACE FUNCTION public.handle_new_user()
    RETURNS TRIGGER 
    SECURITY DEFINER
    SET search_path = public
    LANGUAGE plpgsql
    AS $$
    BEGIN
      INSERT INTO public.profiles (id, email, full_name, avatar_url, provider)
      VALUES (
        NEW.id,
        NEW.email,
        NEW.raw_user_meta_data->>'full_name',
        NEW.raw_user_meta_data->>'avatar_url',
        COALESCE(NEW.raw_app_meta_data->>'provider', 'email')
      )
      ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        full_name = EXCLUDED.full_name,
        avatar_url = EXCLUDED.avatar_url;
      
      INSERT INTO public.user_statistics (user_id)
      VALUES (NEW.id)
      ON CONFLICT (user_id) DO NOTHING;
      
      RETURN NEW;
    END;
    $$;
""")
print("✅ Fixed trigger function with SECURITY DEFINER")

# Recreate trigger
cursor.execute("""
    DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
    
    CREATE TRIGGER on_auth_user_created
      AFTER INSERT ON auth.users
      FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
""")
print("✅ Recreated trigger")

cursor.close()
conn.close()

print("\n✅ All RLS policies and triggers fixed!")
print("Now logout and login again to test.")
