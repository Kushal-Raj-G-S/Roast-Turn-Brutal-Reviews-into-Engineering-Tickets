"""
Setup script to create bulk processing tables in Supabase PostgreSQL.
Run this once to initialize the database schema.
NO REVIEWS TABLE - we only store clusters!
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Supabase connection string (NEW PROJECT)
DATABASE_URL = "postgresql://postgres.ouxdpbbmvazmtaxeueko:roastgooglereviewproject@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

def create_tables():
    """Create all tables for bulk processing."""
    
    print("Connecting to Supabase PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    print("Creating tables...")
    
    # Drop existing tables if they exist
    cursor.execute("""
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
    
    # Create clusters table (NO reviews table!)
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
    
    print("✅ SKIPPED reviews table (not needed - saves 99% storage!)")
    
    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX idx_clusters_job_id ON clusters(job_id);
        CREATE INDEX idx_clusters_severity ON clusters(severity);
        CREATE INDEX idx_bulk_jobs_status ON bulk_jobs(status);
    """)
    print("✅ Created indexes")
    
    # No foreign key for sample_review_id since we don't have reviews table
    # sample_review_id is just a UUID reference stored in cluster.sample_content
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Database setup complete!")
    print("=" * 60)
    print("\nTables created:")
    print("  - bulk_jobs (job tracking)")
    print("  - clusters (issue clusters/tickets with sample content)")
    print("\n❌ NO reviews table (saves 99% storage!)")
    print("\nYou can now run the bulk processing pipeline.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        create_tables()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure psycopg2-binary is installed:")
        print("  pip install psycopg2-binary")
