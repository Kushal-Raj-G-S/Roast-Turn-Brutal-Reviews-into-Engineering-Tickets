"""
Roast Memory - ChromaDB Vector Service
"""

from typing import Optional


class RoastMemory:
    """Vector memory layer using ChromaDB and Sentence-Transformers."""

    def __init__(self, persist_path: str = "./chroma_db"):
        """Initialize ChromaDB (lazy import). Embeddings via EmbeddingBackend (no torch)."""
        import chromadb  # lazy import — ~100 MB, only load when actually used
        from app.services.bulk_embedding import EmbeddingBackend
        self.client = chromadb.PersistentClient(path=persist_path)
        self.collection = self.client.get_or_create_collection(name="roasts")
        self._backend = EmbeddingBackend()

    def get_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text via EmbeddingBackend (HF API or TF-IDF)."""
        import numpy as np
        vecs = self._backend.encode_batch([text])
        return vecs[0].tolist() if isinstance(vecs, np.ndarray) and vecs.ndim == 2 else list(vecs)
    
    def find_similar(self, text: str, threshold: float = 0.3) -> Optional[str]:
        """
        Find similar cluster in memory.
        
        Args:
            text: The review text to match
            threshold: Distance threshold (lower = more similar)
            
        Returns:
            cluster_id if match found, None otherwise
        """
        embedding = self.get_embedding(text)
        
        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["distances", "metadatas"]
        )
        
        # Check if we got results and if distance is below threshold
        if results["ids"] and results["ids"][0]:
            distance = results["distances"][0][0]
            if distance < threshold:
                return results["ids"][0][0]
        
        return None
    
    def save_cluster(self, cluster_id: str, text: str, metadata: dict) -> None:
        """
        Upsert a cluster vector to ChromaDB.
        
        Args:
            cluster_id: Unique cluster ID
            text: Representative text for embedding
            metadata: Additional metadata to store
        """
        embedding = self.get_embedding(text)
        
        self.collection.upsert(
            ids=[cluster_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata]
        )
    
    def reset(self) -> None:
        """Clear all data (for testing)."""
        self.client.delete_collection("roasts")
        self.collection = self.client.get_or_create_collection(name="roasts")
