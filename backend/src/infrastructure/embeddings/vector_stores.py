"""
Vector Store Implementations
Supports FAISS (local), Pinecone, Weaviate, Qdrant.
"""

import logging
from typing import List, Optional, Dict, Any
import numpy as np

from ...domain.services import IVectorStore

logger = logging.getLogger(__name__)


class FAISSVectorStore(IVectorStore):
    """
    FAISS vector store for local/in-memory similarity search.
    Optimized for CPU with optional GPU support.
    """

    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        self.indices: Dict[str, Any] = {}  # index_name -> faiss.Index
        self.id_maps: Dict[str, Dict[int, str]] = {}  # index_name -> {faiss_id: external_id}
        self.metadata_store: Dict[str, Dict[str, Dict]] = {}  # index_name -> {id -> metadata}

    async def create_index(
        self,
        index_name: str,
        dimension: int,
        metric: str = "cosine"
    ) -> None:
        """Create a FAISS index."""
        import faiss

        if metric == "cosine":
            # Use inner product with normalized vectors
            index = faiss.IndexFlatIP(dimension)
        elif metric == "l2":
            # L2 distance
            index = faiss.IndexFlatL2(dimension)
        else:
            raise ValueError(f"Unsupported metric: {metric}")

        # Move to GPU if requested
        if self.use_gpu:
            try:
                res = faiss.StandardGpuResources()
                index = faiss.index_cpu_to_gpu(res, 0, index)
                logger.info(f"Created GPU FAISS index: {index_name}")
            except Exception as e:
                logger.warning(f"GPU not available, using CPU: {e}")
        else:
            logger.info(f"Created CPU FAISS index: {index_name}")

        self.indices[index_name] = index
        self.id_maps[index_name] = {}
        self.metadata_store[index_name] = {}

    async def add_vectors(
        self,
        index_name: str,
        vectors: List[List[float]],
        ids: List[str],
        metadata: Optional[List[Dict]] = None
    ) -> None:
        """Add vectors to FAISS index."""
        if index_name not in self.indices:
            raise ValueError(f"Index {index_name} not found")

        index = self.indices[index_name]
        id_map = self.id_maps[index_name]
        meta_store = self.metadata_store[index_name]

        # Convert to numpy array
        vectors_np = np.array(vectors, dtype=np.float32)

        # Normalize for cosine similarity (if using IP)
        if isinstance(index, (type(index).__name__ == "IndexFlatIP")):
            faiss.normalize_L2(vectors_np)

        # Get current index size to assign FAISS IDs
        current_size = index.ntotal

        # Add to FAISS
        index.add(vectors_np)

        # Map external IDs to FAISS IDs
        for i, external_id in enumerate(ids):
            faiss_id = current_size + i
            id_map[faiss_id] = external_id

            # Store metadata
            if metadata and i < len(metadata):
                meta_store[external_id] = metadata[i]

        logger.debug(f"Added {len(vectors)} vectors to index {index_name}")

    async def search(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        if index_name not in self.indices:
            raise ValueError(f"Index {index_name} not found")

        index = self.indices[index_name]
        id_map = self.id_maps[index_name]
        meta_store = self.metadata_store[index_name]

        # Convert query to numpy
        query_np = np.array([query_vector], dtype=np.float32)

        # Normalize for cosine
        import faiss
        if isinstance(index, (type(index).__name__ == "IndexFlatIP")):
            faiss.normalize_L2(query_np)

        # Search
        distances, indices = index.search(query_np, top_k)

        # Convert results
        results = []
        for i, (faiss_id, distance) in enumerate(zip(indices[0], distances[0])):
            if faiss_id == -1:  # No result
                continue

            external_id = id_map.get(faiss_id)
            if external_id is None:
                continue

            # Apply filters if provided
            if filter_dict:
                metadata = meta_store.get(external_id, {})
                if not all(metadata.get(k) == v for k, v in filter_dict.items()):
                    continue

            result = {
                "id": external_id,
                "score": float(distance),
                "metadata": meta_store.get(external_id, {})
            }
            results.append(result)

        return results

    async def delete_index(self, index_name: str) -> None:
        """Delete an index."""
        if index_name in self.indices:
            del self.indices[index_name]
            del self.id_maps[index_name]
            del self.metadata_store[index_name]
            logger.info(f"Deleted index: {index_name}")

    async def update_vector(
        self,
        index_name: str,
        vector_id: str,
        vector: List[float],
        metadata: Optional[Dict] = None
    ) -> None:
        """Update a vector (FAISS doesn't support updates, so we'd need to rebuild)."""
        logger.warning("FAISS doesn't support vector updates efficiently")
        # For production, consider using IndexIDMap for better update support


class PineconeVectorStore(IVectorStore):
    """
    Pinecone vector database integration.
    Cloud-based, fully managed vector DB.
    """

    def __init__(self, api_key: str, environment: str):
        self.api_key = api_key
        self.environment = environment
        self._pinecone = None

    def _get_client(self):
        """Lazy load Pinecone client."""
        if self._pinecone is None:
            import pinecone
            pinecone.init(api_key=self.api_key, environment=self.environment)
            self._pinecone = pinecone
        return self._pinecone

    async def create_index(
        self,
        index_name: str,
        dimension: int,
        metric: str = "cosine"
    ) -> None:
        """Create Pinecone index."""
        pinecone = self._get_client()

        if index_name not in pinecone.list_indexes():
            pinecone.create_index(
                name=index_name,
                dimension=dimension,
                metric=metric
            )
            logger.info(f"Created Pinecone index: {index_name}")
        else:
            logger.info(f"Pinecone index already exists: {index_name}")

    async def add_vectors(
        self,
        index_name: str,
        vectors: List[List[float]],
        ids: List[str],
        metadata: Optional[List[Dict]] = None
    ) -> None:
        """Add vectors to Pinecone."""
        pinecone = self._get_client()
        index = pinecone.Index(index_name)

        # Prepare upsert data
        vectors_to_upsert = []
        for i, (vec, vec_id) in enumerate(zip(vectors, ids)):
            meta = metadata[i] if metadata and i < len(metadata) else {}
            vectors_to_upsert.append((vec_id, vec, meta))

        # Upsert in batches
        batch_size = 100
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i:i + batch_size]
            index.upsert(vectors=batch)

        logger.debug(f"Added {len(vectors)} vectors to Pinecone index {index_name}")

    async def search(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search Pinecone index."""
        pinecone = self._get_client()
        index = pinecone.Index(index_name)

        # Query
        query_response = index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            filter=filter_dict
        )

        # Convert results
        results = []
        for match in query_response.matches:
            results.append({
                "id": match.id,
                "score": float(match.score),
                "metadata": match.metadata
            })

        return results

    async def delete_index(self, index_name: str) -> None:
        """Delete Pinecone index."""
        pinecone = self._get_client()
        pinecone.delete_index(index_name)
        logger.info(f"Deleted Pinecone index: {index_name}")

    async def update_vector(
        self,
        index_name: str,
        vector_id: str,
        vector: List[float],
        metadata: Optional[Dict] = None
    ) -> None:
        """Update vector in Pinecone."""
        pinecone = self._get_client()
        index = pinecone.Index(index_name)

        index.upsert(vectors=[(vector_id, vector, metadata or {})])
        logger.debug(f"Updated vector {vector_id} in Pinecone")


class QdrantVectorStore(IVectorStore):
    """
    Qdrant vector database integration.
    Can be self-hosted or cloud-based.
    """

    def __init__(self, url: str = "http://localhost:6333", api_key: Optional[str] = None):
        self.url = url
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """Lazy load Qdrant client."""
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(
                url=self.url,
                api_key=self.api_key
            )
        return self._client

    async def create_index(
        self,
        index_name: str,
        dimension: int,
        metric: str = "cosine"
    ) -> None:
        """Create Qdrant collection."""
        from qdrant_client.models import Distance, VectorParams

        client = self._get_client()

        # Map metric
        distance_map = {
            "cosine": Distance.COSINE,
            "l2": Distance.EUCLID,
            "dot": Distance.DOT
        }

        client.create_collection(
            collection_name=index_name,
            vectors_config=VectorParams(
                size=dimension,
                distance=distance_map.get(metric, Distance.COSINE)
            )
        )
        logger.info(f"Created Qdrant collection: {index_name}")

    async def add_vectors(
        self,
        index_name: str,
        vectors: List[List[float]],
        ids: List[str],
        metadata: Optional[List[Dict]] = None
    ) -> None:
        """Add vectors to Qdrant."""
        from qdrant_client.models import PointStruct

        client = self._get_client()

        # Prepare points
        points = []
        for i, (vec, vec_id) in enumerate(zip(vectors, ids)):
            payload = metadata[i] if metadata and i < len(metadata) else {}
            point = PointStruct(
                id=vec_id,
                vector=vec,
                payload=payload
            )
            points.append(point)

        # Upsert
        client.upsert(collection_name=index_name, points=points)
        logger.debug(f"Added {len(vectors)} vectors to Qdrant collection {index_name}")

    async def search(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search Qdrant collection."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = self._get_client()

        # Build filter
        qdrant_filter = None
        if filter_dict:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_dict.items()
            ]
            qdrant_filter = Filter(must=conditions)

        # Search
        search_result = client.search(
            collection_name=index_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter
        )

        # Convert results
        results = []
        for hit in search_result:
            results.append({
                "id": hit.id,
                "score": float(hit.score),
                "metadata": hit.payload
            })

        return results

    async def delete_index(self, index_name: str) -> None:
        """Delete Qdrant collection."""
        client = self._get_client()
        client.delete_collection(collection_name=index_name)
        logger.info(f"Deleted Qdrant collection: {index_name}")

    async def update_vector(
        self,
        index_name: str,
        vector_id: str,
        vector: List[float],
        metadata: Optional[Dict] = None
    ) -> None:
        """Update vector in Qdrant."""
        from qdrant_client.models import PointStruct

        client = self._get_client()

        point = PointStruct(
            id=vector_id,
            vector=vector,
            payload=metadata or {}
        )

        client.upsert(collection_name=index_name, points=[point])
        logger.debug(f"Updated vector {vector_id} in Qdrant")
