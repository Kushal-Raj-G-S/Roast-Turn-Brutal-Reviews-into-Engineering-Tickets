"""
Fix the uploads table schema to match SQLAlchemy models.
Handles the case where table was partially migrated.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DATABASE_URL = "postgresql://postgres.ouxdpbbmvazmtaxeueko:roastgooglereviewproject@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

def fix_uploads_table():
    """Fix uploads table schema."""
    
    print("=" * 80)
    print("FIXING UPLOADS TABLE")
    print("=" * 80)
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Check current state
    print("\n🔍 Checking current table structure...")
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'uploads'
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()
    print("Current columns:")
    for col_name, col_type in columns:
        print(f"  - {col_name}: {col_type}")
    
    # Check clusters table
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'clusters' AND column_name IN ('job_id', 'upload_id')
        ORDER BY ordinal_position;
    """)
    cluster_cols = cursor.fetchall()
    print("\nClusters foreign key column:")
    for col_name, col_type in cluster_cols:
        print(f"  - {col_name}: {col_type}")
    
    # Fix strategy: Drop and recreate both tables
    print("\n🔧 Dropping and recreating tables...")
    
    # Drop tables
    cursor.execute("DROP TABLE IF EXISTS clusters CASCADE;")
    cursor.execute("DROP TABLE IF EXISTS uploads CASCADE;")
    print("✅ Dropped old tables")
    
    # Create uploads table (SERIAL id, not UUID)
    cursor.execute("""
        CREATE TABLE uploads (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            filename VARCHAR(255) NOT NULL,
            file_size_bytes INTEGER,
            total_reviews INTEGER,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            error_message TEXT,
            processed_reviews INTEGER,
            filtered_noise INTEGER,
            clusters_created INTEGER,
            ai_analyzed_count INTEGER,
            processing_time_ms INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        );
    """)
    print("✅ Created uploads table with SERIAL id")
    
    # Create clusters table (INTEGER upload_id)
    cursor.execute("""
        CREATE TABLE clusters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
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
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    print("✅ Created clusters table with INTEGER upload_id")
    
    # Create indexes
    cursor.execute("""
        CREATE INDEX idx_uploads_user_id ON uploads(user_id);
        CREATE INDEX idx_uploads_status ON uploads(status);
        CREATE INDEX idx_uploads_created_at ON uploads(created_at DESC);
        CREATE INDEX idx_clusters_upload_id ON clusters(upload_id);
        CREATE INDEX idx_clusters_severity ON clusters(severity);
    """)
    print("✅ Created indexes")
    
    # Verify final structure
    print("\n✅ Final table structure:")
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'uploads'
        ORDER BY ordinal_position;
    """)
    columns = cursor.fetchall()
    for col_name, col_type in columns:
        print(f"  uploads.{col_name}: {col_type}")
    
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'clusters' AND column_name IN ('id', 'upload_id')
        ORDER BY ordinal_position;
    """)
    cluster_cols = cursor.fetchall()
    for col_name, col_type in cluster_cols:
        print(f"  clusters.{col_name}: {col_type}")
    
    print("\n" + "=" * 80)
    print("✅ Tables fixed successfully!")
    print("=" * 80)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    fix_uploads_table()
