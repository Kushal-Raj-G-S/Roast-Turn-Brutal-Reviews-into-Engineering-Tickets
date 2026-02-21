"""
Background worker for processing bulk jobs.
Polls for PENDING jobs and processes them using BulkProcessor.
"""

import asyncio
import logging
from pathlib import Path

from sqlmodel import Session, select

from app.bulk_models import BulkJob, get_engine, get_session
from app.bulk_processor import BulkProcessor
from app.bulk_embedding import EmbeddingBackend
from app.config import config

logger = logging.getLogger(__name__)


class BulkWorker:
    """
    Background worker that processes bulk jobs.
    
    Runs in a loop, polling for PENDING jobs and processing them.
    """
    
    def __init__(self, engine):
        """
        Initialize worker.
        
        Args:
            engine: SQLAlchemy engine
        """
        self.engine = engine
        self.embedding_backend = None
        self.is_running = False
    
    def _init_embedding_backend(self):
        """Initialize embedding backend (lazy load)."""
        if not self.embedding_backend:
            logger.info("Initializing embedding backend for worker")
            self.embedding_backend = EmbeddingBackend()
    
    async def start(self):
        """Start the worker loop."""
        logger.info("Starting bulk worker")
        self.is_running = True
        
        while self.is_running:
            try:
                await self._process_pending_jobs()
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
            
            # Sleep before next poll
            await asyncio.sleep(config.WORKER_POLL_INTERVAL)
    
    def stop(self):
        """Stop the worker loop."""
        logger.info("Stopping bulk worker")
        self.is_running = False
    
    async def _process_pending_jobs(self):
        """
        Find and process pending jobs.
        
        This is run in the asyncio event loop but uses synchronous DB operations
        since SQLModel/SQLAlchemy doesn't require async for our use case.
        """
        with Session(self.engine) as session:
            # Find pending jobs
            statement = select(BulkJob).where(BulkJob.status == "PENDING").limit(1)
            job = session.exec(statement).first()
            
            if not job:
                return  # No pending jobs
            
            logger.info(f"Found pending job {job.id}")
            
            # Initialize embedding backend if needed
            self._init_embedding_backend()
            
            # Get CSV path
            csv_path = Path(config.UPLOAD_DIR) / f"{job.id}.csv"
            
            if not csv_path.exists():
                logger.error(f"CSV file not found for job {job.id}: {csv_path}")
                job.status = "FAILED"
                job.error_message = f"CSV file not found: {csv_path}"
                session.commit()
                return
            
            # Process job (this will update job status)
            try:
                # Create processor with session
                processor = BulkProcessor(
                    session=session,
                    embedding_backend=self.embedding_backend
                )
                
                # Process job (runs synchronously)
                await asyncio.to_thread(
                    processor.process_bulk_job,
                    job.id,
                    str(csv_path)
                )
                
                logger.info(f"Job {job.id} completed successfully")
            
            except Exception as e:
                logger.error(f"Job {job.id} failed: {e}", exc_info=True)
                # Error already logged in processor


# Global worker instance
_worker: BulkWorker = None


async def start_worker(engine):
    """
    Start the background worker.
    
    This should be called on FastAPI startup.
    
    Args:
        engine: SQLAlchemy engine
    """
    global _worker
    
    if _worker and _worker.is_running:
        logger.warning("Worker already running")
        return
    
    _worker = BulkWorker(engine)
    
    # Start worker in background task
    asyncio.create_task(_worker.start())
    logger.info("Background worker started")


def stop_worker():
    """Stop the background worker."""
    global _worker
    
    if _worker:
        _worker.stop()
        _worker = None
        logger.info("Background worker stopped")
