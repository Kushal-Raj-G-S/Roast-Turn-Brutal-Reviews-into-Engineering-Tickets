"""
Setup script to create bulk processing tables in Supabase PostgreSQL.
Run this once to initialize the database schema.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Supabase connection string
DATABASE_URL = "postgresql://postgres.ovvinemzixqdvbxrvyzs:roastgooglereviewproject@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

def create_tables():
    """Create all tables for bulk processing."""
    
    print("Connecting to Supabase PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    print("Creating tables...")
    
    # Drop existing tables if they exist
    cursor.execute("""
        DROP TABLE IF EXISTS reviews CASCADE;
        DROP TABLE IF EXISTS clusters CASCADE;
        DROP TABLE IF EXISTS bulk_jobs CASCADE;
    """)
    print("✅ Dropped existing tables (if any)")
    
    # Create bulk_jobs table
    cursor.execute("""
        CREATE TABLE bulk_jobs (
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
    
    # Create clusters table
    cursor.execute("""
        CREATE TABLE clusters (
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
    
    # Create reviews table
    cursor.execute("""
        CREATE TABLE reviews (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES bulk_jobs(id) ON DELETE CASCADE,
            app_id UUID,
            review_id VARCHAR(255) NOT NULL,
            user_name VARCHAR(255),
            content TEXT NOT NULL,
            score INTEGER NOT NULL,
            thumbs_up_count INTEGER,
            app_version VARCHAR(100),
            created_at_store TIMESTAMP WITH TIME ZONE,
            is_noise BOOLEAN DEFAULT FALSE,
            processed_at TIMESTAMP WITH TIME ZONE,
            cluster_id UUID REFERENCES clusters(id) ON DELETE SET NULL,
            version VARCHAR(100),
            device VARCHAR(100)
        );
    """)
    print("✅ Created reviews table")
    
    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX idx_reviews_job_id ON reviews(job_id);
        CREATE INDEX idx_reviews_cluster_id ON reviews(cluster_id);
        CREATE INDEX idx_reviews_is_noise ON reviews(is_noise);
        CREATE INDEX idx_clusters_job_id ON clusters(job_id);
        CREATE INDEX idx_bulk_jobs_status ON bulk_jobs(status);
    """)
    print("✅ Created indexes")
    
    # Add foreign key for sample_review_id (after reviews table exists)
    cursor.execute("""
        ALTER TABLE clusters 
        ADD CONSTRAINT fk_clusters_sample_review 
        FOREIGN KEY (sample_review_id) 
        REFERENCES reviews(id) 
        ON DELETE SET NULL;
    """)
    print("✅ Added foreign key constraints")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Database setup complete!")
    print("=" * 60)
    print("\nTables created:")
    print("  - bulk_jobs (job tracking)")
    print("  - clusters (issue clusters/tickets)")
    print("  - reviews (individual reviews)")
    print("\nYou can now run the bulk processing pipeline.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        create_tables()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure psycopg2-binary is installed:")
        print("  pip install psycopg2-binary")
