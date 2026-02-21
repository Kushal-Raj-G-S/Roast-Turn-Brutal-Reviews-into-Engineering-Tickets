"""
Add new columns to existing tables:
- uploads.processing_time_seconds
- clusters.sample_reviews
"""

import os
import logging
from dotenv import load_dotenv
from sqlalchemy import text, create_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment")

# Create engine
engine = create_engine(DATABASE_URL, echo=True)

def add_columns():
    """Add new columns to tables."""
    
    with engine.begin() as conn:
        # Add processing_time_seconds to uploads table
        logger.info("Adding processing_time_seconds column to uploads table...")
        try:
            conn.execute(text("""
                ALTER TABLE uploads 
                ADD COLUMN IF NOT EXISTS processing_time_seconds FLOAT
            """))
            logger.info("✓ Added processing_time_seconds column")
        except Exception as e:
            logger.warning(f"Column might already exist: {e}")
        
        # Add sample_reviews to clusters table
        logger.info("Adding sample_reviews column to clusters table...")
        try:
            conn.execute(text("""
                ALTER TABLE clusters 
                ADD COLUMN IF NOT EXISTS sample_reviews JSONB
            """))
            logger.info("✓ Added sample_reviews column")
        except Exception as e:
            logger.warning(f"Column might already exist: {e}")
    
    logger.info("✓ Migration completed successfully!")

if __name__ == "__main__":
    add_columns()
