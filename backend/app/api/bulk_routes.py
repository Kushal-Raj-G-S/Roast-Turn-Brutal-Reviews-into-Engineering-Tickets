"""
FastAPI routes for bulk upload and job management (optimized system).
Uses 'uploads' table with INTEGER id.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.models.bulk_models import Upload, Cluster
from app.core.config import config
from app.database.auth_supabase import get_current_user
from app.models.models_supabase import Profile
from app.core.shadow_deployment import schedule_shadow_deployment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["bulk"])


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
    processing_time_seconds: Optional[float] = None
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


class ClusterDetailResponse(BaseModel):
    """Response for cluster with full reviews."""
    id: int
    title: str
    severity: str
    status: str
    review_count: int
    rca_title: Optional[str] = None
    rca_hypothesis: Optional[str] = None
    rca_steps: Optional[str] = None
    rca_fix: Optional[str] = None
    affected_versions: Optional[list[str]] = None
    affected_devices: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    sample_reviews: Optional[list[dict]] = None
    created_at: str


# Dependency to get DB session
def get_db_session():
    """Get database session for dependency injection."""
    from app.api.bulk_api import get_engine_instance
    engine = get_engine_instance()
    if not engine:
        raise HTTPException(status_code=503, detail="Database not initialized")
    with Session(engine) as session:
        yield session


@router.post("/upload", response_model=UploadResponse)
async def bulk_upload(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user)
):
    """
    Upload a CSV file for bulk processing.
    
    Creates a new Upload record with status PENDING and saves the file.
    The background worker will pick it up and process it.
    
    🔥 Automatically triggers shadow deployment (v2 + v3 monitoring).
    
    Args:
        file: CSV file with reviews
        background_tasks: FastAPI background tasks
        session: Database session
        user: Authenticated user
    
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
        
        # Create upload record with authenticated user
        # Use status='shadow_processing' so worker ignores it (orchestrator handles these)
        upload = Upload(
            user_id=user.id,
            filename=file.filename,
            file_size_bytes=file_size_bytes,
            status="shadow_processing"  # Orchestrator-managed, worker ignores
        )
        
        session.add(upload)
        session.commit()
        session.refresh(upload)
        
        # Save file
        file_path = Path(config.UPLOAD_DIR) / f"{upload.id}.csv"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # 🔥 FIX: Verify file exists before triggering shadow deployment (fixes race condition)
        if not file_path.exists():
            logger.error(f"File not saved properly: {file_path}")
            raise HTTPException(status_code=500, detail="Failed to save file")
        
        logger.info(f"Created upload {upload.id} for file {file.filename} ({file_size_mb:.2f}MB)")
        
        # 🔥 TRIGGER SHADOW DEPLOYMENT (v2 + v3 monitoring in background)
        # v1 will be processed by the worker, shadow deployment runs v2 in parallel
        if background_tasks:
            background_tasks.add_task(
                schedule_shadow_deployment,
                upload.id,
                str(file_path)
            )
            logger.info(f"🔄 Shadow deployment scheduled for upload {upload.id}")
        
        return UploadResponse(
            upload_id=upload.id,
            status="pending",
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
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user)
):
    """
    Get status of an upload.

    Returns only uploads belonging to the authenticated user.
    """
    upload = session.get(Upload, upload_id)

    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if str(upload.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized to view this upload")
    
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
        processing_time_seconds=upload.processing_time_seconds,
        error_message=upload.error_message,
        created_at=upload.created_at.isoformat(),
        completed_at=upload.completed_at.isoformat() if upload.completed_at else None
    )


@router.get("/uploads", response_model=UploadListResponse)
async def list_uploads(
    limit: int = 10,
    offset: int = 0,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user)
):
    """
    List uploads for the authenticated user with pagination.
    """
    # Efficient count — no full table scan
    total = session.exec(
        select(func.count(Upload.id)).where(Upload.user_id == user.id)
    ).one()

    # Get paginated results for this user only
    statement = (
        select(Upload)
        .where(Upload.user_id == user.id)
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
                processing_time_seconds=u.processing_time_seconds,
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
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user)
):
    """
    Get all clusters for an upload.

    Returns clusters only if the upload belongs to the authenticated user.
    """
    # Verify upload exists and is owned by user
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if str(upload.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized to view this upload")
    
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


# ---------------------------------------------------------------------------
# Severity-category explanation endpoints
# ---------------------------------------------------------------------------

class SeverityExplanationResponse(BaseModel):
    """Pre-generated explanation for one severity category."""
    upload_id: int
    severity: str
    status: str  # not_started | pending | generating | done | failed
    explanation: Optional[str] = None


@router.get("/uploads/{upload_id}/severity-explanations/{severity}", response_model=SeverityExplanationResponse)
async def get_severity_explanation(
    upload_id: int,
    severity: str,
    session: Session = Depends(get_db_session)
):
    """
    Return the pre-generated AI explanation for one severity category of an upload.
    Checks DB first (persistent across restarts), falls back to in-memory cache
    for explanations still being generated in this process.
    Poll every 5 s while status is 'pending' or 'generating'.
    """
    from app.models.bulk_models import SeverityExplanation
    from app.services import explanation_cache

    if severity not in ("critical", "high", "medium", "low"):
        raise HTTPException(status_code=400, detail="severity must be critical / high / medium / low")

    # 1. DB — authoritative, survives server restarts
    row = session.exec(
        select(SeverityExplanation).where(
            SeverityExplanation.upload_id == upload_id,
            SeverityExplanation.severity == severity,
        )
    ).first()
    if row:
        return SeverityExplanationResponse(
            upload_id=upload_id,
            severity=severity,
            status=row.status,
            explanation=row.explanation,
        )

    # 2. In-memory — still generating in this process (DB write pending)
    cached = explanation_cache.get(upload_id, severity)
    if cached:
        return SeverityExplanationResponse(
            upload_id=upload_id,
            severity=severity,
            status=cached.get("status", "not_started"),
            explanation=cached.get("explanation"),
        )

    return SeverityExplanationResponse(upload_id=upload_id, severity=severity, status="not_started")


class ClusterExplainResponse(BaseModel):
    """AI-generated explanation for a cluster."""
    cluster_id: int
    title: str
    explanation: str
    reviews_used: int
    total_reviews: int


@router.get("/clusters/{cluster_id}/explain", response_model=ClusterExplainResponse)
async def explain_cluster(
    cluster_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Generate an AI explanation for a cluster by reading its sample reviews.
    Hard cap: reads at most 25 reviews regardless of cluster size.
    """
    from app.services.llm_service import get_llm_service

    cluster = session.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    MAX_REVIEWS = 25
    raw_reviews: list = cluster.sample_reviews or []
    capped = raw_reviews[:MAX_REVIEWS]

    if not capped:
        return ClusterExplainResponse(
            cluster_id=cluster_id,
            title=cluster.title,
            explanation="No sample reviews are stored for this cluster.",
            reviews_used=0,
            total_reviews=cluster.review_count or 0,
        )

    # Build numbered review list for the prompt
    review_lines = "\n".join(
        f'{i+1}. Rating {r.get("rating", "?")}★  |  version {r.get("version", "?")}  |  device {r.get("device", "?")}\n   "{r.get("content", "").strip()}"'
        for i, r in enumerate(capped)
    )

    prompt = f"""You are a senior mobile-platform engineer performing a quick triage for a cluster of user reports.

CLUSTER: "{cluster.title}"
SEVERITY: {cluster.severity.upper()}
AFFECTED USERS: ~{cluster.review_count}
EVIDENCE ({len(capped)} of {cluster.review_count} reviews):

{review_lines}

Write a tight engineering triage note structured EXACTLY as below. Every section is mandatory.

**Root Cause Hypothesis**
1-2 sentences on the most likely technical root cause inferred from the reviews. Be specific — name the subsystem, API, or flow if reviewable.

**Affected Surface**
One line each: Client layer · Server/API layer · Data layer
Write "Likely unaffected" if not implicated. Do NOT leave any line blank.

**Reproduction Signal**
The clearest pattern (version, device, action sequence) that an engineer could use to reproduce.

**Recommended First Action**
The single most impactful next step for the on-call engineer (log query, feature flag, rollback, hotfix, etc.).

Rules: Every sentence must be traceable to at least one review above. Do not invent details not present in the data. If the cluster appears mislabelled (e.g. reviews are positive), state "Cluster may be mislabelled — reviews appear positive." and stop."""

    llm = get_llm_service()
    explanation = await llm.generate(prompt, max_tokens=500)

    return ClusterExplainResponse(
        cluster_id=cluster_id,
        title=cluster.title,
        explanation=explanation.strip(),
        reviews_used=len(capped),
        total_reviews=cluster.review_count or 0,
    )


@router.get("/clusters/{cluster_id}", response_model=ClusterDetailResponse)
async def get_cluster_details(
    cluster_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get detailed information about a cluster including full sample reviews.
    
    Args:
        cluster_id: Cluster ID
        session: Database session
    
    Returns:
        ClusterDetailResponse with full reviews
    """
    # Get cluster
    cluster = session.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    return ClusterDetailResponse(
        id=cluster.id,
        title=cluster.title,
        severity=cluster.severity,
        status=cluster.status,
        review_count=cluster.review_count,
        rca_title=cluster.rca_title,
        rca_hypothesis=cluster.rca_hypothesis,
        rca_steps=cluster.rca_steps,
        rca_fix=cluster.rca_fix,
        affected_versions=cluster.affected_versions,
        affected_devices=cluster.affected_devices,
        keywords=cluster.keywords,
        sample_reviews=cluster.sample_reviews,
        created_at=cluster.created_at.isoformat()
    )
