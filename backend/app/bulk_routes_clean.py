"""
FastAPI routes for bulk upload and job management (optimized system).
Uses 'uploads' table with INTEGER id.
"""

import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.bulk_models import Upload, Cluster
from app.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["bulk"])


# Response models
class UploadResponse(BaseModel):
    """Response for bulk upload."""
    upload_id: int
    status: str
    message: str


class UploadStatusResponse(BaseModel):
    """Response for upload status."""
    upload_id: int
    status: str
    filename: str
    total_reviews: Optional[int] = None
    processed_reviews: Optional[int] = None
    filtered_noise: Optional[int] = None
    clusters_created: Optional[int] = None
    ai_analyzed_count: Optional[int] = None
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class UploadListResponse(BaseModel):
    """Response for upload list."""
    uploads: list[UploadStatusResponse]
    total: int


class ClusterResponse(BaseModel):
    """Response for cluster."""
    id: int
    title: str
    severity: str
    status: str
    review_count: int
    rca_title: Optional[str] = None
    rca_hypothesis: Optional[str] = None
    created_at: str


# Dependency to get DB session
def get_db_session():
    """Get database session for dependency injection."""
    from app.bulk_api import get_engine_instance
    engine = get_engine_instance()
    if not engine:
        raise HTTPException(status_code=503, detail="Database not initialized")
    with Session(engine) as session:
        yield session


@router.post("/upload", response_model=UploadResponse)
async def bulk_upload(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session)
):
    """
    Upload a CSV file for bulk processing.
    
    Creates a new Upload record with status PENDING and saves the file.
    The background worker will pick it up and process it.
    
    Args:
        file: CSV file with reviews
        session: Database session
    
    Returns:
        UploadResponse with upload_id
    """
    try:
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")
        
        # Check file size (in MB)
        file.file.seek(0, 2)  # Seek to end
        file_size_bytes = file.file.tell()
        file_size_mb = file_size_bytes / (1024 * 1024)
        file.file.seek(0)  # Reset
        
        if file_size_mb > config.MAX_UPLOAD_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {config.MAX_UPLOAD_SIZE_MB}MB"
            )
        
        # Create upload directory
        config.ensure_upload_dir()
        
        # TODO: Get user_id from authentication
        # For now, use a dummy UUID (this should come from auth)
        from uuid import uuid4
        dummy_user_id = uuid4()
        
        # Create upload record
        upload = Upload(
            user_id=dummy_user_id,
            filename=file.filename,
            file_size_bytes=file_size_bytes,
            status="PENDING"
        )
        session.add(upload)
        session.commit()
        session.refresh(upload)
        
        # Save file
        file_path = Path(config.UPLOAD_DIR) / f"{upload.id}.csv"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"Created upload {upload.id} for file {file.filename} ({file_size_mb:.2f}MB)")
        
        return UploadResponse(
            upload_id=upload.id,
            status="PENDING",
            message=f"Upload created successfully. Processing will start shortly."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/uploads/{upload_id}/progress", response_model=UploadStatusResponse)
async def get_upload_status(
    upload_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get status of an upload.
    
    Args:
        upload_id: Upload ID
        session: Database session
    
    Returns:
        UploadStatusResponse with upload details
    """
    upload = session.get(Upload, upload_id)
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    return UploadStatusResponse(
        upload_id=upload.id,
        status=upload.status,
        filename=upload.filename,
        total_reviews=upload.total_reviews,
        processed_reviews=upload.processed_reviews,
        filtered_noise=upload.filtered_noise,
        clusters_created=upload.clusters_created,
        ai_analyzed_count=upload.ai_analyzed_count,
        processing_time_ms=upload.processing_time_ms,
        error_message=upload.error_message,
        created_at=upload.created_at.isoformat(),
        completed_at=upload.completed_at.isoformat() if upload.completed_at else None
    )


@router.get("/uploads", response_model=UploadListResponse)
async def list_uploads(
    limit: int = 10,
    offset: int = 0,
    session: Session = Depends(get_db_session)
):
    """
    List all uploads with pagination.
    
    Args:
        limit: Max number of results
        offset: Number of results to skip
        session: Database session
    
    Returns:
        UploadListResponse with list of uploads
    """
    # Get total count
    total_statement = select(Upload)
    total = len(session.exec(total_statement).all())
    
    # Get paginated results
    statement = (
        select(Upload)
        .order_by(Upload.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    uploads = session.exec(statement).all()
    
    return UploadListResponse(
        uploads=[
            UploadStatusResponse(
                upload_id=u.id,
                status=u.status,
                filename=u.filename,
                total_reviews=u.total_reviews,
                processed_reviews=u.processed_reviews,
                filtered_noise=u.filtered_noise,
                clusters_created=u.clusters_created,
                ai_analyzed_count=u.ai_analyzed_count,
                processing_time_ms=u.processing_time_ms,
                error_message=u.error_message,
                created_at=u.created_at.isoformat(),
                completed_at=u.completed_at.isoformat() if u.completed_at else None
            )
            for u in uploads
        ],
        total=total
    )


@router.get("/uploads/{upload_id}/clusters", response_model=list[ClusterResponse])
async def get_upload_clusters(
    upload_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get all clusters for an upload.
    
    Args:
        upload_id: Upload ID
        session: Database session
    
    Returns:
        List of ClusterResponse
    """
    # Verify upload exists
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    # Get clusters
    statement = (
        select(Cluster)
        .where(Cluster.upload_id == upload_id)
        .order_by(Cluster.created_at.desc())
    )
    clusters = session.exec(statement).all()
    
    return [
        ClusterResponse(
            id=c.id,
            title=c.title,
            severity=c.severity,
            status=c.status,
            review_count=c.review_count,
            rca_title=c.rca_title,
            rca_hypothesis=c.rca_hypothesis,
            created_at=c.created_at.isoformat()
        )
        for c in clusters
    ]
