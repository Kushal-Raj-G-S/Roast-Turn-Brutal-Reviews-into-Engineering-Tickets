"""
Complete database setup for ROAST application.
Creates ALL tables needed by both frontend and backend.

Frontend tables: profiles, roast_results, user_statistics
Backend tables: bulk_jobs, clusters
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Supabase connection string (NEW PROJECT)
DATABASE_URL = "postgresql://postgres.ouxdpbbmvazmtaxeueko:roastgooglereviewproject@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

def create_all_tables():
    """Create all tables for the ROAST application."""
    
    print("=" * 80)
    print("ROAST APPLICATION - COMPLETE DATABASE SETUP")
    print("=" * 80)
    print("\nConnecting to Supabase PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    print("\n📦 Creating extensions...")
    cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    print("✅ UUID extension enabled")
    
    print("\n🔧 Creating FRONTEND tables...")
    
    # PROFILES TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id UUID PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT,
            avatar_url TEXT,
            provider TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    print("✅ Created profiles table")
    
    # ROAST RESULTS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roast_results (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
            review_text TEXT NOT NULL,
            original_rating NUMERIC(2,1) CHECK (original_rating >= 1.0 AND original_rating <= 5.0),
            reviewer_name TEXT,
            review_date TIMESTAMPTZ,
            roast_summary TEXT,
            sentiment_score NUMERIC(3,2) CHECK (sentiment_score >= -1.0 AND sentiment_score <= 1.0),
            toxicity_level TEXT CHECK (toxicity_level IN ('low', 'medium', 'high', 'extreme')),
            key_issues JSONB,
            ai_response TEXT,
            suggested_reply TEXT,
            improvement_suggestions JSONB,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
            ticket_number TEXT UNIQUE,
            is_resolved BOOLEAN DEFAULT FALSE,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    print("✅ Created roast_results table")
    
    # USER STATISTICS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_statistics (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
            total_reviews_analyzed INTEGER DEFAULT 0,
            total_issues_found INTEGER DEFAULT 0,
            total_issues_resolved INTEGER DEFAULT 0,
            average_sentiment_score NUMERIC(3,2),
            rating_1_count INTEGER DEFAULT 0,
            rating_2_count INTEGER DEFAULT 0,
            rating_3_count INTEGER DEFAULT 0,
            rating_4_count INTEGER DEFAULT 0,
            rating_5_count INTEGER DEFAULT 0,
            average_resolution_time_hours NUMERIC(10,2),
            satisfaction_improvement_percentage NUMERIC(5,2),
            last_analysis_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    print("✅ Created user_statistics table")
    
    print("\n🔧 Creating BACKEND tables...")
    
    # BULK JOBS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bulk_jobs (
            id UUID PRIMARY KEY,
            status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            filename VARCHAR(255),
            total_rows INTEGER,
            processed_rows INTEGER,
            kept_rows INTEGER,
            cluster_count INTEGER,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    print("✅ Created bulk_jobs table")
    
    # CLUSTERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clusters (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES bulk_jobs(id) ON DELETE CASCADE,
            app_id UUID,
            title VARCHAR(500) NOT NULL,
            severity VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'freshroast',
            review_count INTEGER DEFAULT 0,
            sample_review_id UUID,
            sample_content TEXT,
            rca_title TEXT,
            rca_hypothesis TEXT,
            rca_steps TEXT,
            rca_fix TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    print("✅ Created clusters table")
    
    print("\n📊 Creating indexes...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_roast_results_user_id ON roast_results(user_id);
        CREATE INDEX IF NOT EXISTS idx_roast_results_created_at ON roast_results(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_roast_results_status ON roast_results(status);
        CREATE INDEX IF NOT EXISTS idx_roast_results_ticket_number ON roast_results(ticket_number);
        CREATE INDEX IF NOT EXISTS idx_clusters_job_id ON clusters(job_id);
        CREATE INDEX IF NOT EXISTS idx_clusters_severity ON clusters(severity);
        CREATE INDEX IF NOT EXISTS idx_bulk_jobs_status ON bulk_jobs(status);
    """)
    print("✅ Created all indexes")
    
    print("\n🔐 Enabling Row Level Security...")
    cursor.execute("""
        ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
        ALTER TABLE roast_results ENABLE ROW LEVEL SECURITY;
        ALTER TABLE user_statistics ENABLE ROW LEVEL SECURITY;
    """)
    print("✅ RLS enabled on frontend tables")
    
    print("\n🛡️  Creating RLS policies...")
    
    # Profiles policies
    cursor.execute("""
        DROP POLICY IF EXISTS "Users can view their own profile" ON profiles;
        CREATE POLICY "Users can view their own profile" 
            ON profiles FOR SELECT 
            USING (auth.uid() = id);
        
        DROP POLICY IF EXISTS "Users can update their own profile" ON profiles;
        CREATE POLICY "Users can update their own profile" 
            ON profiles FOR UPDATE 
            USING (auth.uid() = id);
    """)
    
    # Roast results policies
    cursor.execute("""
        DROP POLICY IF EXISTS "Users can view their own roast results" ON roast_results;
        CREATE POLICY "Users can view their own roast results" 
            ON roast_results FOR SELECT 
            USING (auth.uid() = user_id);
        
        DROP POLICY IF EXISTS "Users can insert their own roast results" ON roast_results;
        CREATE POLICY "Users can insert their own roast results" 
            ON roast_results FOR INSERT 
            WITH CHECK (auth.uid() = user_id);
        
        DROP POLICY IF EXISTS "Users can update their own roast results" ON roast_results;
        CREATE POLICY "Users can update their own roast results" 
            ON roast_results FOR UPDATE 
            USING (auth.uid() = user_id);
        
        DROP POLICY IF EXISTS "Users can delete their own roast results" ON roast_results;
        CREATE POLICY "Users can delete their own roast results" 
            ON roast_results FOR DELETE 
            USING (auth.uid() = user_id);
    """)
    
    # User statistics policies
    cursor.execute("""
        DROP POLICY IF EXISTS "Users can view their own statistics" ON user_statistics;
        CREATE POLICY "Users can view their own statistics" 
            ON user_statistics FOR SELECT 
            USING (auth.uid() = user_id);
        
        DROP POLICY IF EXISTS "Users can update their own statistics" ON user_statistics;
        CREATE POLICY "Users can update their own statistics" 
            ON user_statistics FOR UPDATE 
            USING (auth.uid() = user_id);
    """)
    print("✅ Created all RLS policies")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ COMPLETE DATABASE SETUP SUCCESSFUL!")
    print("=" * 80)
    print("\n📋 Tables created:")
    print("\n  FRONTEND:")
    print("    - profiles (user data)")
    print("    - roast_results (roast analysis)")
    print("    - user_statistics (aggregated stats)")
    print("\n  BACKEND:")
    print("    - bulk_jobs (job tracking)")
    print("    - clusters (top priority issue clusters)")
    print("\n❌ NO reviews table (saves 99% storage!)")
    print("\n🔐 Row Level Security enabled")
    print("🛡️  RLS policies configured")
    print("📊 Indexes created for performance")
    print("\n🚀 You're all set! Run your application now.")
    print("=" * 80)


if __name__ == "__main__":
    try:
        create_all_tables()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check your Supabase connection string")
        print("2. Make sure psycopg2-binary is installed: pip install psycopg2-binary")
        print("3. Verify your Supabase project is active")
