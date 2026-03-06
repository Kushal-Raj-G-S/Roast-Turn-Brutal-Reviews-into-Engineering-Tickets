"""
Embedding backend — uses HuggingFace Inference API when HUGGINGFACE_API_KEY is set,
falls back to local sentence-transformers otherwise.

HF API removes the ~450 MB torch footprint entirely, making the app safe on 1 GB plans.
"""

import logging
import os
import threading
import time
from typing import Any, List

import numpy as np

from app.core.config import config

logger = logging.getLogger(__name__)

# HuggingFace Inference API config
_HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
_HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_HF_API_URL = f"https://api-inference.huggingface.co/models/{_HF_MODEL}"
_HF_BATCH_SIZE = 64   # HF API can handle up to ~100 texts per request

# Local model fallback singleton
_GLOBAL_MODEL_INSTANCE = None
_GLOBAL_MODEL_LOCK = threading.Lock()


def _hf_encode_batch(texts: List[str]) -> np.ndarray:
    """Call HuggingFace Inference API to get embeddings. Batches automatically."""
    import httpx

    headers = {"Authorization": f"Bearer {_HF_API_KEY}"}
    all_embeddings = []

    for i in range(0, len(texts), _HF_BATCH_SIZE):
        batch = texts[i: i + _HF_BATCH_SIZE]
        retries = 3
        for attempt in range(retries):
            try:
                resp = httpx.post(
                    _HF_API_URL,
                    headers=headers,
                    json={"inputs": batch},
                    timeout=60.0,
                )
                if resp.status_code == 503:
                    # Model warming up — wait and retry
                    wait = resp.json().get("estimated_time", 20)
                    logger.info(f"HF model warming up, waiting {wait}s...")
                    time.sleep(min(wait, 30))
                    continue
                resp.raise_for_status()
                all_embeddings.extend(resp.json())
                break
            except Exception as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"HF API failed after {retries} attempts: {e}") from e
                time.sleep(2 ** attempt)

    return np.array(all_embeddings, dtype="float32")


def get_global_model(model_name: str = None) -> Any:
    """Get or create the local singleton embedding model (lazy-loaded fallback)."""
    global _GLOBAL_MODEL_INSTANCE

    if _GLOBAL_MODEL_INSTANCE is None:
        with _GLOBAL_MODEL_LOCK:
            if _GLOBAL_MODEL_INSTANCE is None:
                from sentence_transformers import SentenceTransformer  # lazy import
                model_name = model_name or config.MODEL_NAME
                logger.info(f"🔧 Loading local embedding model (fallback): {model_name}")
                _GLOBAL_MODEL_INSTANCE = SentenceTransformer(model_name)
                logger.info(f"✅ Local model loaded. dim={_GLOBAL_MODEL_INSTANCE.get_sentence_embedding_dimension()}")

    return _GLOBAL_MODEL_INSTANCE


class EmbeddingBackend:
    """
    Embedding backend with automatic HF API / local fallback.

    If HUGGINGFACE_API_KEY is set → uses HF Inference API (zero torch, ~5 MB RAM).
    Otherwise → loads sentence-transformers locally (~450 MB torch).

    Interface is identical to the old class — no other code needs to change.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or config.MODEL_NAME
        self._use_hf = bool(_HF_API_KEY)
        if self._use_hf:
            logger.info(f"✅ EmbeddingBackend: using HuggingFace API ({_HF_MODEL}) — torch not loaded")
        else:
            logger.warning("⚠️  HUGGINGFACE_API_KEY not set — falling back to local torch model")
            self.model = get_global_model(self.model_name)

    def _load_model(self):
        """Legacy compat — no-op when using HF API."""
        if not self._use_hf:
            self.model = get_global_model(self.model_name)

    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False
    ) -> np.ndarray:
        """
        Encode texts to embeddings.
        Uses HF Inference API when key present, local model otherwise.
        """
        if not texts:
            return np.array([])

        logger.info(f"Encoding {len(texts)} texts via {'HF API' if self._use_hf else 'local model'}")

        if self._use_hf:
            return _hf_encode_batch(texts)

        # Local fallback
        batch_size = batch_size or config.BATCH_SIZE
        return self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=False,
        )

    def encode_parallel(
        self,
        texts: List[str],
        batch_size: int = None,
        num_workers: int = None,
    ) -> np.ndarray:
        """Parallel encoding — routes through encode_batch (HF API is already async-friendly)."""
        if not texts:
            return np.array([])
        # HF API handles batching internally; local model uses single process only on 1 vCPU
        return self.encode_batch(texts, batch_size=batch_size)


def _encode_chunk_worker(texts: List[str], model_name: str, batch_size: int) -> np.ndarray:
    """Legacy multiprocessing worker — used only when HF API is unavailable."""
    from sentence_transformers import SentenceTransformer  # lazy import
    model = SentenceTransformer(model_name)
    return model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=False,
    )
