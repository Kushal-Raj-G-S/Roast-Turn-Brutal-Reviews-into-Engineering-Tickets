"""
Commands - Represent actions/intents to modify system state.
Follows CQRS (Command Query Responsibility Segregation) pattern.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from ..domain.value_objects import TenantId, UploadId, ClusterId


@dataclass
class CreateUploadCommand:
    """Command to create a new upload."""
    tenant_id: TenantId
    user_id: UUID
    filename: str
    file_path: str
    file_size_bytes: int


@dataclass
class StartProcessingCommand:
    """Command to start processing an upload."""
    upload_id: UploadId


@dataclass
class CancelUploadCommand:
    """Command to cancel an upload."""
    upload_id: UploadId
    tenant_id: TenantId


@dataclass
class AssignClusterCommand:
    """Command to assign a cluster to an engineer."""
    cluster_id: ClusterId
    tenant_id: TenantId
    assigned_to: str


@dataclass
class ResolveClusterCommand:
    """Command to mark a cluster as resolved."""
    cluster_id: ClusterId
    tenant_id: TenantId


@dataclass
class RequestAIAnalysisCommand:
    """Command to request AI analysis for clusters."""
    upload_id: UploadId
    tenant_id: TenantId
    cluster_ids: Optional[list[ClusterId]] = None  # None = analyze all


@dataclass
class TrainActionabilityModelCommand:
    """Command to train actionability model with labeled data."""
    tenant_id: TenantId
    labeled_samples: list[tuple[str, bool]]  # (review_text, is_actionable)
