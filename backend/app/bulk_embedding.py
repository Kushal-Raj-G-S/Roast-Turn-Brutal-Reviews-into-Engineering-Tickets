"""
High-performance embedding backend with CPU multiprocessing support.
Optimized for bulk processing of 100k+ reviews.
"""

import logging
import multiprocessing as mp
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import config

logger = logging.getLogger(__name__)


class EmbeddingBackend:
    """
    Wrapper around sentence-transformers with batch encoding and multiprocessing.
    
    Features:
    - CPU-parallel encoding using all cores
    - Automatic batching for memory efficiency
    - Progress tracking for large datasets
    
    Example:
        backend = EmbeddingBackend()
        embeddings = backend.encode_batch(texts, batch_size=256)
    """
    
    def __init__(self, model_name: str = None):
        """
        Initialize the embedding model.
        
        Args:
            model_name: Model to load (defaults to config.MODEL_NAME)
        """
        self.model_name = model_name or config.MODEL_NAME
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load the sentence transformer model."""
        logger.info(f"Loading embedding model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"Model loaded. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
    
    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False
    ) -> np.ndarray:
        """
        Encode a list of texts into embeddings using batching.
        
        Args:
            texts: List of text strings to embed
            batch_size: Batch size for encoding (defaults to config.BATCH_SIZE)
            show_progress: Whether to show progress bar
        
        Returns:
            numpy array of shape [len(texts), embedding_dim]
        """
        if not texts:
            return np.array([])
        
        batch_size = batch_size or config.BATCH_SIZE
        
        logger.info(f"Encoding {len(texts)} texts with batch_size={batch_size}")
        
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=show_progress,
            normalize_embeddings=False  # We'll use cosine distance in clustering
        )
        
        logger.info(f"Encoded {len(texts)} texts → shape {embeddings.shape}")
        return embeddings
    
    def encode_parallel(
        self,
        texts: List[str],
        batch_size: int = None,
        num_workers: int = None
    ) -> np.ndarray:
        """
        Encode texts using multiprocessing for CPU parallelization.
        
        This splits the texts into chunks, processes each chunk in a separate
        process (each with its own model instance), then concatenates results.
        
        Args:
            texts: List of text strings to embed
            batch_size: Batch size for encoding (defaults to config.BATCH_SIZE)
            num_workers: Number of worker processes (defaults to config.NUM_WORKERS)
        
        Returns:
            numpy array of shape [len(texts), embedding_dim]
        """
        if not texts:
            return np.array([])
        
        batch_size = batch_size or config.BATCH_SIZE
        num_workers = num_workers or config.NUM_WORKERS
        
        # For small datasets, just use single-process encoding
        if len(texts) < 1000:
            logger.info(f"Small dataset ({len(texts)} texts), using single-process encoding")
            return self.encode_batch(texts, batch_size=batch_size)
        
        logger.info(f"Parallel encoding {len(texts)} texts with {num_workers} workers")
        
        # Split texts into chunks
        chunk_size = len(texts) // num_workers
        chunks = []
        for i in range(num_workers):
            start = i * chunk_size
            end = start + chunk_size if i < num_workers - 1 else len(texts)
            chunks.append(texts[start:end])
        
        # Process chunks in parallel
        with mp.Pool(processes=num_workers) as pool:
            args = [(chunk, self.model_name, batch_size) for chunk in chunks]
            results = pool.starmap(_encode_chunk_worker, args)
        
        # Concatenate results
        embeddings = np.vstack(results)
        logger.info(f"Parallel encoding complete → shape {embeddings.shape}")
        
        return embeddings


def _encode_chunk_worker(texts: List[str], model_name: str, batch_size: int) -> np.ndarray:
    """
    Worker function for parallel encoding.
    Each process loads its own model instance to avoid serialization issues.
    
    Args:
        texts: Chunk of texts to encode
        model_name: Model to load
        batch_size: Batch size for encoding
    
    Returns:
        Embeddings for this chunk
    """
    # Each worker loads its own model
    model = SentenceTransformer(model_name)
    
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=False
    )
    
    return embeddings
