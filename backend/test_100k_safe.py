"""
Safe test for 100k reviews with detailed reporting.
Processes in smaller chunks to prevent crashes.
"""

import logging
import time
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session

from app.bulk_models import get_engine, init_db, BulkJob, Cluster
from app.bulk_processor import BulkProcessor
from app.bulk_embedding import EmbeddingBackend
from app.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("test_100k")


def display_clusters(session: Session, job_id):
    """Display top priority clusters (frontend output preview)."""
    from sqlmodel import select
    
    # Fetch clusters for this job
    statement = select(Cluster).where(Cluster.job_id == job_id).order_by(Cluster.severity.desc())
    clusters = session.exec(statement).all()
    
    if not clusters:
        logger.warning("No clusters found!")
        return
    
    logger.info("=" * 80)
    logger.info("TOP PRIORITY CLUSTERS (Frontend Output Preview)")
    logger.info("=" * 80)
    logger.info(f"Total clusters persisted: {len(clusters)}")
    logger.info("")
    
    # Group by severity
    severity_groups = {}
    for cluster in clusters:
        severity = cluster.severity
        if severity not in severity_groups:
            severity_groups[severity] = []
        severity_groups[severity].append(cluster)
    
    # Display each severity group
    severity_order = ['critical', 'high', 'medium', 'low']
    
    for severity in severity_order:
        if severity not in severity_groups:
            continue
        
        group = severity_groups[severity]
        logger.info(f"🔴 {severity.upper()} PRIORITY ({len(group)} clusters)")
        logger.info("-" * 80)
        
        for i, cluster in enumerate(group, 1):
            logger.info(f"  #{i} {cluster.title}")
            logger.info(f"      Reviews: {cluster.review_count} | Status: {cluster.status}")
            logger.info(f"      Sample: {cluster.sample_content[:150]}...")
            logger.info("")
    
    logger.info("=" * 80)



def test_100k_reviews():
    """Test the 100k reviews CSV with detailed reporting."""
    
    csv_path = Path("E:\\BMSIT\\Personal Ai projects\\1 Internship-Resume Projects\\5_Roast_google_reviews\\chatgpt_reviews.csv")
    
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return
    
    logger.info("=" * 80)
    logger.info("100K REVIEWS TEST - DETAILED REPORT")
    logger.info("=" * 80)
    logger.info(f"CSV Path: {csv_path}")
    logger.info(f"Batch Size: {config.BATCH_SIZE}")
    logger.info(f"Workers: {config.NUM_WORKERS}")
    logger.info(f"Cosine Threshold: {config.COSINE_THRESHOLD}")
    logger.info("=" * 80)
    
    # Initialize database
    logger.info("Step 1/6: Initializing database...")
    start_time = time.time()
    engine = get_engine(config.DATABASE_URL)
    init_db(engine)
    init_time = time.time() - start_time
    logger.info(f"✅ Database initialized in {init_time:.2f}s")
    
    # Create job
    logger.info("Step 2/6: Creating bulk job...")
    start_time = time.time()
    job_id = uuid4()
    with Session(engine) as session:
        job = BulkJob(
            id=job_id,
            status="PENDING",
            filename="test_100k_reviews.csv"
        )
        session.add(job)
        session.commit()
    job_time = time.time() - start_time
    logger.info(f"✅ Created job {job_id} in {job_time:.2f}s")
    
    # Initialize embedding backend
    logger.info("Step 3/6: Loading embedding model...")
    start_time = time.time()
    embedding_backend = EmbeddingBackend()
    model_time = time.time() - start_time
    logger.info(f"✅ Model loaded in {model_time:.2f}s")
    
    # Process
    logger.info("Step 4/6: Processing reviews...")
    logger.info("This may take several minutes. Please wait...")
    
    total_start = time.time()
    
    with Session(engine) as session:
        processor = BulkProcessor(session, embedding_backend)
        
        try:
            stats = processor.process_bulk_job(job_id, str(csv_path))
            
            total_time = time.time() - total_start
            
            # Detailed report
            logger.info("=" * 80)
            logger.info("DETAILED RESULTS")
            logger.info("=" * 80)
            logger.info(f"Status: {stats['status']}")
            logger.info(f"")
            logger.info(f"REVIEW STATISTICS:")
            logger.info(f"  Total reviews: {stats['total_rows']:,}")
            logger.info(f"  Kept reviews: {stats['kept_rows']:,}")
            logger.info(f"  Noise filtered: {stats['total_rows'] - stats['kept_rows']:,}")
            logger.info(f"  Noise rate: {((stats['total_rows'] - stats['kept_rows']) / stats['total_rows'] * 100):.1f}%")
            logger.info(f"")
            logger.info(f"CLUSTERING RESULTS:")
            logger.info(f"  Clusters created: {stats['cluster_count']}")
            logger.info(f"  Avg reviews per cluster: {stats['kept_rows'] / stats['cluster_count']:.1f}")
            logger.info(f"")
            logger.info(f"PERFORMANCE:")
            logger.info(f"  Database init: {init_time:.2f}s")
            logger.info(f"  Job creation: {job_time:.2f}s")
            logger.info(f"  Model loading: {model_time:.2f}s")
            logger.info(f"  Processing: {stats['elapsed_seconds']:.2f}s")
            logger.info(f"  Total time: {total_time:.2f}s")
            logger.info(f"")
            logger.info(f"  Reviews/second: {stats['total_rows'] / stats['elapsed_seconds']:.1f}")
            logger.info(f"  Embeddings/second: {stats['kept_rows'] / stats['elapsed_seconds']:.1f}")
            logger.info("=" * 80)
            
            # Target validation
            target_minutes = 2
            if stats['elapsed_seconds'] < target_minutes * 60:
                logger.info(f"✅ SUCCESS: Processed in {stats['elapsed_seconds']:.2f}s (target: <{target_minutes * 60}s)")
            else:
                logger.warning(f"⚠️  SLOW: Processed in {stats['elapsed_seconds']:.2f}s (target: <{target_minutes * 60}s)")
                minutes = stats['elapsed_seconds'] / 60
                logger.info(f"   Took {minutes:.1f} minutes")
            
            # Step 5: Display top clusters (what frontend will show)
            logger.info("")
            logger.info("Step 5/6: Fetching top priority clusters...")
            display_clusters(session, job_id)
            
            return stats
        
        except Exception as e:
            logger.error(f"❌ Processing failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    test_100k_reviews()
