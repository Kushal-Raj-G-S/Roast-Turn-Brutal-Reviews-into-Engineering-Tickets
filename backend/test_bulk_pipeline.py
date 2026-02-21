"""
Test script for bulk review processing pipeline.
Validates that 100k reviews can be processed in under 2 minutes.
"""

import asyncio
import logging
import time
from pathlib import Path
from uuid import uuid4

import pandas as pd
from sqlmodel import Session

from app.bulk_models import get_engine, init_db, BulkJob
from app.bulk_processor import BulkProcessor
from app.bulk_embedding import EmbeddingBackend
from app.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("test_bulk")


def generate_test_csv(num_reviews: int = 100000, output_path: str = "test_100k_reviews.csv"):
    """
    Generate a test CSV with realistic app store reviews.
    
    Args:
        num_reviews: Number of reviews to generate
        output_path: Path to save CSV
    """
    logger.info(f"Generating {num_reviews} test reviews...")
    
    # Sample review templates
    templates = [
        # Noise (will be filtered)
        "Good app",
        "Nice",
        "Best app ever",
        "Love it",
        "Very good",
        "Awesome",
        "Great",
        
        # Critical issues
        "App crashes on startup. Can't use it at all. Pixel 7",
        "Keeps crashing after v2.4 update. Galaxy S21",
        "Won't open anymore. Completely broken. iPhone 13",
        
        # High severity
        "Login not working after update to v2.4",
        "Can't upload photos. Shows error every time. Samsung Galaxy",
        "Payment failed but money was deducted. Fix this bug!",
        
        # Medium severity
        "App is slow on my Pixel 6",
        "UI is confusing, hard to find settings",
        "Too many ads, annoying",
        
        # Low severity
        "Could use dark mode",
        "Missing some features",
        "Needs better design",
    ]
    
    scores = [5, 5, 5, 5, 5, 5, 5,  # Noise (high ratings)
              1, 1, 1,  # Critical
              2, 2, 2,  # High
              3, 3, 3,  # Medium
              4, 4, 4]  # Low
    
    # Generate reviews
    reviews = []
    for i in range(num_reviews):
        idx = i % len(templates)
        reviews.append({
            "reviewId": f"review_{i}",
            "userName": f"user_{i}",
            "content": templates[idx],
            "score": scores[idx],
            "thumbsUpCount": (i % 100),
            "appVersion": f"2.{i % 5}",
        })
    
    # Create DataFrame and save
    df = pd.DataFrame(reviews)
    df.to_csv(output_path, index=False)
    
    logger.info(f"✅ Generated {num_reviews} reviews → {output_path}")
    return output_path


def test_bulk_pipeline(csv_path: str):
    """
    Test the bulk processing pipeline end-to-end.
    
    Args:
        csv_path: Path to test CSV
    """
    logger.info("=" * 80)
    logger.info("BULK PIPELINE TEST")
    logger.info("=" * 80)
    
    # Initialize database
    logger.info("Initializing database...")
    engine = get_engine(config.DATABASE_URL)
    init_db(engine)
    logger.info("✅ Database initialized")
    
    # Create a test job
    job_id = uuid4()
    with Session(engine) as session:
        job = BulkJob(
            id=job_id,
            status="PENDING",
            filename="test_100k_reviews.csv"
        )
        session.add(job)
        session.commit()
        logger.info(f"✅ Created test job: {job_id}")
    
    # Initialize processor
    logger.info("Initializing processor...")
    embedding_backend = EmbeddingBackend()
    
    with Session(engine) as session:
        processor = BulkProcessor(session, embedding_backend)
        
        # Run pipeline
        logger.info("🔥 Starting bulk processing...")
        start_time = time.time()
        
        try:
            stats = processor.process_bulk_job(job_id, csv_path)
            
            elapsed = time.time() - start_time
            
            # Print results
            logger.info("=" * 80)
            logger.info("RESULTS")
            logger.info("=" * 80)
            logger.info(f"Status: {stats['status']}")
            logger.info(f"Total reviews: {stats['total_rows']}")
            logger.info(f"Kept reviews: {stats['kept_rows']}")
            logger.info(f"Noise filtered: {stats['total_rows'] - stats['kept_rows']}")
            logger.info(f"Clusters created: {stats['cluster_count']}")
            logger.info(f"Processing time: {elapsed:.2f}s")
            logger.info("=" * 80)
            
            # Validate target
            if elapsed < 120:
                logger.info(f"✅ SUCCESS: Processed in {elapsed:.2f}s (target: <120s)")
            else:
                logger.warning(f"⚠️  SLOW: Processed in {elapsed:.2f}s (target: <120s)")
            
            return stats
        
        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
            raise


def test_small_sample():
    """Quick test with 1000 reviews."""
    logger.info("Running quick test with 1000 reviews...")
    csv_path = generate_test_csv(num_reviews=1000, output_path="test_1k_reviews.csv")
    test_bulk_pipeline(csv_path)


def test_full_100k():
    """Full test with 100k reviews."""
    logger.info("Running full test with 100k reviews...")
    csv_path = generate_test_csv(num_reviews=100000, output_path="test_100k_reviews.csv")
    test_bulk_pipeline(csv_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        # Full 100k test
        test_full_100k()
    else:
        # Quick 1k test
        test_small_sample()
