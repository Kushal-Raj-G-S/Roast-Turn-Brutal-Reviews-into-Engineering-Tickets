"""
Clustering Engine Implementations
"""

import logging
from typing import List, Dict
import numpy as np

from ...domain.services import IClusteringEngine

logger = logging.getLogger(__name__)


class FAISSClusteringEngine(IClusteringEngine):
    """
    FAISS-based clustering using similarity thresholds.
    Fast and scalable for CPU.
    """

    # Target ~150 reviews per cluster, capped so K never explodes on huge
    # uploads. K is derived from n, not from a similarity threshold -- see
    # the class docstring for why the old threshold approach was replaced.
    REVIEWS_PER_CLUSTER = 150
    MAX_CLUSTERS = 400

    def __init__(self, metric: str = "cosine"):
        self.metric = metric

    async def cluster(
        self,
        embeddings: List[List[float]],
        threshold: float = 0.3,
        min_cluster_size: int = 1
    ) -> List[int]:
        """
        Partition embeddings with FAISS-native KMeans (adaptive K).

        Why not the old greedy-threshold approach: single-linkage chaining on
        a cosine threshold collapsed catastrophically -- either ~96% of
        reviews into one mega-cluster (low threshold) or thousands of
        singletons (high threshold, e.g. this method's old default of
        similarity >= 0.7). No threshold produced a usable distribution;
        the defect was the algorithm, not the tuning. KMeans avoids both
        failure modes by construction: a fixed K partitions every point,
        with no chaining and no unclustered noise.

        `threshold`/`min_cluster_size` are accepted for interface
        compatibility but no longer drive the partition -- K is sized from
        the review count instead.

        Args:
            embeddings: List of embedding vectors (one per review)
            threshold: Accepted for compatibility; not used to size clusters.
            min_cluster_size: Accepted for compatibility.

        Returns:
            List of cluster labels (same length as embeddings), each in
            [0, k).
        """
        import faiss

        if not embeddings:
            return []

        vectors = np.array(embeddings, dtype=np.float32)
        n_vectors, dimension = vectors.shape

        if n_vectors <= 2:
            # Too few to partition meaningfully; each is its own cluster.
            return list(range(n_vectors))

        # Cosine == L2 on L2-normalized vectors, so normalize once and let
        # KMeans (which minimizes L2) operate in cosine space.
        faiss.normalize_L2(vectors)

        k = max(1, min(self.MAX_CLUSTERS, n_vectors // self.REVIEWS_PER_CLUSTER))
        if k <= 1:
            return [0] * n_vectors

        km = faiss.Kmeans(dimension, k, niter=25, seed=42, verbose=False)
        km.train(vectors)
        _, assignments = km.index.search(vectors, 1)
        labels = [int(row[0]) for row in assignments]

        logger.info(
            f"Clustered {n_vectors} vectors into {k} clusters "
            f"(FAISS KMeans, ~{self.REVIEWS_PER_CLUSTER}/cluster)"
        )

        return labels

    async def incremental_cluster(
        self,
        new_embeddings: List[List[float]],
        existing_cluster_centers: List[List[float]],
        threshold: float = 0.3
    ) -> List[int]:
        """
        Assign new embeddings to existing clusters or create new ones.
        
        Args:
            new_embeddings: New vectors to cluster
            existing_cluster_centers: Centroids of existing clusters
            threshold: Similarity threshold
        
        Returns:
            List of cluster IDs (existing or new)
        """
        import faiss

        if not new_embeddings:
            return []

        if not existing_cluster_centers:
            # No existing clusters, do regular clustering
            return await self.cluster(new_embeddings, threshold)

        # Convert to numpy
        new_vectors = np.array(new_embeddings, dtype=np.float32)
        center_vectors = np.array(existing_cluster_centers, dtype=np.float32)

        # Create index of cluster centers
        dimension = center_vectors.shape[1]
        if self.metric == "cosine":
            index = faiss.IndexFlatIP(dimension)
            faiss.normalize_L2(center_vectors)
            faiss.normalize_L2(new_vectors)
        else:
            index = faiss.IndexFlatL2(dimension)

        index.add(center_vectors)

        # Assign each new vector to nearest cluster or create new
        labels = []
        next_new_cluster_id = len(existing_cluster_centers)

        for i in range(len(new_vectors)):
            distances, indices = index.search(new_vectors[i:i+1], 1)
            nearest_distance = distances[0][0]
            nearest_cluster = indices[0][0]

            # Check if within threshold
            if self.metric == "cosine":
                is_similar = nearest_distance >= (1 - threshold)
            else:
                is_similar = nearest_distance <= threshold

            if is_similar:
                labels.append(nearest_cluster)
            else:
                # Create new cluster
                labels.append(next_new_cluster_id)
                next_new_cluster_id += 1

        logger.info(
            f"Incrementally clustered {len(new_vectors)} vectors "
            f"({sum(1 for l in labels if l < len(existing_cluster_centers))} matched existing, "
            f"{sum(1 for l in labels if l >= len(existing_cluster_centers))} new clusters)"
        )

        return labels

    def get_cluster_centers(
        self,
        embeddings: List[List[float]],
        labels: List[int]
    ) -> Dict[int, List[float]]:
        """Calculate cluster centroids."""
        vectors = np.array(embeddings, dtype=np.float32)
        
        centers = {}
        for cluster_id in set(labels):
            cluster_mask = np.array(labels) == cluster_id
            cluster_vectors = vectors[cluster_mask]
            centroid = cluster_vectors.mean(axis=0)
            centers[cluster_id] = centroid.tolist()

        return centers


class HDBSCANClusteringEngine(IClusteringEngine):
    """
    HDBSCAN clustering - density-based, finds clusters of varying shapes.
    Good for noisy data.
    """

    def __init__(self, min_cluster_size: int = 5, min_samples: int = 1):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples

    async def cluster(
        self,
        embeddings: List[List[float]],
        threshold: float = 0.3,
        min_cluster_size: int = None
    ) -> List[int]:
        """Cluster using HDBSCAN."""
        try:
            import hdbscan
        except ImportError:
            logger.warning("HDBSCAN not installed, falling back to FAISS clustering")
            fallback = FAISSClusteringEngine()
            return await fallback.cluster(embeddings, threshold, min_cluster_size or 1)

        min_cluster_size = min_cluster_size or self.min_cluster_size

        # Convert to numpy
        vectors = np.array(embeddings, dtype=np.float32)

        # Cluster
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=self.min_samples,
            metric='euclidean',
            cluster_selection_method='eom'
        )

        labels = clusterer.fit_predict(vectors)

        # HDBSCAN uses -1 for noise, remap to separate clusters
        unique_labels = set(labels)
        n_clusters = len([l for l in unique_labels if l != -1])
        
        # Remap noise points to individual clusters
        remapped_labels = labels.tolist()
        next_cluster_id = max(unique_labels) + 1 if unique_labels else 0
        for i, label in enumerate(remapped_labels):
            if label == -1:
                remapped_labels[i] = next_cluster_id
                next_cluster_id += 1

        logger.info(
            f"HDBSCAN clustered {len(vectors)} vectors into {n_clusters} clusters "
            f"({sum(1 for l in labels if l == -1)} noise points reassigned)"
        )

        return remapped_labels

    async def incremental_cluster(
        self,
        new_embeddings: List[List[float]],
        existing_cluster_centers: List[List[float]],
        threshold: float = 0.3
    ) -> List[int]:
        """HDBSCAN doesn't support incremental clustering natively."""
        # Fall back to distance-based assignment
        fallback = FAISSClusteringEngine()
        return await fallback.incremental_cluster(
            new_embeddings,
            existing_cluster_centers,
            threshold
        )

    def get_cluster_centers(
        self,
        embeddings: List[List[float]],
        labels: List[int]
    ) -> Dict[int, List[float]]:
        """Calculate cluster centroids."""
        vectors = np.array(embeddings, dtype=np.float32)
        
        centers = {}
        for cluster_id in set(labels):
            cluster_mask = np.array(labels) == cluster_id
            cluster_vectors = vectors[cluster_mask]
            centroid = cluster_vectors.mean(axis=0)
            centers[cluster_id] = centroid.tolist()

        return centers
