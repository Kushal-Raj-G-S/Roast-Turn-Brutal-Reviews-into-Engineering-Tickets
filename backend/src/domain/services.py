"""
Service Interfaces - Abstract service layer (Ports).
Defines contracts for external dependencies without implementation.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from enum import Enum

from .value_objects import EmbeddingVector, ActionabilityScore, ClusterId
from .entities import Review


class VectorBackend(str, Enum):
    """Supported vector database backends."""
    FAISS_LOCAL = "faiss_local"
    FAISS_IVF = "faiss_ivf"
    PINECONE = "pinecone"
    WEAVIATE = "weaviate"
    QDRANT = "qdrant"
    MILVUS = "milvus"


class IEmbeddingProvider(ABC):
    """Interface for text embedding generation."""

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingVector:
        """Embed a single text."""
        pass

    @abstractmethod
    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 128,
        show_progress: bool = False
    ) -> List[EmbeddingVector]:
        """Embed a batch of texts."""
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get model identifier."""
        pass

    @abstractmethod
    async def cache_embeddings(
        self,
        text_embedding_pairs: List[tuple[str, EmbeddingVector]]
    ) -> None:
        """Cache embeddings for reuse."""
        pass

    @abstractmethod
    async def get_cached_embedding(self, text: str) -> Optional[EmbeddingVector]:
        """Retrieve cached embedding."""
        pass


class IVectorStore(ABC):
    """Interface for vector storage and similarity search."""

    @abstractmethod
    async def create_index(
        self,
        index_name: str,
        dimension: int,
        metric: str = "cosine"
    ) -> None:
        """Create a new vector index."""
        pass

    @abstractmethod
    async def add_vectors(
        self,
        index_name: str,
        vectors: List[List[float]],
        ids: List[str],
        metadata: Optional[List[Dict]] = None
    ) -> None:
        """Add vectors to index."""
        pass

    @abstractmethod
    async def search(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        pass

    @abstractmethod
    async def delete_index(self, index_name: str) -> None:
        """Delete an index."""
        pass

    @abstractmethod
    async def update_vector(
        self,
        index_name: str,
        vector_id: str,
        vector: List[float],
        metadata: Optional[Dict] = None
    ) -> None:
        """Update a vector in the index."""
        pass


class IClusteringEngine(ABC):
    """Interface for clustering algorithms."""

    @abstractmethod
    async def cluster(
        self,
        embeddings: List[List[float]],
        threshold: float = 0.3,
        min_cluster_size: int = 1
    ) -> List[int]:
        """
        Cluster embeddings and return cluster labels.
        Returns: List of cluster IDs (same length as embeddings).
        """
        pass

    @abstractmethod
    async def incremental_cluster(
        self,
        new_embeddings: List[List[float]],
        existing_cluster_centers: List[List[float]],
        threshold: float = 0.3
    ) -> List[int]:
        """
        Assign new embeddings to existing clusters or create new ones.
        Returns: List of cluster IDs.
        """
        pass

    @abstractmethod
    def get_cluster_centers(
        self,
        embeddings: List[List[float]],
        labels: List[int]
    ) -> Dict[int, List[float]]:
        """Calculate cluster centroids."""
        pass


class IRankingStrategy(ABC):
    """Interface for cluster ranking/prioritization."""

    @abstractmethod
    async def rank_clusters(
        self,
        clusters: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Rank clusters by priority.
        Returns: Sorted list of clusters with priority scores.
        """
        pass

    @abstractmethod
    def calculate_priority_score(self, cluster: Dict[str, Any]) -> float:
        """Calculate priority score for a single cluster."""
        pass


class IActionabilityScorer(ABC):
    """Interface for ML-based actionability scoring."""

    @abstractmethod
    async def score(self, review: Review) -> ActionabilityScore:
        """Score a single review."""
        pass

    @abstractmethod
    async def score_batch(self, reviews: List[Review]) -> List[ActionabilityScore]:
        """Score a batch of reviews (optimized)."""
        pass

    @abstractmethod
    async def train_online(
        self,
        reviews: List[Review],
        labels: List[bool]
    ) -> None:
        """
        Update model with new labeled data (online learning).
        Labels: True = actionable, False = not actionable.
        """
        pass

    @abstractmethod
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores."""
        pass


class IAIAnalysisService(ABC):
    """Interface for LLM-based analysis."""

    @abstractmethod
    async def analyze_cluster(
        self,
        cluster_id: ClusterId,
        reviews: List[Review]
    ) -> Dict[str, str]:
        """
        Generate RCA for a cluster.
        Returns: Dict with rca_title, rca_hypothesis, rca_steps, rca_fix.
        """
        pass

    @abstractmethod
    async def analyze_batch(
        self,
        clusters: List[tuple[ClusterId, List[Review]]]
    ) -> Dict[ClusterId, Dict[str, str]]:
        """Batch analyze multiple clusters (optimized)."""
        pass


class IFileStorage(ABC):
    """Interface for file storage."""

    @abstractmethod
    async def save_file(
        self,
        file_path: str,
        content: bytes,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Save file and return storage path/URL.
        """
        pass

    @abstractmethod
    async def get_file(self, file_path: str) -> bytes:
        """Retrieve file content."""
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> None:
        """Delete a file."""
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        pass
