"""
Domain Events - Events that represent something interesting that happened in the domain.
Used for event-driven architecture and async processing.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from .value_objects import UploadId, ClusterId, TenantId, ProcessingStage, Severity


class EventType(str, Enum):
    """Types of domain events."""
    # Upload events
    UPLOAD_CREATED = "upload.created"
    UPLOAD_STARTED = "upload.started"
    UPLOAD_STAGE_COMPLETED = "upload.stage_completed"
    UPLOAD_COMPLETED = "upload.completed"
    UPLOAD_FAILED = "upload.failed"
    UPLOAD_CANCELLED = "upload.cancelled"
    
    # Cluster events
    CLUSTER_CREATED = "cluster.created"
    CLUSTER_UPDATED = "cluster.updated"
    CLUSTER_ASSIGNED = "cluster.assigned"
    CLUSTER_RESOLVED = "cluster.resolved"
    CLUSTER_MERGED = "cluster.merged"
    
    # Temporal events
    CLUSTER_TRENDING = "cluster.trending"
    CLUSTER_SPIKE_DETECTED = "cluster.spike_detected"
    CLUSTER_DRIFT_DETECTED = "cluster.drift_detected"
    NEW_ISSUE_DISCOVERED = "new_issue.discovered"
    
    # System events
    RESOURCE_LIMIT_EXCEEDED = "system.resource_limit_exceeded"
    ANOMALY_DETECTED = "system.anomaly_detected"


@dataclass
class DomainEvent:
    """Base class for all domain events."""
    event_id: str
    event_type: EventType
    tenant_id: TenantId
    timestamp: datetime
    metadata: Dict[str, Any]

    @staticmethod
    def create(event_type: EventType, tenant_id: TenantId, **metadata) -> "DomainEvent":
        """Factory method to create domain events."""
        return DomainEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata=metadata
        )


# Upload Events

@dataclass
class UploadCreatedEvent(DomainEvent):
    """Emitted when a new upload is created."""
    upload_id: UploadId
    filename: str
    total_reviews: int

    @staticmethod
    def create(upload_id: UploadId, tenant_id: TenantId, filename: str, total_reviews: int):
        return UploadCreatedEvent(
            event_id=str(uuid4()),
            event_type=EventType.UPLOAD_CREATED,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata={},
            upload_id=upload_id,
            filename=filename,
            total_reviews=total_reviews
        )


@dataclass
class UploadStageCompletedEvent(DomainEvent):
    """Emitted when a processing stage completes."""
    upload_id: UploadId
    stage: ProcessingStage
    duration_ms: int
    records_processed: int

    @staticmethod
    def create(
        upload_id: UploadId,
        tenant_id: TenantId,
        stage: ProcessingStage,
        duration_ms: int,
        records_processed: int
    ):
        return UploadStageCompletedEvent(
            event_id=str(uuid4()),
            event_type=EventType.UPLOAD_STAGE_COMPLETED,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata={},
            upload_id=upload_id,
            stage=stage,
            duration_ms=duration_ms,
            records_processed=records_processed
        )


@dataclass
class UploadCompletedEvent(DomainEvent):
    """Emitted when upload processing completes."""
    upload_id: UploadId
    clusters_created: int
    total_time_ms: int

    @staticmethod
    def create(
        upload_id: UploadId,
        tenant_id: TenantId,
        clusters_created: int,
        total_time_ms: int
    ):
        return UploadCompletedEvent(
            event_id=str(uuid4()),
            event_type=EventType.UPLOAD_COMPLETED,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata={},
            upload_id=upload_id,
            clusters_created=clusters_created,
            total_time_ms=total_time_ms
        )


@dataclass
class UploadFailedEvent(DomainEvent):
    """Emitted when upload processing fails."""
    upload_id: UploadId
    error_message: str
    stage: Optional[ProcessingStage] = None

    @staticmethod
    def create(
        upload_id: UploadId,
        tenant_id: TenantId,
        error_message: str,
        stage: Optional[ProcessingStage] = None
    ):
        return UploadFailedEvent(
            event_id=str(uuid4()),
            event_type=EventType.UPLOAD_FAILED,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata={},
            upload_id=upload_id,
            error_message=error_message,
            stage=stage
        )


# Cluster Events

@dataclass
class ClusterCreatedEvent(DomainEvent):
    """Emitted when a new cluster is created."""
    cluster_id: ClusterId
    upload_id: UploadId
    severity: Severity
    review_count: int

    @staticmethod
    def create(
        cluster_id: ClusterId,
        upload_id: UploadId,
        tenant_id: TenantId,
        severity: Severity,
        review_count: int
    ):
        return ClusterCreatedEvent(
            event_id=str(uuid4()),
            event_type=EventType.CLUSTER_CREATED,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata={},
            cluster_id=cluster_id,
            upload_id=upload_id,
            severity=severity,
            review_count=review_count
        )


@dataclass
class ClusterTrendingEvent(DomainEvent):
    """Emitted when a cluster starts trending (rapid growth)."""
    cluster_id: ClusterId
    growth_rate: float
    current_count: int

    @staticmethod
    def create(
        cluster_id: ClusterId,
        tenant_id: TenantId,
        growth_rate: float,
        current_count: int
    ):
        return ClusterTrendingEvent(
            event_id=str(uuid4()),
            event_type=EventType.CLUSTER_TRENDING,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata={},
            cluster_id=cluster_id,
            growth_rate=growth_rate,
            current_count=current_count
        )


@dataclass
class ClusterSpikeDetectedEvent(DomainEvent):
    """Emitted when sudden spike in cluster growth detected."""
    cluster_id: ClusterId
    spike_magnitude: float
    baseline_count: int
    current_count: int

    @staticmethod
    def create(
        cluster_id: ClusterId,
        tenant_id: TenantId,
        spike_magnitude: float,
        baseline_count: int,
        current_count: int
    ):
        return ClusterSpikeDetectedEvent(
            event_id=str(uuid4()),
            event_type=EventType.CLUSTER_SPIKE_DETECTED,
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            metadata={},
            cluster_id=cluster_id,
            spike_magnitude=spike_magnitude,
            baseline_count=baseline_count,
            current_count=current_count
        )
