"""
Queries - Represent read-only data requests.
Follows CQRS pattern - separated from commands.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..domain.value_objects import (
    TenantId, UploadId, ClusterId, UploadStatus, ClusterStatus
)


@dataclass
class GetUploadQuery:
    """Query to get upload details."""
    upload_id: UploadId
    tenant_id: TenantId


@dataclass
class ListUploadsQuery:
    """Query to list uploads for a tenant."""
    tenant_id: TenantId
    status: Optional[UploadStatus] = None
    limit: int = 100
    offset: int = 0


@dataclass
class GetUploadProgressQuery:
    """Query to get real-time upload progress."""
    upload_id: UploadId
    tenant_id: TenantId


@dataclass
class ListClustersQuery:
    """Query to list clusters."""
    tenant_id: TenantId
    upload_id: Optional[UploadId] = None
    status: Optional[ClusterStatus] = None
    limit: int = 100
    offset: int = 0


@dataclass
class GetClusterQuery:
    """Query to get cluster details."""
    cluster_id: ClusterId
    tenant_id: TenantId


@dataclass
class GetClusterReviewsQuery:
    """Query to get reviews in a cluster."""
    cluster_id: ClusterId
    tenant_id: TenantId
    limit: int = 100
    offset: int = 0


@dataclass
class GetAnalyticsQuery:
    """Query to get analytics for uploads/clusters."""
    tenant_id: TenantId
    upload_id: Optional[UploadId] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@dataclass
class SearchSimilarClustersQuery:
    """Query to find similar clusters."""
    tenant_id: TenantId
    query_text: str
    limit: int = 10


@dataclass
class GetTrendingClustersQuery:
    """Query to get trending clusters."""
    tenant_id: TenantId
    window_hours: int = 24
    limit: int = 20


@dataclass
class GetClusterTimeSeriesQuery:
    """Query to get time-series metrics for a cluster."""
    cluster_id: ClusterId
    tenant_id: TenantId
    start_time: datetime
    end_time: datetime
