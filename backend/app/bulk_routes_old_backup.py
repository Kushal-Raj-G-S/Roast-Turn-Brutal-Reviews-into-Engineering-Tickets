"""
FastAPI routes for bulk upload and job management.
"""

import logging
import os
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.bulk_models import BulkJob, get_session
from app.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["bulk"])


# Response models
class BulkUploadResponse(BaseModel):
    """Response for bulk upload."""
    job_id: str
    status: str
    message: str


class BulkJobStatusResponse(BaseModel):
    """Response for job status."""
    job_id: str
    status: str
    filename: Optional[str] = None
    total_rows: Optional[int] = None
    processed_rows: Optional[int] = None
    kept_rows: Optional[int] = None
    cluster_count: Optional[int] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class BulkJobListResponse(BaseModel):
    """Response for job list."""
    jobs: list[BulkJobStatusResponse]
    total: int


# Dependency to get DB session
def get_db_session():
    """Get database session for dependency injection."""
    from app.bulk_api import get_engine_instance
    engine = get_engine_instance()
    if not engine:
        raise HTTPException(status_code=503, detail="Database not initialized")
    with Session(engine) as session:
        yield session


@router.post("/upload", response_model=BulkUploadResponse)
async def bulk_upload(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session)
):
    """
    Upload a CSV file for bulk processing.
    
    Creates a new BulkJob with status PENDING and saves the file.
    The background worker will pick it up and process it.
    
    Args:
        file: CSV file with reviews
        session: Database session
    
    Returns:
        BulkUploadResponse with job_id
    """
    try:
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")
        
        # Check file size (in MB)
        file.file.seek(0, 2)  # Seek to end
        file_size_mb = file.file.tell() / (1024 * 1024)
        file.file.seek(0)  # Reset
        
        if file_size_mb > config.MAX_UPLOAD_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {config.MAX_UPLOAD_SIZE_MB}MB"
            )
        
        # Create upload directory
        config.ensure_upload_dir()
        
        # Create job
        job = BulkJob(
            status="PENDING",
            filename=file.filename
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        
        # Save file
        file_path = Path(config.UPLOAD_DIR) / f"{job.id}.csv"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"Created bulk job {job.id} for file {file.filename} ({file_size_mb:.2f}MB)")
        
        return BulkUploadResponse(
            job_id=str(job.id),
            status="PENDING",
            message=f"Job created successfully. Processing will start shortly."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/bulk-jobs/{job_id}", response_model=BulkJobStatusResponse)
async def get_bulk_job_status(
    job_id: UUID,
    session: Session = Depends(get_db_session)
):
    """
    Get status of a bulk job.
    
    Args:
        job_id: Job UUID
        session: Database session
    
    Returns:
        BulkJobStatusResponse with job details
    """
    job = session.get(BulkJob, job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return BulkJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        filename=job.filename,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        kept_rows=job.kept_rows,
        cluster_count=job.cluster_count,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat()
    )


@router.get("/bulk-jobs", response_model=BulkJobListResponse)
async def list_bulk_jobs(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db_session)
):
    """
    List all bulk jobs.
    
    Args:
        limit: Max number of jobs to return
        offset: Offset for pagination
        session: Database session
    
    Returns:
        BulkJobListResponse with list of jobs
    """
    # Get total count
    statement = select(BulkJob)
    all_jobs = session.exec(statement).all()
    total = len(all_jobs)
    
    # Get paginated results
    jobs = session.exec(
        select(BulkJob)
        .order_by(BulkJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    
    return BulkJobListResponse(
        jobs=[
            BulkJobStatusResponse(
                job_id=str(job.id),
                status=job.status,
                filename=job.filename,
                total_rows=job.total_rows,
                processed_rows=job.processed_rows,
                kept_rows=job.kept_rows,
                cluster_count=job.cluster_count,
                error_message=job.error_message,
                created_at=job.created_at.isoformat(),
                updated_at=job.updated_at.isoformat()
            )
            for job in jobs
        ],
        total=total
    )


@router.get("/clusters")
async def list_clusters(
    job_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db_session)
):
    """
    List clusters, optionally filtered by job_id.
    
    Args:
        job_id: Optional job ID to filter by
        limit: Max number of clusters to return
        offset: Offset for pagination
        session: Database session
    
    Returns:
        List of clusters
    """
    from app.bulk_models import Cluster
    
    statement = select(Cluster)
    
    if job_id:
        statement = statement.where(Cluster.job_id == job_id)
    
    statement = statement.order_by(Cluster.created_at.desc()).limit(limit).offset(offset)
    
    clusters = session.exec(statement).all()
    
    return {
        "clusters": [
            {
                "id": str(cluster.id),
                "job_id": str(cluster.job_id),
                "title": cluster.title,
                "severity": cluster.severity,
                "status": cluster.status,
                "review_count": cluster.review_count,
                "sample_content": cluster.sample_content,
                "created_at": cluster.created_at.isoformat()
            }
            for cluster in clusters
        ],
        "total": len(clusters)
    }


@router.get("/reviews")
async def list_reviews(
    job_id: Optional[UUID] = None,
    cluster_id: Optional[UUID] = None,
    include_noise: bool = False,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db_session)
):
    """
    List reviews, optionally filtered by job_id or cluster_id.
    
    Args:
        job_id: Optional job ID to filter by
        cluster_id: Optional cluster ID to filter by
        include_noise: Whether to include noise reviews
        limit: Max number of reviews to return
        offset: Offset for pagination
        session: Database session
    
    Returns:
        List of reviews
    """
    from app.bulk_models import Review
    
    statement = select(Review)
    
    if job_id:
        statement = statement.where(Review.job_id == job_id)
    
    if cluster_id:
        statement = statement.where(Review.cluster_id == cluster_id)
    
    if not include_noise:
        statement = statement.where(Review.is_noise == False)
    
    statement = statement.limit(limit).offset(offset)
    
    reviews = session.exec(statement).all()
    
    return {
        "reviews": [
            {
                "id": str(review.id),
                "job_id": str(review.job_id),
                "cluster_id": str(review.cluster_id) if review.cluster_id else None,
                "review_id": review.review_id,
                "user_name": review.user_name,
                "content": review.content,
                "score": review.score,
                "is_noise": review.is_noise,
                "version": review.version,
                "device": review.device
            }
            for review in reviews
        ],
        "total": len(reviews)
    }
