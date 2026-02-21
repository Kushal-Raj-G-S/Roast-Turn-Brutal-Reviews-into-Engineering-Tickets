"""
Fix clusters table to use INTEGER id instead of UUID.
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DATABASE_URL = "postgresql://postgres.ouxdpbbmvazmtaxeueko:roastgooglereviewproject@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

def fix_clusters_id():
    """Fix clusters.id to be INTEGER instead of UUID."""
    
    print("=" * 80)
    print("FIXING CLUSTERS TABLE - INTEGER ID")
    print("=" * 80)
    
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    print("\n🔧 Recreating clusters table with INTEGER id...")
    
    # Drop and recreate
    cursor.execute("DROP TABLE IF EXISTS clusters CASCADE;")
    
    cursor.execute("""
        CREATE TABLE clusters (
            id SERIAL PRIMARY KEY,
            upload_id INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
            cluster_uuid VARCHAR(255) UNIQUE NOT NULL,
            title VARCHAR(500) NOT NULL,
            severity VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'fresh_roast',
            rca_title TEXT,
            rca_hypothesis TEXT,
            rca_steps TEXT,
            rca_fix TEXT,
            ai_analyzed BOOLEAN,
            affected_versions JSONB,
            affected_devices JSONB,
            keywords JSONB,
            review_count INTEGER,
            assigned_to VARCHAR(255),
            assigned_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ
        );
    """)
    print("✅ Created clusters table with SERIAL id")
    
    # Create indexes
    cursor.execute("""
        CREATE INDEX idx_clusters_upload_id ON clusters(upload_id);
        CREATE INDEX idx_clusters_severity ON clusters(severity);
        CREATE INDEX idx_clusters_status ON clusters(status);
        CREATE INDEX idx_clusters_cluster_uuid ON clusters(cluster_uuid);
    """)
    print("✅ Created indexes")
    
    # Also recreate reviews table to match
    cursor.execute("DROP TABLE IF EXISTS reviews CASCADE;")
    cursor.execute("""
        CREATE TABLE reviews (
            id SERIAL PRIMARY KEY,
            cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
            original_text TEXT NOT NULL,
            rating INTEGER,
            version VARCHAR(100),
            device VARCHAR(100),
            review_date TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    print("✅ Created reviews table")
    
    cursor.execute("CREATE INDEX idx_reviews_cluster_id ON reviews(cluster_id);")
    print("✅ Created reviews indexes")
    
    print("\n" + "=" * 80)
    print("✅ All tables fixed!")
    print("=" * 80)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    fix_clusters_id()
