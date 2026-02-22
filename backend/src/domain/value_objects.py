"""
Domain Value Objects - Immutable objects defined by their attributes.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4


class UploadStatus(str, Enum):
    """Upload processing status."""
    PENDING = "pending"
    VALIDATING = "validating"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClusterStatus(str, Enum):
    """Cluster lifecycle status."""
    FRESH_ROAST = "fresh_roast"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"
    DUPLICATE = "duplicate"


class Severity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "critical"  # App-breaking, immediate action
    HIGH = "high"  # Major feature broken, high impact
    MEDIUM = "medium"  # Moderate issues, usability problems
    LOW = "low"  # Minor issues, enhancement requests


class ProcessingStage(str, Enum):
    """Pipeline processing stages for observability."""
    CSV_LOADING = "csv_loading"
    VALIDATION = "validation"
    NOISE_FILTERING = "noise_filtering"
    ACTIONABILITY_SCORING = "actionability_scoring"
    EMBEDDING = "embedding"
    CLUSTERING = "clustering"
    RANKING = "ranking"
    AI_ANALYSIS = "ai_analysis"
    PERSISTENCE = "persistence"
    COMPLETED = "completed"


@dataclass(frozen=True)
class TenantId:
    """Multi-tenant identifier."""
    value: UUID

    @staticmethod
    def generate() -> "TenantId":
        return TenantId(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class UploadId:
    """Upload job identifier."""
    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ClusterId:
    """Cluster identifier."""
    value: str  # UUID string

    @staticmethod
    def generate() -> "ClusterId":
        return ClusterId(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ReviewMetadata:
    """Extracted metadata from review content."""
    rating: Optional[int] = None
    version: Optional[str] = None
    device: Optional[str] = None
    review_date: Optional[datetime] = None
    is_verified: bool = False


@dataclass(frozen=True)
class ActionabilityScore:
    """ML-based score indicating if a review is actionable."""
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    features: dict  # Feature values used for scoring
    is_actionable: bool  # True if score > threshold

    def __post_init__(self):
        assert 0.0 <= self.score <= 1.0, "Score must be between 0 and 1"
        assert 0.0 <= self.confidence <= 1.0, "Confidence must be between 0 and 1"


@dataclass(frozen=True)
class EmbeddingVector:
    """Vector representation of text."""
    values: List[float]
    dimension: int
    model_name: str

    def __post_init__(self):
        assert len(self.values) == self.dimension, "Vector dimension mismatch"

    def to_array(self):
        """Convert to numpy array."""
        import numpy as np
        return np.array(self.values, dtype=np.float32)


@dataclass(frozen=True)
class ClusterMetrics:
    """Metrics for a single cluster."""
    review_count: int
    avg_rating: float
    severity_distribution: dict
    affected_versions: List[str]
    affected_devices: List[str]
    time_range: tuple  # (start_date, end_date)
    keywords: List[str]


@dataclass(frozen=True)
class ProcessingMetrics:
    """Metrics for a complete processing job."""
    total_reviews: int
    filtered_noise: int
    actionable_reviews: int
    clusters_created: int
    ai_analyzed_count: int
    processing_time_ms: int
    stage_timings: dict  # Stage -> ms
    memory_peak_mb: float
    cpu_utilization: float

    @property
    def throughput_reviews_per_sec(self) -> float:
        """Calculate reviews processed per second."""
        if self.processing_time_ms == 0:
            return 0.0
        return (self.total_reviews / self.processing_time_ms) * 1000


@dataclass(frozen=True)
class TemporalMetrics:
    """Time-series metrics for cluster evolution."""
    cluster_id: ClusterId
    timestamp: datetime
    review_count: int
    growth_rate: float  # reviews/day
    is_trending: bool
    is_spike: bool  # Sudden increase
    drift_score: float  # How much cluster changed
