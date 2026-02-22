"""
Embedding Provider Implementations
Supports multiple embedding models with caching and optimization.
"""

import logging
import hashlib
from typing import List, Optional, Dict
import numpy as np

from sentence_transformers import SentenceTransformer

from ...domain.services import IEmbeddingProvider
from ...domain.value_objects import EmbeddingVector

logger = logging.getLogger(__name__)


class SentenceTransformerProvider(IEmbeddingProvider):
    """
    Sentence Transformers embedding provider.
    Optimized for CPU with caching and batching.
    """

    def __init__(
        self,
        model_name: str = "paraphrase-MiniLM-L3-v2",
        cache_enabled: bool = True,
        batch_size: int = 128,
        num_workers: int = 1
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.cache_enabled = cache_enabled
        
        # Lazy load model
        self._model: Optional[SentenceTransformer] = None
        
        # In-memory cache (could be Redis/Memcached)
        self._cache: Dict[str, EmbeddingVector] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def _load_model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Model loaded. Dimension: {self._model.get_sentence_embedding_dimension()}")

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.sha256(text.encode()).hexdigest()

    async def embed(self, text: str) -> EmbeddingVector:
        """Embed single text with caching."""
        # Check cache
        if self.cache_enabled:
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                self._cache_hits += 1
                return self._cache[cache_key]
            self._cache_misses += 1

        # Load model if needed
        self._load_model()

        # Generate embedding
        embedding_array = self._model.encode(
            [text],
            batch_size=1,
            convert_to_numpy=True,
            normalize_embeddings=False
        )[0]

        embedding = EmbeddingVector(
            values=embedding_array.tolist(),
            dimension=len(embedding_array),
            model_name=self.model_name
        )

        # Cache it
        if self.cache_enabled:
            cache_key = self._get_cache_key(text)
            self._cache[cache_key] = embedding

        return embedding

    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False
    ) -> List[EmbeddingVector]:
        """Embed batch of texts with caching."""
        batch_size = batch_size or self.batch_size
        
        # Check cache for all texts
        results: List[Optional[EmbeddingVector]] = [None] * len(texts)
        texts_to_embed = []
        text_indices = []

        if self.cache_enabled:
            for i, text in enumerate(texts):
                cache_key = self._get_cache_key(text)
                if cache_key in self._cache:
                    results[i] = self._cache[cache_key]
                    self._cache_hits += 1
                else:
                    texts_to_embed.append(text)
                    text_indices.append(i)
                    self._cache_misses += 1
        else:
            texts_to_embed = texts
            text_indices = list(range(len(texts)))

        # Embed uncached texts
        if texts_to_embed:
            self._load_model()
            
            embedding_arrays = self._model.encode(
                texts_to_embed,
                batch_size=batch_size,
                convert_to_numpy=True,
                show_progress_bar=show_progress,
                normalize_embeddings=False
            )

            for i, (text, embedding_array) in enumerate(zip(texts_to_embed, embedding_arrays)):
                embedding = EmbeddingVector(
                    values=embedding_array.tolist(),
                    dimension=len(embedding_array),
                    model_name=self.model_name
                )
                
                # Store in result
                original_index = text_indices[i]
                results[original_index] = embedding

                # Cache it
                if self.cache_enabled:
                    cache_key = self._get_cache_key(text)
                    self._cache[cache_key] = embedding

        logger.debug(
            f"Batch embedding complete. Cache stats - "
            f"hits: {self._cache_hits}, misses: {self._cache_misses}, "
            f"hit_rate: {self._cache_hits / (self._cache_hits + self._cache_misses) * 100:.1f}%"
        )

        return results

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        self._load_model()
        return self._model.get_sentence_embedding_dimension()

    def get_model_name(self) -> str:
        """Get model identifier."""
        return self.model_name

    async def cache_embeddings(
        self,
        text_embedding_pairs: List[tuple[str, EmbeddingVector]]
    ) -> None:
        """Bulk cache embeddings."""
        for text, embedding in text_embedding_pairs:
            cache_key = self._get_cache_key(text)
            self._cache[cache_key] = embedding

    async def get_cached_embedding(self, text: str) -> Optional[EmbeddingVector]:
        """Retrieve cached embedding."""
        if not self.cache_enabled:
            return None
        cache_key = self._get_cache_key(text)
        return self._cache.get(cache_key)

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._cache),
            "hit_rate_pct": (
                self._cache_hits / (self._cache_hits + self._cache_misses) * 100
                if (self._cache_hits + self._cache_misses) > 0 else 0
            )
        }


class OpenAIEmbeddingProvider(IEmbeddingProvider):
    """
    OpenAI embedding provider (for comparison).
    Uses text-embedding-ada-002 or newer models.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-ada-002",
        cache_enabled: bool = True
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, EmbeddingVector] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key."""
        return hashlib.sha256(text.encode()).hexdigest()

    async def embed(self, text: str) -> EmbeddingVector:
        """Embed single text."""
        # Check cache
        if self.cache_enabled:
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                self._cache_hits += 1
                return self._cache[cache_key]
            self._cache_misses += 1

        # Call OpenAI API
        import openai
        openai.api_key = self.api_key
        
        response = await openai.Embedding.acreate(
            input=[text],
            model=self.model_name
        )
        
        embedding_values = response['data'][0]['embedding']
        embedding = EmbeddingVector(
            values=embedding_values,
            dimension=len(embedding_values),
            model_name=self.model_name
        )

        # Cache it
        if self.cache_enabled:
            cache_key = self._get_cache_key(text)
            self._cache[cache_key] = embedding

        return embedding

    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
        show_progress: bool = False
    ) -> List[EmbeddingVector]:
        """Embed batch of texts."""
        # OpenAI has rate limits, so batch carefully
        import openai
        openai.api_key = self.api_key

        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            response = await openai.Embedding.acreate(
                input=batch,
                model=self.model_name
            )
            
            for item in response['data']:
                embedding_values = item['embedding']
                embedding = EmbeddingVector(
                    values=embedding_values,
                    dimension=len(embedding_values),
                    model_name=self.model_name
                )
                results.append(embedding)

        return results

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        if self.model_name == "text-embedding-ada-002":
            return 1536
        elif self.model_name == "text-embedding-3-small":
            return 1536
        elif self.model_name == "text-embedding-3-large":
            return 3072
        return 1536  # Default

    def get_model_name(self) -> str:
        """Get model identifier."""
        return self.model_name

    async def cache_embeddings(
        self,
        text_embedding_pairs: List[tuple[str, EmbeddingVector]]
    ) -> None:
        """Bulk cache embeddings."""
        for text, embedding in text_embedding_pairs:
            cache_key = self._get_cache_key(text)
            self._cache[cache_key] = embedding

    async def get_cached_embedding(self, text: str) -> Optional[EmbeddingVector]:
        """Retrieve cached embedding."""
        if not self.cache_enabled:
            return None
        cache_key = self._get_cache_key(text)
        return self._cache.get(cache_key)
