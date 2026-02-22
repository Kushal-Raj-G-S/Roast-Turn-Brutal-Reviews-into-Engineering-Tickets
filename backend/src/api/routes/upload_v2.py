"""
v2 API Routes - New Architecture
Uses dependency injection and domain-driven pipeline.
"""

import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.auth_supabase import get_current_user
from src.bootstrap import bootstrap_application, ApplicationConfig
from src.infrastructure.dependency_injection import DependencyContainer
from src.domain.entities import Upload as UploadEntity
from src.domain.value_objects import UploadId, TenantId, UploadStatus
from src.application.use_cases.bulk_processing_pipeline import BulkProcessingPipeline
from src.infrastructure.persistence.repositories import PostgresUploadRepository, PostgresClusterRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["v2-upload"])

# Global container (initialized at startup)
_container: Optional[DependencyContainer] = None


def get_container() -> DependencyContainer:
    """Get or create the global DI container."""
    global _container
    if _container is None:
        _container = bootstrap_application()
    return _container


async def get_upload_repository(session: AsyncSession = Depends(get_session)) -> PostgresUploadRepository:
    """Dependency for upload repository."""
    return PostgresUploadRepository(session)


async def get_cluster_repository(session: AsyncSession = Depends(get_session)) -> PostgresClusterRepository:
    """Dependency for cluster repository."""
    return PostgresClusterRepository(session)


@router.post("/upload")
async def upload_csv_v2(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    upload_repo: PostgresUploadRepository = Depends(get_upload_repository)
):
    """
    Upload CSV for bulk processing (v2 - New Architecture).
    
    This endpoint uses:
    - Domain-driven entities
    - Dependency injection
    - Event-driven processing
    - Pluggable services
    """
    try:
        user_id = UUID(current_user["id"])
        tenant_id = TenantId(user_id)
        
        # Validate file
        if not file.filename.endswith('.csv'):
            raise HTTPException(400, "File must be a CSV")
        
        # Read file
        content = await file.read()
        file_size = len(content)
        
        config = ApplicationConfig()
        max_size = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(400, f"File too large. Max size: {config.MAX_UPLOAD_SIZE_MB}MB")
        
        # Create upload directory if not exists
        upload_dir = Path(config.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Create domain entity
        upload_entity = UploadEntity(
            id=None,  # Will be assigned by repo
            tenant_id=tenant_id,
            user_id=user_id,
            filename=file.filename,
            file_size_bytes=file_size,
            file_path="",  # Will be set after saving
            status=UploadStatus.PENDING
        )
        
        # Save to database
        upload_entity = await upload_repo.create(upload_entity)
        
        # Save file
        file_path = upload_dir / f"{upload_entity.id.value}.csv"
        upload_entity.file_path = str(file_path)
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(
            f"Upload created (v2): {upload_entity.id.value} "
            f"by user {user_id} ({file_size} bytes)"
        )
        
        # Trigger background processing
        if background_tasks:
            background_tasks.add_task(
                process_upload_v2,
                upload_id=upload_entity.id,
                session=session
            )
        
        return {
            "upload_id": upload_entity.id.value,
            "filename": upload_entity.filename,
            "status": upload_entity.status.value,
            "message": "Upload queued for processing (v2 architecture)",
            "architecture": "v2"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed (v2): {e}", exc_info=True)
        raise HTTPException(500, f"Upload failed: {str(e)}")


async def process_upload_v2(upload_id: UploadId, session: AsyncSession):
    """
    Background task to process upload using the new pipeline.
    """
    try:
        logger.info(f"Starting v2 processing for upload {upload_id}")
        
        # Get container
        container = get_container()
        
        # Get repositories
        upload_repo = PostgresUploadRepository(session)
        cluster_repo = PostgresClusterRepository(session)
        
        # Get services from container
        embedding_provider = container.resolve(IEmbeddingProvider)
        clustering_engine = container.resolve(IClusteringEngine)
        ranking_strategy = container.resolve(IRankingStrategy)
        
        # Create pipeline
        pipeline = BulkProcessingPipeline(
            upload_repo=upload_repo,
            cluster_repo=cluster_repo,
            embedding_provider=embedding_provider,
            clustering_engine=clustering_engine,
            ranking_strategy=ranking_strategy,
            actionability_scorer=None,  # Optional
            ai_analysis_service=None,   # Optional
            file_storage=None,           # Optional
            event_bus=None               # Will be added later
        )
        
        # Execute pipeline
        metrics = await pipeline.execute(upload_id)
        
        logger.info(
            f"v2 processing complete for upload {upload_id}: "
            f"{metrics.clusters_created} clusters in {metrics.processing_time_ms}ms"
        )
    
    except Exception as e:
        logger.error(f"v2 processing failed for upload {upload_id}: {e}", exc_info=True)
        
        # Mark upload as failed
        try:
            upload = await upload_repo.get_by_id(upload_id)
            if upload:
                upload.fail(str(e))
                await upload_repo.update(upload)
        except Exception as update_error:
            logger.error(f"Failed to update upload status: {update_error}")


@router.get("/uploads/{upload_id}/progress")
async def get_upload_progress_v2(
    upload_id: int,
    current_user: dict = Depends(get_current_user),
    upload_repo: PostgresUploadRepository = Depends(get_upload_repository)
):
    """Get upload progress (v2)."""
    try:
        upload = await upload_repo.get_by_id(UploadId(upload_id))
        
        if not upload:
            raise HTTPException(404, "Upload not found")
        
        # Verify ownership
        user_id = UUID(current_user["id"])
        if upload.user_id != user_id:
            raise HTTPException(403, "Access denied")
        
        response = {
            "upload_id": upload.id.value,
            "status": upload.status.value,
            "filename": upload.filename,
            "architecture": "v2"
        }
        
        if upload.metrics:
            response.update({
                "total_reviews": upload.metrics.total_reviews,
                "filtered_noise": upload.metrics.filtered_noise,
                "processed_reviews": upload.metrics.actionable_reviews,
                "clusters_created": upload.metrics.clusters_created,
                "processing_time_ms": upload.metrics.processing_time_ms,
                "throughput": upload.metrics.throughput_reviews_per_sec
            })
        
        if upload.error_message:
            response["error"] = upload.error_message
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get progress: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@router.get("/uploads/{upload_id}/clusters")
async def get_upload_clusters_v2(
    upload_id: int,
    current_user: dict = Depends(get_current_user),
    upload_repo: PostgresUploadRepository = Depends(get_upload_repository),
    cluster_repo: PostgresClusterRepository = Depends(get_cluster_repository)
):
    """Get clusters for an upload (v2)."""
    try:
        # Verify upload exists and user owns it
        upload = await upload_repo.get_by_id(UploadId(upload_id))
        if not upload:
            raise HTTPException(404, "Upload not found")
        
        user_id = UUID(current_user["id"])
        if upload.user_id != user_id:
            raise HTTPException(403, "Access denied")
        
        # Get clusters
        clusters = await cluster_repo.list_by_upload(UploadId(upload_id))
        
        # Convert to response format
        clusters_response = []
        for cluster in clusters:
            clusters_response.append({
                "id": cluster.id.value,
                "title": cluster.title,
                "severity": cluster.severity.value,
                "status": cluster.status.value,
                "review_count": cluster.metrics.review_count if cluster.metrics else 0,
                "affected_versions": cluster.metrics.affected_versions if cluster.metrics else [],
                "affected_devices": cluster.metrics.affected_devices if cluster.metrics else [],
                "sample_reviews": cluster.sample_reviews[:3],  # Top 3
                "ai_analyzed": cluster.ai_analyzed,
                "rca_title": cluster.rca_title,
                "assigned_to": cluster.assigned_to,
                "created_at": cluster.created_at.isoformat()
            })
        
        return {
            "upload_id": upload_id,
            "clusters": clusters_response,
            "total_clusters": len(clusters),
            "architecture": "v2"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get clusters: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@router.get("/health")
async def health_check_v2():
    """Health check for v2 API."""
    try:
        container = get_container()
        config = container.resolve(ApplicationConfig)
        
        return {
            "status": "healthy",
            "version": "2.0.0",
            "architecture": "domain-driven",
            "features": {
                "ml_scoring": config.ML_SCORING_ENABLED,
                "ai_analysis": config.AI_ANALYSIS_ENABLED,
                "vector_backend": config.VECTOR_BACKEND,
                "message_queue": config.MESSAGE_QUEUE_BACKEND
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


# Import required for type hints
from src.domain.services import IEmbeddingProvider, IClusteringEngine, IRankingStrategy
