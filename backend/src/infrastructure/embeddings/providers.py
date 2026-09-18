"""
Embedding Provider Implementations
Supports multiple embedding models with caching and optimization.
"""

import asyncio
import logging
import hashlib
from typing import List, Optional, Dict, Any

import httpx
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # torch removed in prod — NVIDIA API / TF-IDF used instead
    SentenceTransformer = None  # type: ignore[assignment,misc]

from ...domain.services import IEmbeddingProvider
from ...domain.value_objects import EmbeddingVector

logger = logging.getLogger(__name__)


class _TorchlessAdaptor:
    """Wraps EmbeddingBackend to mimic the SentenceTransformer duck-type interface."""

    def __init__(self, backend: Any):
        self._backend = backend

    def encode(self, texts, batch_size=128, convert_to_numpy=True, **_kwargs):
        if isinstance(texts, str):
            texts = [texts]
        return self._backend.encode_batch(texts)

    def get_sentence_embedding_dimension(self) -> int:
        return 384


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
        """Lazy load the embedding model. Falls back to EmbeddingBackend if torch unavailable."""
        if self._model is None:
            if SentenceTransformer is None:
                # torch removed from prod — delegate to memory-safe EmbeddingBackend
                from app.services.bulk_embedding import EmbeddingBackend
                logger.info("sentence-transformers unavailable — using EmbeddingBackend (HF API / TF-IDF)")
                self._model = _TorchlessAdaptor(EmbeddingBackend(self.model_name))
                return
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


class NvidiaEmbeddingProvider(IEmbeddingProvider):
    """
    Semantic embeddings via NVIDIA's hosted API (integrate.api.nvidia.com,
    OpenAI-compatible /v1/embeddings). This is the production embedding path:
    no local torch, so the whole app fits a 512 MB dyno, while still using
    real transformer embeddings (not TF-IDF).

    Engineered around three real constraints of the free dev tier:

    - **No network at startup.** get_dimension() returns a known constant, so
      app bootstrap never makes an API call — otherwise a slow first call
      could blow Heroku's 60 s boot window (R10).
    - **Concurrency, not sequential.** Batches are embedded in parallel
      (bounded by a semaphore), so ~600 reviews embed in ~3 s instead of the
      ~18 s a sequential loop takes.
    - **Key rotation + model fallback for resilience.** NVIDIA rate-limits per
      key AND per account (429), and retires embedding models (410 Gone).
      Each batch round-robins across the configured API keys and, on
      429/5xx/EOL, falls through to the next model with a short backoff. Add
      more keys (from separate accounts) to multiply the effective RPM; the
      code needs no change.

    All configured models MUST share one embedding dimension — a batch that
    falls back to another model must produce vectors the clusterer can mix
    with the rest.
    """

    _API_URL = "https://integrate.api.nvidia.com/v1/embeddings"

    def __init__(
        self,
        api_keys: List[str],
        models: List[str],
        dimension: int = 2048,
        api_batch_size: int = 100,
        concurrency: int = 16,
        cache_enabled: bool = True,
    ):
        self.api_keys = [k.strip() for k in api_keys if k and k.strip()]
        if not self.api_keys:
            raise ValueError("NVIDIA embedding provider requires at least one API key")
        self.models = [m.strip() for m in models if m and m.strip()]
        if not self.models:
            raise ValueError("NVIDIA embedding provider requires at least one model")
        self._dimension = dimension
        self.api_batch_size = api_batch_size
        self._sem = asyncio.Semaphore(concurrency)
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, EmbeddingVector] = {}
        self._key_cursor = 0

    def get_dimension(self) -> int:
        return self._dimension

    def get_model_name(self) -> str:
        return self.models[0]

    def _get_cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _next_key(self) -> str:
        # Round-robin so requests spread across accounts/keys, multiplying the
        # effective per-minute budget when keys live on separate accounts.
        key = self.api_keys[self._key_cursor % len(self.api_keys)]
        self._key_cursor += 1
        return key

    async def _embed_one_batch(
        self, client: httpx.AsyncClient, batch: List[str]
    ) -> List[List[float]]:
        """Embed one API batch, rotating keys and falling back across models."""
        api_key = self._next_key()
        last_err = "no attempt made"
        async with self._sem:
            for model in self.models:
                for retry in range(3):  # retries for transient 429/5xx/timeouts
                    try:
                        resp = await client.post(
                            self._API_URL,
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={
                                "input": batch,
                                "model": model,
                                "input_type": "passage",
                                "truncate": "END",
                            },
                        )
                        if resp.status_code == 200:
                            return [d["embedding"] for d in resp.json()["data"]]
                        if resp.status_code in (429, 500, 502, 503, 504):
                            # Transient / rate-limited: back off, and try a
                            # different key on the next attempt.
                            last_err = f"{resp.status_code} on {model}"
                            await asyncio.sleep(1.5 * (retry + 1))
                            api_key = self._next_key()
                            continue
                        # 410 EOL / 404 / other 4xx: this model is out, next model
                        last_err = f"{resp.status_code} on {model}: {resp.text[:120]}"
                        break
                    except Exception as e:  # network blip, timeout
                        last_err = f"{type(e).__name__} on {model}: {e}"
                        await asyncio.sleep(1.0)
        raise RuntimeError(
            f"NVIDIA embedding failed for a batch after all keys/models: {last_err}"
        )

    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 128,
        show_progress: bool = False,
    ) -> List[Optional[EmbeddingVector]]:
        results: List[Optional[EmbeddingVector]] = [None] * len(texts)

        to_embed: List[str] = []
        indices: List[int] = []
        for i, text in enumerate(texts):
            if self.cache_enabled:
                ck = self._get_cache_key(text)
                cached = self._cache.get(ck)
                if cached is not None:
                    results[i] = cached
                    continue
            to_embed.append(text)
            indices.append(i)

        if to_embed:
            bs = self.api_batch_size
            batches = [to_embed[i:i + bs] for i in range(0, len(to_embed), bs)]
            index_batches = [indices[i:i + bs] for i in range(0, len(indices), bs)]

            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
                embedded = await asyncio.gather(
                    *[self._embed_one_batch(client, b) for b in batches]
                )

            for bi, vectors in enumerate(embedded):
                for j, vec in enumerate(vectors):
                    orig = index_batches[bi][j]
                    vec = self._maybe_truncate(vec)
                    ev = EmbeddingVector(
                        values=vec,
                        dimension=len(vec),
                        model_name=self.models[0],
                    )
                    results[orig] = ev
                    if self.cache_enabled:
                        self._cache[self._get_cache_key(texts[orig])] = ev

        return results

    def _maybe_truncate(self, vec: List[float]) -> List[float]:
        """
        Matryoshka-style truncation: keep the first `_dimension` components and
        re-normalize to unit length. The model returns 2048-dim vectors, but
        clustering cost scales with dimension (2048-dim clustering measured
        ~13x slower than 384-dim on 50k vectors). Truncating to e.g. 384 keeps
        the bulk of the semantic signal — these models are trained so the
        leading dimensions carry the most information — while making the
        downstream cluster step as cheap as the small local model's.
        Re-normalization matters because clustering uses cosine similarity.
        """
        if len(vec) <= self._dimension:
            return vec
        v = np.asarray(vec[:self._dimension], dtype=np.float32)
        norm = float(np.linalg.norm(v))
        if norm > 0:
            v = v / norm
        return v.tolist()

    async def embed(self, text: str) -> EmbeddingVector:
        return (await self.embed_batch([text]))[0]

    async def cache_embeddings(
        self, text_embedding_pairs: List[tuple[str, EmbeddingVector]]
    ) -> None:
        for text, embedding in text_embedding_pairs:
            self._cache[self._get_cache_key(text)] = embedding

    async def get_cached_embedding(self, text: str) -> Optional[EmbeddingVector]:
        if not self.cache_enabled:
            return None
        return self._cache.get(self._get_cache_key(text))
