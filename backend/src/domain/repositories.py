"""
Repository Interfaces - Abstract data access layer.
These define the contract for persistence without implementation details.
Follows Repository Pattern and Hexagonal Architecture (Ports).
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime

from .entities import Upload, Cluster, Review, Tenant
from .value_objects import UploadId, ClusterId, TenantId, UploadStatus, ClusterStatus


class IUploadRepository(ABC):
    """Repository interface for Upload aggregate."""

    @abstractmethod
    async def create(self, upload: Upload) -> Upload:
        """Create a new upload."""
        pass

    @abstractmethod
    async def get_by_id(self, upload_id: UploadId) -> Optional[Upload]:
        """Get upload by ID."""
        pass

    @abstractmethod
    async def update(self, upload: Upload) -> Upload:
        """Update an existing upload."""
        pass

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: TenantId,
        status: Optional[UploadStatus] = None,
        limit: int = 100
    ) -> List[Upload]:
        """List uploads for a tenant."""
        pass

    @abstractmethod
    async def count_pending_by_tenant(self, tenant_id: TenantId) -> int:
        """Count pending uploads for a tenant."""
        pass

    @abstractmethod
    async def find_pending(self, limit: int = 1) -> List[Upload]:
        """Find pending uploads for processing."""
        pass


class IClusterRepository(ABC):
    """Repository interface for Cluster aggregate."""

    @abstractmethod
    async def create(self, cluster: Cluster) -> Cluster:
        """Create a new cluster."""
        pass

    @abstractmethod
    async def create_batch(self, clusters: List[Cluster]) -> List[Cluster]:
        """Batch create clusters (optimized)."""
        pass

    @abstractmethod
    async def get_by_id(self, cluster_id: ClusterId) -> Optional[Cluster]:
        """Get cluster by ID."""
        pass

    @abstractmethod
    async def update(self, cluster: Cluster) -> Cluster:
        """Update an existing cluster."""
        pass

    @abstractmethod
    async def list_by_upload(
        self,
        upload_id: UploadId,
        limit: int = 1000
    ) -> List[Cluster]:
        """List clusters for an upload."""
        pass

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: TenantId,
        status: Optional[ClusterStatus] = None,
        limit: int = 100
    ) -> List[Cluster]:
        """List clusters for a tenant."""
        pass

    @abstractmethod
    async def search_similar(
        self,
        tenant_id: TenantId,
        query_embedding: List[float],
        threshold: float = 0.8,
        limit: int = 10
    ) -> List[Cluster]:
        """Find similar clusters using vector search."""
        pass


class IReviewRepository(ABC):
    """Repository interface for Review aggregate."""

    @abstractmethod
    async def create_batch(self, reviews: List[Review]) -> List[Review]:
        """Batch create reviews (optimized)."""
        pass

    @abstractmethod
    async def list_by_cluster(
        self,
        cluster_id: ClusterId,
        limit: int = 100
    ) -> List[Review]:
        """List reviews in a cluster."""
        pass


class ITenantRepository(ABC):
    """Repository interface for Tenant aggregate."""

    @abstractmethod
    async def get_by_id(self, tenant_id: TenantId) -> Optional[Tenant]:
        """Get tenant by ID."""
        pass

    @abstractmethod
    async def get_by_api_key(self, api_key: str) -> Optional[Tenant]:
        """Get tenant by API key."""
        pass

    @abstractmethod
    async def create(self, tenant: Tenant) -> Tenant:
        """Create a new tenant."""
        pass

    @abstractmethod
    async def update(self, tenant: Tenant) -> Tenant:
        """Update tenant."""
        pass


class ITemporalMetricsRepository(ABC):
    """Repository for time-series cluster metrics."""

    @abstractmethod
    async def record_snapshot(
        self,
        cluster_id: ClusterId,
        metrics: Dict[str, Any]
    ) -> None:
        """Record a metrics snapshot for a cluster."""
        pass

    @abstractmethod
    async def get_time_series(
        self,
        cluster_id: ClusterId,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get time-series data for a cluster."""
        pass

    @abstractmethod
    async def detect_trending(
        self,
        tenant_id: TenantId,
        window_hours: int = 24
    ) -> List[ClusterId]:
        """Detect trending clusters."""
        pass
