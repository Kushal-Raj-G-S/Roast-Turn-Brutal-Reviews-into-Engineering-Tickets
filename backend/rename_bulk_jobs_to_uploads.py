"""
Rename bulk_jobs table to uploads to match SQLAlchemy models.
Also update the columns to match the Upload model schema.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Supabase connection string (NEW PROJECT)
DATABASE_URL = "postgresql://postgres.ouxdpbbmvazmtaxeueko:roastgooglereviewproject@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

def rename_table():
    """Rename bulk_jobs to uploads and update schema."""
    
    print("=" * 80)
    print("RENAMING bulk_jobs TO uploads")
    print("=" * 80)
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Check if bulk_jobs exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'bulk_jobs'
        );
    """)
    bulk_jobs_exists = cursor.fetchone()[0]
    
    # Check if uploads exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'uploads'
        );
    """)
    uploads_exists = cursor.fetchone()[0]
    
    if uploads_exists:
        print("✅ uploads table already exists, no migration needed")
        cursor.close()
        conn.close()
        return
    
    if not bulk_jobs_exists:
        print("⚠️  bulk_jobs table doesn't exist, creating uploads from scratch...")
        # Create uploads table
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
        print("✅ Created uploads table")
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id);
            CREATE INDEX IF NOT EXISTS idx_uploads_status ON uploads(status);
            CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at DESC);
        """)
        print("✅ Created indexes")
        
        # Update clusters foreign key
        cursor.execute("""
            ALTER TABLE clusters 
            DROP CONSTRAINT IF EXISTS clusters_job_id_fkey;
            
            ALTER TABLE clusters 
            RENAME COLUMN job_id TO upload_id;
            
            ALTER TABLE clusters 
            ADD CONSTRAINT clusters_upload_id_fkey 
            FOREIGN KEY (upload_id) REFERENCES uploads(id) ON DELETE CASCADE;
        """)
        print("✅ Updated clusters.upload_id foreign key")
        
    else:
        print("📦 Renaming bulk_jobs to uploads...")
        
        # Rename table
        cursor.execute("ALTER TABLE bulk_jobs RENAME TO uploads;")
        print("✅ Renamed table")
        
        # Rename indexes
        cursor.execute("ALTER INDEX IF EXISTS idx_bulk_jobs_status RENAME TO idx_uploads_status;")
        print("✅ Renamed indexes")
        
        # Update columns to match Upload model
        print("🔧 Updating columns...")
        
        # Step 1: Drop foreign key constraint first
        cursor.execute("""
            ALTER TABLE clusters DROP CONSTRAINT IF EXISTS clusters_job_id_fkey;
        """)
        print("✅ Dropped old foreign key constraint")
        
        # Step 2: Convert both columns from UUID to INTEGER
        cursor.execute("""
            -- Change uploads.id from UUID to SERIAL
            ALTER TABLE uploads ALTER COLUMN id DROP DEFAULT;
            ALTER TABLE uploads ALTER COLUMN id TYPE INTEGER USING (substring(id::text from 1 for 8))::bit(32)::int;
            CREATE SEQUENCE IF NOT EXISTS uploads_id_seq OWNED BY uploads.id;
            ALTER TABLE uploads ALTER COLUMN id SET DEFAULT nextval('uploads_id_seq');
            SELECT setval('uploads_id_seq', COALESCE((SELECT MAX(id) FROM uploads), 0) + 1, false);
            
            -- Change clusters.job_id from UUID to INTEGER (matching conversion)
            ALTER TABLE clusters 
            ALTER COLUMN job_id TYPE INTEGER USING (substring(job_id::text from 1 for 8))::bit(32)::int;
        """)
        print("✅ Converted ID columns from UUID to INTEGER")
        
        # Step 3: Add missing columns
        cursor.execute("""
            ALTER TABLE uploads ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES profiles(id) ON DELETE CASCADE;
            ALTER TABLE uploads ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER;
            ALTER TABLE uploads ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
            ALTER TABLE uploads ADD COLUMN IF NOT EXISTS ai_analyzed_count INTEGER;
            ALTER TABLE uploads ADD COLUMN IF NOT EXISTS processing_time_ms INTEGER;
        """)
        print("✅ Added missing columns")
        
        # Step 4: Rename columns
        cursor.execute("""
            ALTER TABLE uploads RENAME COLUMN total_rows TO total_reviews;
            ALTER TABLE uploads RENAME COLUMN processed_rows TO processed_reviews;
            ALTER TABLE uploads RENAME COLUMN kept_rows TO filtered_noise;
            ALTER TABLE uploads RENAME COLUMN cluster_count TO clusters_created;
        """)
        print("✅ Renamed columns")
        
        # Step 5: Update status column
        cursor.execute("""
            ALTER TABLE uploads ALTER COLUMN status TYPE VARCHAR(50);
            ALTER TABLE uploads ALTER COLUMN status SET DEFAULT 'pending';
        """)
        print("✅ Updated status column")
        
        # Step 6: Rename job_id to upload_id and recreate foreign key
        cursor.execute("""
            ALTER TABLE clusters RENAME COLUMN job_id TO upload_id;
            
            ALTER TABLE clusters 
            ADD CONSTRAINT clusters_upload_id_fkey 
            FOREIGN KEY (upload_id) REFERENCES uploads(id) ON DELETE CASCADE;
        """)
        print("✅ Updated clusters.upload_id foreign key")
        
        # Create additional indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id);
            CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads(created_at DESC);
        """)
        print("✅ Created additional indexes")
    
    print("\n" + "=" * 80)
    print("✅ Migration completed successfully!")
    print("=" * 80)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    rename_table()
