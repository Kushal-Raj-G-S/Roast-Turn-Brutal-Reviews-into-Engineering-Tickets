"""
Background worker for processing bulk jobs.
Polls for PENDING jobs and processes them using BulkProcessor.

NOTE (architecture): All uploads created via POST /upload are assigned
status='shadow_processing' and are handled entirely by the shadow deployment
orchestrator (shadow_deployment.py). This worker therefore never finds any
jobs to process in the current architecture.

The worker is kept alive as a safety net for any future uploads that may
be created with status='pending' (e.g. direct DB inserts, admin tools, or
if the shadow orchestrator is disabled). It does NOT consume resources when
idle — it simply wakes, queries, finds nothing, and sleeps.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.models.bulk_models import Upload, get_engine, get_session
from app.services.bulk_processor import BulkProcessor
from app.services.bulk_embedding import EmbeddingBackend
from app.services import explanation_cache
from app.services.explanation_pregenerate import pregenerate_for_upload
from app.core.config import config

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
        _db_backoff = 0  # seconds; 0 means no extra wait

        while self.is_running:
            try:
                await self._process_pending_jobs()
                _db_backoff = 0  # reset on success
            except OperationalError as e:
                # DB unreachable (DNS, pooler timeout, Supabase pause, etc.)
                _db_backoff = min(_db_backoff * 2 if _db_backoff else 5, 120)  # 5→10→20→40→80→120 cap
                logger.warning(
                    f"DB connection failed (will retry in {_db_backoff}s): {e.__class__.__name__}: {e.orig}"
                )
                # Dispose stale pool so next attempt gets a fresh connection
                try:
                    self.engine.dispose()
                except Exception:
                    pass
                await asyncio.sleep(_db_backoff)
                continue  # skip normal poll sleep
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)

            # Normal poll interval
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
        # Use a separate session just for finding pending jobs
        with Session(self.engine) as session:
            # Find ONLY 'pending' jobs (orchestrator uses 'shadow_processing')
            statement = select(Upload).where(Upload.status == "pending").limit(1)
            job = session.exec(statement).first()
            
            if not job:
                return  # No pending jobs
            
            job_id = job.id
            logger.info(f"[worker] Found pending upload {job_id}")
        
        # Initialize embedding backend if needed
        self._init_embedding_backend()
        
        # Get CSV path
        csv_path = Path(config.UPLOAD_DIR) / f"{job_id}.csv"
        
        # 🔥 FIX: Retry with exponential backoff for file race condition
        max_retries = 5
        retry_delay = 1.0  # seconds
        
        for attempt in range(max_retries):
            if csv_path.exists():
                break
            
            if attempt < max_retries - 1:
                logger.warning(f"CSV file not found (attempt {attempt + 1}/{max_retries}): {csv_path}, retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff
            else:
                # Final attempt failed
                with Session(self.engine) as session:
                    job = session.get(Upload, job_id)
                    if job:
                        logger.error(f"CSV file not found after {max_retries} attempts for upload {job_id}: {csv_path}")
                        job.status = "failed"
                        job.error_message = f"CSV file not found after {max_retries} retries: {csv_path}"
                        session.commit()
                return
        
        # Process upload (processor will manage its own session)
        try:
            # Track processing time
            start_time = time.time()
            
            # Create a new session for the processor
            with Session(self.engine) as processor_session:
                # Create processor with its own session
                processor = BulkProcessor(
                    session=processor_session,
                    embedding_backend=self.embedding_backend
                )
                
                # Process upload (runs synchronously)
                await asyncio.to_thread(
                    processor.process_bulk_job,
                    job_id,
                    str(csv_path)
                )
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Update processing time
            with Session(self.engine) as session:
                job = session.get(Upload, job_id)
                if job:
                    job.processing_time_seconds = round(processing_time, 2)
                    session.commit()
            
            logger.info(f"✓ Upload {job_id} completed in {processing_time:.2f}s")

            # 🧠 Pre-generate 4 severity-category explanations in background.
            # By the time the user navigates from analytics → AI Debug Center
            # (typically 5+ minutes), explanations will already be ready.
            try:
                for sev in ["critical", "high", "medium", "low"]:
                    explanation_cache.set_status(job_id, sev, "pending")
                asyncio.create_task(pregenerate_for_upload(job_id, self.engine))
                logger.info(f"[worker] Triggered severity explanation pre-generation for upload {job_id}")
            except Exception as eg:
                logger.warning(f"[worker] Pre-generation trigger failed (non-fatal): {eg}")

        except Exception as e:
            logger.error(f"Upload {job_id} failed: {e}", exc_info=True)
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
