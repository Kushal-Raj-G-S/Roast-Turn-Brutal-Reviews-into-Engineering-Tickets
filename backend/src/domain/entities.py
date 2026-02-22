"""
Domain Entities - Objects with identity and lifecycle.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from .value_objects import (
    UploadId, ClusterId, TenantId, UploadStatus, ClusterStatus,
    Severity, ReviewMetadata, ActionabilityScore, EmbeddingVector,
    ClusterMetrics, ProcessingMetrics
)


@dataclass
class Review:
    """
    Review entity - represents a single user review.
    This is an in-memory entity, not always persisted individually.
    """
    id: Optional[int]
    text: str
    metadata: ReviewMetadata
    actionability: Optional[ActionabilityScore] = None
    embedding: Optional[EmbeddingVector] = None
    cluster_id: Optional[ClusterId] = None
    tenant_id: Optional[TenantId] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_noise(self) -> bool:
        """Check if review is noise (not actionable)."""
        if self.actionability:
            return not self.actionability.is_actionable
        # Fallback to simple rule
        rating = self.metadata.rating
        return rating is not None and rating >= 4 and len(self.text) < 25

    def __hash__(self):
        """Hash based on text for deduplication."""
        return hash(self.text.lower().strip())


@dataclass
class Cluster:
    """
    Cluster entity - represents a group of similar reviews (an issue/ticket).
    """
    id: ClusterId
    upload_id: UploadId
    tenant_id: TenantId
    
    # Content
    title: str
    severity: Severity
    status: ClusterStatus = ClusterStatus.FRESH_ROAST
    
    # AI Analysis
    rca_title: Optional[str] = None
    rca_hypothesis: Optional[str] = None
    rca_steps: Optional[str] = None
    rca_fix: Optional[str] = None
    ai_analyzed: bool = False
    
    # Metadata
    metrics: Optional[ClusterMetrics] = None
    sample_reviews: List[Dict[str, Any]] = field(default_factory=list)
    
    # Assignment
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    def assign_to(self, engineer: str):
        """Assign cluster to an engineer."""
        self.assigned_to = engineer
        self.assigned_at = datetime.utcnow()
        self.status = ClusterStatus.IN_PROGRESS

    def mark_resolved(self):
        """Mark cluster as resolved."""
        self.status = ClusterStatus.RESOLVED
        self.resolved_at = datetime.utcnow()

    def add_ai_analysis(self, rca_title: str, hypothesis: str, steps: str, fix: str):
        """Add AI-generated RCA analysis."""
        self.rca_title = rca_title
        self.rca_hypothesis = hypothesis
        self.rca_steps = steps
        self.rca_fix = fix
        self.ai_analyzed = True
        self.updated_at = datetime.utcnow()


@dataclass
class Upload:
    """
    Upload entity - represents a batch processing job.
    """
    id: UploadId
    tenant_id: TenantId
    user_id: UUID
    
    # File info
    filename: str
    file_size_bytes: int
    file_path: str
    
    # Status
    status: UploadStatus = UploadStatus.PENDING
    error_message: Optional[str] = None
    
    # Metrics
    metrics: Optional[ProcessingMetrics] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def start_processing(self):
        """Mark upload as processing."""
        self.status = UploadStatus.PROCESSING
        self.started_at = datetime.utcnow()

    def complete(self, metrics: ProcessingMetrics):
        """Mark upload as completed."""
        self.status = UploadStatus.COMPLETED
        self.metrics = metrics
        self.completed_at = datetime.utcnow()

    def fail(self, error: str):
        """Mark upload as failed."""
        self.status = UploadStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()

    def cancel(self):
        """Cancel the upload."""
        self.status = UploadStatus.CANCELLED
        self.completed_at = datetime.utcnow()

    @property
    def is_terminal_state(self) -> bool:
        """Check if upload is in a terminal state."""
        return self.status in [
            UploadStatus.COMPLETED,
            UploadStatus.FAILED,
            UploadStatus.CANCELLED
        ]


@dataclass
class Tenant:
    """
    Tenant entity - represents a customer/organization in multi-tenant setup.
    """
    id: TenantId
    name: str
    api_key: str
    
    # Resource limits
    max_uploads_per_day: int = 100
    max_reviews_per_upload: int = 1_000_000
    max_concurrent_jobs: int = 3
    
    # Features
    features_enabled: Dict[str, bool] = field(default_factory=dict)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True

    def can_submit_upload(self, current_pending: int) -> bool:
        """Check if tenant can submit new upload."""
        return (
            self.is_active and
            current_pending < self.max_concurrent_jobs
        )

    def has_feature(self, feature: str) -> bool:
        """Check if tenant has a specific feature enabled."""
        return self.features_enabled.get(feature, False)
