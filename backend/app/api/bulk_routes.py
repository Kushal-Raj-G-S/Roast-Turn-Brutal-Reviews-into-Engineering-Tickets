"""
FastAPI routes for bulk upload and job management (optimized system).
Uses 'uploads' table with INTEGER id.
"""

import asyncio
import logging
import math
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import numpy as np

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.models.bulk_models import Upload, Cluster, PushSubscription
from app.models.usage_models import get_monthly_usage, increment_upload_count
from app.core.config import config
from app.core.plans import get_limits, uploads_unlimited, reviews_unlimited
from app.database.auth_supabase import get_current_user
from app.models.models_supabase import Profile
from app.core.shadow_deployment import schedule_shadow_deployment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["bulk"])


# ---------------------------------------------------------------------------
# Release-bisected regressions
# ---------------------------------------------------------------------------
# `affected_versions` on Cluster is never populated by the live pipeline, but
# each sample review already carries its own `version` (captured from the
# CSV's app-version column, when the upload has one -- most don't). Rather
# than a pipeline/schema change, this derives a best-effort "which version
# did this start showing up in" directly from sample_reviews on read.

def _parse_version_tuple(v: str) -> Optional[tuple]:
    """'v4.2.1' / '4.2' -> (4, 2, 1) / (4, 2). None if it doesn't look like a version."""
    import re
    m = re.findall(r"\d+", v or "")
    if not m:
        return None
    return tuple(int(x) for x in m[:4])


def bisect_versions(sample_reviews: Optional[list[dict]]) -> Optional[dict]:
    if not sample_reviews:
        return None

    versions = [r.get("version") for r in sample_reviews if r.get("version")]
    if not versions:
        return None

    from collections import Counter
    counts = Counter(versions)

    parsed = [(v, t) for v in set(versions) if (t := _parse_version_tuple(v)) is not None]
    earliest = min(parsed, key=lambda x: x[1])[0] if parsed else None

    return {
        "earliest_version": earliest,
        "most_common_version": counts.most_common(1)[0][0],
        "distinct_versions": len(counts),
        "version_counts": dict(counts.most_common(5)),
    }


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
    regression_detected: Optional[bool] = None
    regression_of_title: Optional[str] = None
    regression_confidence: Optional[float] = None
    regression_match_method: Optional[str] = None


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
    ai_metadata: Optional[dict] = None
    created_at: str
    regression_detected: Optional[bool] = None
    regression_of_title: Optional[str] = None
    regression_confidence: Optional[float] = None
    regression_match_method: Optional[str] = None
    regression_resolved_at: Optional[str] = None
    version_bisect: Optional[dict] = None


# Dependency to get DB session
def get_db_session():
    """Get database session for dependency injection with proper error handling."""
    from app.api.bulk_api import get_engine_instance
    engine = get_engine_instance()
    if not engine:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    session = Session(engine)
    try:
        yield session
    except Exception as e:
        logger.error(f"Database session error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


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

        # ── Plan enforcement ──────────────────────────────────────────────────
        plan = getattr(user, "plan", "free") or "free"
        limits = get_limits(plan)
        
        logger.info(f"🔍 Plan enforcement check for user {str(user.id)[:8]}... | plan={plan} | limit={limits['uploads_per_month']}")

        # 1. Monthly upload count check
        if not uploads_unlimited(plan):
            used_this_month = get_monthly_usage(session, str(user.id))
            logger.info(f"📊 Monthly usage: {used_this_month}/{limits['uploads_per_month']} | unlimited={uploads_unlimited(plan)}")
            
            if used_this_month >= limits["uploads_per_month"]:
                logger.warning(f"⛔ LIMIT REACHED: {used_this_month} >= {limits['uploads_per_month']}")
                raise HTTPException(
                    status_code=402,
                    detail={
                        "code": "UPLOAD_LIMIT_REACHED",
                        "message": f"You've used all {limits['uploads_per_month']} uploads for this month on the {limits['label']} plan.",
                        "plan": plan,
                        "uploads_used": used_this_month,
                        "uploads_limit": limits["uploads_per_month"],
                    },
                )
            else:
                logger.info(f"✅ Under limit: {used_this_month} < {limits['uploads_per_month']}")
        # ─────────────────────────────────────────────────────────────────────
        
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

        # 2. Row-count (review) — computed unconditionally now (it's just a
        # byte scan, already cheap) so it can be stored on the upload record
        # below. Previously this was only computed for capped plans purely
        # for the limit check, then thrown away — meaning total_reviews was
        # None for the entire multi-minute processing window regardless of
        # plan, and the frontend had no real number to scale a progress
        # estimate against until the very end.
        file.file.seek(0)
        raw = await file.read()
        file.file.seek(0)
        row_count = raw.count(b"\n")  # fast approximation (header not counted)

        if not reviews_unlimited(plan):
            logger.info(f"📝 Review count check: {row_count:,} rows | limit={limits['max_reviews']:,}")

            if row_count > limits["max_reviews"]:
                logger.warning(f"⛔ REVIEW LIMIT EXCEEDED: {row_count:,} > {limits['max_reviews']:,}")
                raise HTTPException(
                    status_code=402,
                    detail={
                        "code": "REVIEW_LIMIT_EXCEEDED",
                        "message": f"File contains ~{row_count:,} rows but your {limits['label']} plan allows {limits['max_reviews']:,} reviews per upload.",
                        "plan": plan,
                        "row_count": row_count,
                        "reviews_limit": limits["max_reviews"],
                    },
                )
            else:
                logger.info(f"✅ Review count OK: {row_count:,} <= {limits['max_reviews']:,}")

        # Create upload directory
        config.ensure_upload_dir()

        # Create upload record with authenticated user
        # Use status='shadow_processing' so worker ignores it (orchestrator handles these)
        # total_reviews is set immediately from the pre-flight row count (an
        # approximation — actual kept/processed counts land later) so the
        # upload page's progress estimate has a real number to scale against
        # from its very first poll, instead of only learning the size once
        # processing has already finished.
        upload = Upload(
            user_id=user.id,
            filename=file.filename,
            file_size_bytes=file_size_bytes,
            total_reviews=row_count,
            status="shadow_processing"  # Orchestrator-managed, worker ignores
        )
        
        session.add(upload)
        session.commit()
        session.refresh(upload)
        
        # 🔥 INCREMENT USAGE COUNTER (after successful upload creation)
        increment_upload_count(session, str(user.id))
        
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
            created_at=c.created_at.isoformat(),
            regression_detected=c.regression_detected,
            regression_of_title=c.regression_of_title,
            regression_confidence=c.regression_confidence,
            regression_match_method=c.regression_match_method,
        )
        for c in clusters
    ]


# ---------------------------------------------------------------------------
# Confidence-weighted triage queue
# ---------------------------------------------------------------------------
# Severity alone is a coarse, static signal. This fuses four independently-
# computed things the pipeline already produces -- severity, RAGAS
# faithfulness (is the RCA actually supported by evidence?), the fix-
# verification regression signal above, and volume (log-scaled so one huge
# cluster can't drown out everything else) -- into one ranked "fix this
# first" score, instead of engineers re-deriving that priority by eye from
# four separate badges.

_SEVERITY_WEIGHT = {"critical": 100.0, "high": 70.0, "medium": 40.0, "low": 15.0}


def _priority_score(c: Cluster) -> float:
    severity_weight = _SEVERITY_WEIGHT.get((c.severity or "").lower(), 20.0)

    faithfulness = 0.5  # neutral default when no AI eval has run yet
    if isinstance(c.ai_metadata, dict):
        eval_scores = c.ai_metadata.get("eval_scores") or {}
        if isinstance(eval_scores.get("faithfulness"), (int, float)):
            faithfulness = float(eval_scores["faithfulness"])

    regression_boost = 0.0
    if c.regression_detected:
        regression_boost = 30.0 * (c.regression_confidence if c.regression_confidence is not None else 0.5)

    velocity = math.log1p(max(c.review_count or 0, 0)) * 5.0

    return round(severity_weight + faithfulness * 20.0 + regression_boost + velocity, 2)


class TriageClusterResponse(ClusterResponse):
    """ClusterResponse plus the fused priority score and its components."""
    priority_score: float
    priority_breakdown: dict


class TriageQueueResponse(BaseModel):
    upload_id: int
    clusters: list[TriageClusterResponse]


@router.get("/uploads/{upload_id}/triage-queue", response_model=TriageQueueResponse)
async def get_triage_queue(
    upload_id: int,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    """
    All clusters for this upload, ranked by a single fused priority score
    (severity + AI-evidence faithfulness + fix-verification regression
    signal + review volume) instead of severity alone.
    """
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if str(upload.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized to view this upload")

    clusters = session.exec(
        select(Cluster).where(Cluster.upload_id == upload_id)
    ).all()

    scored = []
    for c in clusters:
        score = _priority_score(c)
        faithfulness = 0.5
        if isinstance(c.ai_metadata, dict):
            eval_scores = c.ai_metadata.get("eval_scores") or {}
            if isinstance(eval_scores.get("faithfulness"), (int, float)):
                faithfulness = float(eval_scores["faithfulness"])
        scored.append(
            TriageClusterResponse(
                id=c.id,
                title=c.title,
                severity=c.severity,
                status=c.status,
                review_count=c.review_count,
                rca_title=c.rca_title,
                rca_hypothesis=c.rca_hypothesis,
                created_at=c.created_at.isoformat(),
                regression_detected=c.regression_detected,
                regression_of_title=c.regression_of_title,
                regression_confidence=c.regression_confidence,
                regression_match_method=c.regression_match_method,
                priority_score=score,
                priority_breakdown={
                    "severity_weight": _SEVERITY_WEIGHT.get((c.severity or "").lower(), 20.0),
                    "faithfulness": faithfulness,
                    "regression_boost": 30.0 * (c.regression_confidence or 0.5) if c.regression_detected else 0.0,
                    "velocity": round(math.log1p(max(c.review_count or 0, 0)) * 5.0, 2),
                },
            )
        )

    scored.sort(key=lambda x: x.priority_score, reverse=True)
    return TriageQueueResponse(upload_id=upload_id, clusters=scored)


# ---------------------------------------------------------------------------
# Cross-platform bug fusion
# ---------------------------------------------------------------------------
# There's no structured platform column in the pipeline (see NEW_ARCHITECTURE_
# CHANGES.md §14/exploration) -- platform is inferred two ways and combined:
# explanation_pregenerate._detect_platform scans the cluster TITLE, which
# almost never mentions a platform (titles summarize the bug, not the
# device); each review's own `device` field (populated by bulk_processor.py
# from free-text device-keyword matching, e.g. "Samsung"/"iPhone") is a far
# better signal and was sitting unused -- a live-data survey found it
# populated with real iOS signal (Ios/Iphone) on clusters the title-only
# detector had zero chance of ever catching (see NEW_ARCHITECTURE_CHANGES.md
# §17). Either signal is enough to tag a cluster; this stays best-effort --
# flags candidates for a human to confirm, not a guaranteed fusion.

_ANDROID_DEVICE_WORDS = {"samsung", "pixel", "oneplus", "xiaomi", "huawei", "oppo", "vivo", "realme", "nokia", "galaxy", "android"}
_IOS_DEVICE_WORDS = {"iphone", "ios", "ipad"}


def _detect_platform_from_reviews(cluster: Cluster) -> str:
    has_android = False
    has_ios = False
    for r in (cluster.sample_reviews or []):
        d = (r.get("device") or "").strip().lower()
        if d in _ANDROID_DEVICE_WORDS:
            has_android = True
        elif d in _IOS_DEVICE_WORDS:
            has_ios = True
    if has_android and has_ios:
        return "both"
    if has_android:
        return "android"
    if has_ios:
        return "ios"
    return "unknown"


def _detect_platform_combined(cluster: Cluster) -> str:
    """Union of the title-based and review-device-based signals."""
    from app.services.explanation_pregenerate import _detect_platform

    platforms = {_detect_platform(cluster), _detect_platform_from_reviews(cluster)}
    platforms.discard("unknown")
    if len(platforms) > 1 or "both" in platforms:
        return "both"
    if platforms:
        return platforms.pop()
    return "unknown"


_CROSS_PLATFORM_THRESHOLD = 0.60


class CrossPlatformMatch(BaseModel):
    android_cluster_id: int
    android_title: str
    ios_cluster_id: int
    ios_title: str
    confidence: float


class CrossPlatformMatchesResponse(BaseModel):
    upload_id: int
    matches: list[CrossPlatformMatch]


@router.get("/uploads/{upload_id}/cross-platform-matches", response_model=CrossPlatformMatchesResponse)
async def get_cross_platform_matches(
    upload_id: int,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    """
    Best-effort: flags cluster pairs in this upload that look like the same
    underlying bug reported separately on Android and iOS, so a shared-
    backend issue doesn't get triaged twice as two unrelated client bugs.
    """
    upload = session.get(Upload, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if str(upload.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized to view this upload")

    clusters = session.exec(select(Cluster).where(Cluster.upload_id == upload_id)).all()
    android = [c for c in clusters if _detect_platform_combined(c) in ("android", "both")]
    ios = [c for c in clusters if _detect_platform_combined(c) in ("ios", "both")]

    if not android or not ios:
        return CrossPlatformMatchesResponse(upload_id=upload_id, matches=[])

    try:
        from app.services.bulk_embedding import EmbeddingBackend
        backend = EmbeddingBackend()
        texts = [f"{c.title} {' '.join(c.keywords or [])}" for c in android] + \
                [f"{c.title} {' '.join(c.keywords or [])}" for c in ios]
        vecs = backend.encode_batch(texts)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
        android_vecs = vecs[: len(android)]
        ios_vecs = vecs[len(android):]
        sim = android_vecs @ ios_vecs.T
    except Exception as e:
        logger.warning(f"Cross-platform matching unavailable ({e})")
        return CrossPlatformMatchesResponse(upload_id=upload_id, matches=[])

    matches = []
    for i, ac in enumerate(android):
        for j, ic in enumerate(ios):
            if ac.id == ic.id:
                # A cluster tagged "both" (has device evidence for android
                # AND ios) appears in both lists -- without this it would
                # trivially "match" itself at cosine similarity 1.0.
                continue
            score = float(sim[i, j])
            if score >= _CROSS_PLATFORM_THRESHOLD:
                matches.append(CrossPlatformMatch(
                    android_cluster_id=ac.id,
                    android_title=ac.title,
                    ios_cluster_id=ic.id,
                    ios_title=ic.title,
                    confidence=round(score, 3),
                ))

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return CrossPlatformMatchesResponse(upload_id=upload_id, matches=matches)


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


class PlaygroundRequest(BaseModel):
    """Ad-hoc LLM experimentation request — never persisted to the cluster."""
    prompt: str
    model: Optional[str] = None
    temperature: Optional[float] = 0.2
    max_tokens: Optional[int] = 600


class PlaygroundResponse(BaseModel):
    output: str
    model_used: str
    persona_used: Optional[str] = None
    temperature_used: float


@router.post("/clusters/{cluster_id}/playground", response_model=PlaygroundResponse)
async def playground_run(
    cluster_id: int,
    payload: PlaygroundRequest,
    session: Session = Depends(get_db_session)
):
    """
    Live prompt experimentation for the AI Debug Center. Always calls the
    one configured, verified-fast NVIDIA model (never `payload.model`
    directly) -- most model ids on NVIDIA's public catalog aren't actually
    invokable on every account/key, and routing real requests to a picked
    id meant every "model swap" risked a 404/410 or a long hang instead of
    an answer. `payload.model` is instead passed through as a style persona
    that flavors the system prompt, so picking a different "model" still
    changes the output's voice without the reliability cost. Temperature is
    applied for real. Nothing here is written back to the cluster's stored
    rca_hypothesis/ai_metadata, so it's safe to experiment freely.
    """
    cluster = session.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if not payload.prompt or not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    temperature = 0.2 if payload.temperature is None else max(0.0, min(1.0, payload.temperature))
    max_tokens = max(1, min(payload.max_tokens or 600, 1000))
    persona = payload.model.strip() if payload.model and payload.model.strip() else None

    from app.services.llm_service import get_llm_service
    llm = get_llm_service()
    output = await llm.generate(
        payload.prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        persona_label=persona,
    )

    return PlaygroundResponse(
        output=output.strip(),
        model_used=llm.model,
        persona_used=persona,
        temperature_used=temperature,
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
    try:
        # Get cluster with timeout protection
        cluster = session.get(Cluster, cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        
        # Build response with safe field access
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
            affected_versions=cluster.affected_versions or [],
            affected_devices=cluster.affected_devices or [],
            keywords=cluster.keywords or [],
            sample_reviews=cluster.sample_reviews or [],
            ai_metadata=cluster.ai_metadata,
            created_at=cluster.created_at.isoformat(),
            regression_detected=cluster.regression_detected,
            regression_of_title=cluster.regression_of_title,
            regression_confidence=cluster.regression_confidence,
            regression_match_method=cluster.regression_match_method,
            regression_resolved_at=cluster.regression_resolved_at.isoformat() if cluster.regression_resolved_at else None,
            version_bisect=bisect_versions(cluster.sample_reviews),
        )
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Database error fetching cluster {cluster_id}: {e}")
        # Clean up session on error to prevent connection leaks
        session.rollback()
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")


# ---------------------------------------------------------------------------
# Cluster status updates
# ---------------------------------------------------------------------------
# Was entirely missing until now -- KanbanBoard.tsx rendered fresh/fixing/
# resolved columns but had no drag-persist logic or API calls at all, and no
# backend endpoint existed to change a cluster's status. That's a genuine
# blocker for the fix-verification loop (section 15.1/16.5): the whole
# feature is premised on users marking clusters resolved, which was
# previously only possible by editing the database directly.

_VALID_CLUSTER_STATUSES = {"fresh_roast", "assigned", "in_progress", "resolved", "wont_fix"}


class ClusterStatusUpdate(BaseModel):
    status: str


class ClusterStatusResponse(BaseModel):
    id: int
    status: str
    resolved_at: Optional[str] = None


@router.patch("/clusters/{cluster_id}/status", response_model=ClusterStatusResponse)
async def update_cluster_status(
    cluster_id: int,
    body: ClusterStatusUpdate,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    """
    Move a cluster between fresh_roast / assigned / in_progress / resolved /
    wont_fix. Setting resolved_at happens here, not client-side, so it's
    always the server's clock -- the fix-verification loop's confidence and
    "days since resolved" math both depend on this being trustworthy.
    """
    if body.status not in _VALID_CLUSTER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of: {', '.join(sorted(_VALID_CLUSTER_STATUSES))}",
        )

    cluster = session.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    upload = session.get(Upload, cluster.upload_id)
    if not upload or str(upload.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized to update this cluster")

    was_resolved = cluster.status == "resolved"
    cluster.status = body.status
    cluster.updated_at = datetime.now(timezone.utc)

    if body.status == "resolved" and not was_resolved:
        cluster.resolved_at = datetime.now(timezone.utc)
    elif body.status != "resolved" and was_resolved:
        # Reopened -- this cluster is no longer a valid "resolved" baseline
        # for the regression detector to compare future uploads against.
        cluster.resolved_at = None

    session.add(cluster)
    session.commit()
    session.refresh(cluster)

    return ClusterStatusResponse(
        id=cluster.id,
        status=cluster.status,
        resolved_at=cluster.resolved_at.isoformat() if cluster.resolved_at else None,
    )


@router.get("/health/db", response_model=dict)
async def health_check_db():
    """
    Check database connection pool health for monitoring and diagnostics.
    
    Returns:
        Database connection pool status
    """
    from app.api.bulk_api import get_engine_instance
    
    try:
        engine = get_engine_instance()
        if not engine:
            return {"status": "error", "message": "Database engine not initialized"}
        
        pool = engine.pool
        return {
            "status": "ok",
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "checked_in": pool.checkedin(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid()
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Proactive alerting settings
# ---------------------------------------------------------------------------

class AlertSettingsResponse(BaseModel):
    alert_webhook_url: Optional[str] = None
    alerts_enabled: bool = True
    email_alerts_enabled: bool = True
    weekly_digest_enabled: bool = True


class AlertSettingsUpdate(BaseModel):
    alert_webhook_url: Optional[str] = None
    alerts_enabled: Optional[bool] = None
    email_alerts_enabled: Optional[bool] = None
    weekly_digest_enabled: Optional[bool] = None


@router.get("/settings/alerts", response_model=AlertSettingsResponse)
async def get_alert_settings(user: Profile = Depends(get_current_user)):
    return AlertSettingsResponse(
        alert_webhook_url=user.alert_webhook_url,
        alerts_enabled=bool(user.alerts_enabled) if user.alerts_enabled is not None else True,
        email_alerts_enabled=bool(user.email_alerts_enabled) if user.email_alerts_enabled is not None else True,
        weekly_digest_enabled=bool(user.weekly_digest_enabled) if user.weekly_digest_enabled is not None else True,
    )


@router.put("/settings/alerts", response_model=AlertSettingsResponse)
async def update_alert_settings(
    body: AlertSettingsUpdate,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    profile = session.get(Profile, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if body.alert_webhook_url is not None:
        url = body.alert_webhook_url.strip()
        if url and not (url.startswith("https://hooks.slack.com/") or url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")):
            raise HTTPException(status_code=400, detail="Must be a Slack incoming-webhook or Discord webhook URL")
        profile.alert_webhook_url = url or None
    if body.alerts_enabled is not None:
        profile.alerts_enabled = body.alerts_enabled
    if body.email_alerts_enabled is not None:
        profile.email_alerts_enabled = body.email_alerts_enabled
    if body.weekly_digest_enabled is not None:
        profile.weekly_digest_enabled = body.weekly_digest_enabled

    session.add(profile)
    session.commit()
    session.refresh(profile)

    return AlertSettingsResponse(
        alert_webhook_url=profile.alert_webhook_url,
        alerts_enabled=bool(profile.alerts_enabled),
        email_alerts_enabled=bool(profile.email_alerts_enabled),
        weekly_digest_enabled=bool(profile.weekly_digest_enabled),
    )


class TestStubResponse(BaseModel):
    cluster_id: int
    code: str


@router.post("/clusters/{cluster_id}/test-stub", response_model=TestStubResponse)
async def generate_cluster_test_stub(
    cluster_id: int,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    """
    Generate a runnable Playwright repro-test skeleton from this cluster's RCA.

    Auth + ownership are enforced here (unlike the read-only cluster
    endpoints) because every call spends a real LLM request against the
    shared NVIDIA rate limit -- an unauthenticated version would let anyone
    burn the whole account's throughput by looping over cluster ids.
    """
    from app.services.ai.repro_stub_generator import generate_test_stub

    cluster = session.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    upload = session.get(Upload, cluster.upload_id)
    if not upload or str(upload.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized to use this cluster")

    try:
        code = await generate_test_stub(cluster)
    except Exception as e:
        logger.warning(f"Test stub generation failed for cluster {cluster_id}: {e}")
        raise HTTPException(status_code=502, detail="Test stub generation failed — try again in a moment")

    return TestStubResponse(cluster_id=cluster_id, code=code)


@router.post("/settings/alerts/test")
async def test_alert_webhook(user: Profile = Depends(get_current_user)):
    from app.services import notifications

    if not user.alert_webhook_url:
        raise HTTPException(status_code=400, detail="No webhook URL configured yet")

    ok = await notifications.send_alert(
        user.alert_webhook_url,
        "🔥 Roast test alert — if you can see this, your webhook is wired up correctly.",
    )
    if not ok:
        raise HTTPException(status_code=502, detail="Webhook did not accept the test message — double-check the URL")
    return {"status": "sent"}


@router.post("/settings/alerts/test-email")
async def test_alert_email(user: Profile = Depends(get_current_user)):
    from app.services import notifications

    ok, err = await notifications.send_email(
        user.email,
        "🔥 Roast test email",
        notifications._email_shell(
            "<p>If you can see this, email alerts are wired up correctly.</p>"
        ),
    )
    if not ok:
        raise HTTPException(status_code=502, detail=err or "Email did not send")
    return {"status": "sent"}


# ---------------------------------------------------------------------------
# Web Push (browser push notifications) -- self-generated VAPID keys, no
# third-party push service. One row per browser/device in push_subscriptions;
# a user can have push enabled on more than one browser at once.
# ---------------------------------------------------------------------------

class PushSubscriptionBody(BaseModel):
    endpoint: str
    keys: dict  # {"p256dh": ..., "auth": ...} -- the shape PushManager.subscribe() returns


@router.post("/push/subscribe")
async def subscribe_push(
    body: PushSubscriptionBody,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    if "p256dh" not in body.keys or "auth" not in body.keys:
        raise HTTPException(status_code=400, detail="Malformed subscription -- missing p256dh/auth keys")

    existing = session.exec(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    ).first()
    if existing:
        # Re-subscribing (e.g. the browser rotated the endpoint) -- update in
        # place rather than erroring on the unique constraint.
        existing.user_id = user.id
        existing.p256dh = body.keys["p256dh"]
        existing.auth = body.keys["auth"]
        session.add(existing)
    else:
        session.add(PushSubscription(
            user_id=user.id, endpoint=body.endpoint,
            p256dh=body.keys["p256dh"], auth=body.keys["auth"],
        ))
    session.commit()
    return {"status": "subscribed"}


class PushUnsubscribeBody(BaseModel):
    endpoint: str


@router.post("/push/unsubscribe")
async def unsubscribe_push(
    body: PushUnsubscribeBody,
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    sub = session.exec(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == user.id,
        )
    ).first()
    if sub:
        session.delete(sub)
        session.commit()
    return {"status": "unsubscribed"}


@router.get("/push/status")
async def push_status(
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    """Whether THIS browser is subscribed isn't knowable server-side (the
    endpoint lives in the browser's IndexedDB via the service worker
    registration) -- this just reports whether the account has ANY
    subscription at all, for a simple on/off read in Settings."""
    count = len(session.exec(select(PushSubscription).where(PushSubscription.user_id == user.id)).all())
    return {"subscribed_devices": count}


@router.post("/push/test")
async def test_push(
    session: Session = Depends(get_db_session),
    user: Profile = Depends(get_current_user),
):
    from app.services import notifications

    subs = session.exec(select(PushSubscription).where(PushSubscription.user_id == user.id)).all()
    if not subs:
        raise HTTPException(status_code=400, detail="No push subscription on this account yet -- enable push notifications first")

    sent = 0
    for sub in subs:
        ok, is_gone = notifications.send_push(
            {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            "Roast test notification",
            "If you can see this, browser push is wired up correctly.",
            url=f"{config.FRONTEND_URL}/dashboard",
        )
        if ok:
            sent += 1
        elif is_gone:
            session.delete(sub)
    session.commit()

    if sent == 0:
        raise HTTPException(status_code=502, detail="Push failed to send to every subscribed device")
    return {"status": "sent", "devices": sent}
