"""
PostgreSQL Repository Implementations
Concrete implementations of domain repository interfaces using SQLAlchemy.
"""

import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories import IUploadRepository, IClusterRepository
from ...domain.entities import Upload, Cluster
from ...domain.value_objects import UploadId, ClusterId, TenantId, UploadStatus, ClusterStatus

logger = logging.getLogger(__name__)


class PostgresUploadRepository(IUploadRepository):
    """PostgreSQL implementation of IUploadRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, upload: Upload) -> Upload:
        """Create a new upload."""
        from app.bulk_models import Upload as UploadModel
        
        # Map domain entity to SQLModel
        upload_model = UploadModel(
            id=upload.id.value if upload.id else None,
            user_id=upload.user_id,
            filename=upload.filename,
            file_size_bytes=upload.file_size_bytes,
            total_reviews=0,
            status=upload.status.value,
            created_at=upload.created_at
        )
        
        self.session.add(upload_model)
        await self.session.commit()
        await self.session.refresh(upload_model)
        
        # Map back to domain entity
        upload.id = UploadId(upload_model.id)
        
        logger.info(f"Created upload {upload.id}")
        return upload

    async def get_by_id(self, upload_id: UploadId) -> Optional[Upload]:
        """Get upload by ID."""
        from app.bulk_models import Upload as UploadModel
        
        stmt = select(UploadModel).where(UploadModel.id == upload_id.value)
        result = await self.session.execute(stmt)
        upload_model = result.scalar_one_or_none()
        
        if not upload_model:
            return None
        
        # Map to domain entity
        return self._to_domain(upload_model)

    async def update(self, upload: Upload) -> Upload:
        """Update an existing upload."""
        from app.bulk_models import Upload as UploadModel
        
        stmt = select(UploadModel).where(UploadModel.id == upload.id.value)
        result = await self.session.execute(stmt)
        upload_model = result.scalar_one_or_none()
        
        if not upload_model:
            raise ValueError(f"Upload {upload.id} not found")
        
        # Update fields
        upload_model.status = upload.status.value
        upload_model.error_message = upload.error_message
        upload_model.started_at = upload.started_at
        upload_model.completed_at = upload.completed_at
        
        if upload.metrics:
            upload_model.total_reviews = upload.metrics.total_reviews
            upload_model.filtered_noise = upload.metrics.filtered_noise
            upload_model.processed_reviews = upload.metrics.actionable_reviews
            upload_model.clusters_created = upload.metrics.clusters_created
            upload_model.ai_analyzed_count = upload.metrics.ai_analyzed_count
            upload_model.processing_time_ms = upload.metrics.processing_time_ms
        
        await self.session.commit()
        await self.session.refresh(upload_model)
        
        return self._to_domain(upload_model)

    async def list_by_tenant(
        self,
        tenant_id: TenantId,
        status: Optional[UploadStatus] = None,
        limit: int = 100
    ) -> List[Upload]:
        """List uploads for a tenant."""
        from app.bulk_models import Upload as UploadModel
        
        stmt = select(UploadModel).where(
            UploadModel.user_id == tenant_id.value
        )
        
        if status:
            stmt = stmt.where(UploadModel.status == status.value)
        
        stmt = stmt.order_by(UploadModel.created_at.desc()).limit(limit)
        
        result = await self.session.execute(stmt)
        upload_models = result.scalars().all()
        
        return [self._to_domain(m) for m in upload_models]

    async def count_pending_by_tenant(self, tenant_id: TenantId) -> int:
        """Count pending uploads for a tenant."""
        from app.bulk_models import Upload as UploadModel
        
        stmt = select(func.count()).where(
            and_(
                UploadModel.user_id == tenant_id.value,
                UploadModel.status == UploadStatus.PENDING.value
            )
        )
        
        result = await self.session.execute(stmt)
        return result.scalar()

    async def find_pending(self, limit: int = 1) -> List[Upload]:
        """Find pending uploads for processing."""
        from app.bulk_models import Upload as UploadModel
        
        stmt = select(UploadModel).where(
            UploadModel.status == UploadStatus.PENDING.value
        ).order_by(UploadModel.created_at).limit(limit)
        
        result = await self.session.execute(stmt)
        upload_models = result.scalars().all()
        
        return [self._to_domain(m) for m in upload_models]

    def _to_domain(self, model) -> Upload:
        """Convert SQLModel to domain entity."""
        from ...domain.value_objects import ProcessingMetrics
        
        metrics = None
        if model.processing_time_ms:
            metrics = ProcessingMetrics(
                total_reviews=model.total_reviews or 0,
                filtered_noise=model.filtered_noise or 0,
                actionable_reviews=model.processed_reviews or 0,
                clusters_created=model.clusters_created or 0,
                ai_analyzed_count=model.ai_analyzed_count or 0,
                processing_time_ms=model.processing_time_ms,
                stage_timings={},
                memory_peak_mb=0.0,
                cpu_utilization=0.0
            )
        
        return Upload(
            id=UploadId(model.id),
            tenant_id=TenantId(model.user_id),
            user_id=model.user_id,
            filename=model.filename,
            file_size_bytes=model.file_size_bytes or 0,
            file_path=f"./uploads/{model.id}.csv",
            status=UploadStatus(model.status),
            error_message=model.error_message,
            metrics=metrics,
            created_at=model.created_at,
            started_at=getattr(model, 'started_at', None),
            completed_at=model.completed_at
        )


class PostgresClusterRepository(IClusterRepository):
    """PostgreSQL implementation of IClusterRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, cluster: Cluster) -> Cluster:
        """Create a new cluster."""
        clusters = await self.create_batch([cluster])
        return clusters[0]

    async def create_batch(self, clusters: List[Cluster]) -> List[Cluster]:
        """Batch create clusters (optimized)."""
        from app.bulk_models import Cluster as ClusterModel
        
        cluster_models = []
        for cluster in clusters:
            model = ClusterModel(
                upload_id=cluster.upload_id.value,
                cluster_uuid=cluster.id.value,
                title=cluster.title,
                severity=cluster.severity.value,
                status=cluster.status.value,
                rca_title=cluster.rca_title,
                rca_hypothesis=cluster.rca_hypothesis,
                rca_steps=cluster.rca_steps,
                rca_fix=cluster.rca_fix,
                ai_analyzed=cluster.ai_analyzed,
                affected_versions=cluster.metrics.affected_versions if cluster.metrics else [],
                affected_devices=cluster.metrics.affected_devices if cluster.metrics else [],
                keywords=cluster.metrics.keywords if cluster.metrics else [],
                sample_reviews=cluster.sample_reviews,
                review_count=cluster.metrics.review_count if cluster.metrics else 0,
                assigned_to=cluster.assigned_to,
                assigned_at=cluster.assigned_at,
                created_at=cluster.created_at,
                updated_at=cluster.updated_at,
                resolved_at=cluster.resolved_at
            )
            cluster_models.append(model)
        
        self.session.add_all(cluster_models)
        await self.session.commit()
        
        logger.info(f"Created {len(clusters)} clusters in batch")
        return clusters

    async def get_by_id(self, cluster_id: ClusterId) -> Optional[Cluster]:
        """Get cluster by ID."""
        from app.bulk_models import Cluster as ClusterModel
        
        stmt = select(ClusterModel).where(ClusterModel.cluster_uuid == cluster_id.value)
        result = await self.session.execute(stmt)
        cluster_model = result.scalar_one_or_none()
        
        if not cluster_model:
            return None
        
        return self._to_domain(cluster_model)

    async def update(self, cluster: Cluster) -> Cluster:
        """Update an existing cluster."""
        from app.bulk_models import Cluster as ClusterModel
        
        stmt = select(ClusterModel).where(ClusterModel.cluster_uuid == cluster.id.value)
        result = await self.session.execute(stmt)
        cluster_model = result.scalar_one_or_none()
        
        if not cluster_model:
            raise ValueError(f"Cluster {cluster.id} not found")
        
        # Update fields
        cluster_model.status = cluster.status.value
        cluster_model.assigned_to = cluster.assigned_to
        cluster_model.assigned_at = cluster.assigned_at
        cluster_model.resolved_at = cluster.resolved_at
        cluster_model.updated_at = datetime.utcnow()
        
        if cluster.ai_analyzed:
            cluster_model.rca_title = cluster.rca_title
            cluster_model.rca_hypothesis = cluster.rca_hypothesis
            cluster_model.rca_steps = cluster.rca_steps
            cluster_model.rca_fix = cluster.rca_fix
            cluster_model.ai_analyzed = True
        
        await self.session.commit()
        await self.session.refresh(cluster_model)
        
        return self._to_domain(cluster_model)

    async def list_by_upload(
        self,
        upload_id: UploadId,
        limit: int = 1000
    ) -> List[Cluster]:
        """List clusters for an upload."""
        from app.bulk_models import Cluster as ClusterModel
        
        stmt = select(ClusterModel).where(
            ClusterModel.upload_id == upload_id.value
        ).order_by(ClusterModel.review_count.desc()).limit(limit)
        
        result = await self.session.execute(stmt)
        cluster_models = result.scalars().all()
        
        return [self._to_domain(m) for m in cluster_models]

    async def list_by_tenant(
        self,
        tenant_id: TenantId,
        status: Optional[ClusterStatus] = None,
        limit: int = 100
    ) -> List[Cluster]:
        """List clusters for a tenant."""
        from app.bulk_models import Cluster as ClusterModel
        from app.bulk_models import Upload as UploadModel
        
        # Join with uploads to filter by tenant
        stmt = select(ClusterModel).join(
            UploadModel,
            ClusterModel.upload_id == UploadModel.id
        ).where(
            UploadModel.user_id == tenant_id.value
        )
        
        if status:
            stmt = stmt.where(ClusterModel.status == status.value)
        
        stmt = stmt.order_by(ClusterModel.created_at.desc()).limit(limit)
        
        result = await self.session.execute(stmt)
        cluster_models = result.scalars().all()
        
        return [self._to_domain(m) for m in cluster_models]

    async def search_similar(
        self,
        tenant_id: TenantId,
        query_embedding: List[float],
        threshold: float = 0.8,
        limit: int = 10
    ) -> List[Cluster]:
        """Find similar clusters using vector search."""
        # TODO: Implement vector similarity search
        # For now, return empty list
        logger.warning("Vector similarity search not yet implemented")
        return []

    def _to_domain(self, model) -> Cluster:
        """Convert SQLModel to domain entity."""
        from ...domain.value_objects import ClusterMetrics, Severity, ClusterStatus
        from ...domain.entities import Cluster
        
        metrics = ClusterMetrics(
            review_count=model.review_count,
            avg_rating=0.0,  # TODO: Calculate from sample reviews
            severity_distribution={model.severity: model.review_count},
            affected_versions=model.affected_versions or [],
            affected_devices=model.affected_devices or [],
            time_range=(model.created_at, model.created_at),
            keywords=model.keywords or []
        )
        
        # Get tenant_id from upload (need to join)
        # For now, use a placeholder
        tenant_id = TenantId(model.upload_id)  # This needs proper implementation
        
        return Cluster(
            id=ClusterId(model.cluster_uuid),
            upload_id=UploadId(model.upload_id),
            tenant_id=tenant_id,
            title=model.title,
            severity=Severity(model.severity),
            status=ClusterStatus(model.status),
            rca_title=model.rca_title,
            rca_hypothesis=model.rca_hypothesis,
            rca_steps=model.rca_steps,
            rca_fix=model.rca_fix,
            ai_analyzed=model.ai_analyzed or False,
            metrics=metrics,
            sample_reviews=model.sample_reviews or [],
            assigned_to=model.assigned_to,
            assigned_at=model.assigned_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            resolved_at=model.resolved_at
        )
