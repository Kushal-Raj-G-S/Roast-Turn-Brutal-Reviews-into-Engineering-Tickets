"""
Embedding backend — three-tier, memory-safe:

  Tier 1 (prod):  HuggingFace Inference API   — zero torch, ~5 MB RAM
                  activated when HUGGINGFACE_API_KEY env var is set

  Tier 2 (dev):   sklearn TF-IDF + TruncatedSVD — zero torch, ~15 MB RAM
                  512-dim LSA vectors, good enough for clustering

  torch / sentence-transformers are intentionally NOT imported anywhere.
  They are removed from requirements.txt to prevent accidental installation.
"""

import logging
import os
import threading
import time
from typing import Any, List

import numpy as np

from app.core.config import config

logger = logging.getLogger(__name__)

# ── Tier 1: HuggingFace Inference API ──────────────────────────────────────
_HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
_HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_HF_API_URL = f"https://api-inference.huggingface.co/models/{_HF_MODEL}"
_HF_BATCH_SIZE = 64

# ── Tier 2: sklearn TF-IDF + SVD singleton ─────────────────────────────────
_TFIDF_LOCK = threading.Lock()
_TFIDF_VECTORIZER: Any = None
_TFIDF_SVD: Any = None
_TFIDF_DIM = 384   # match all-MiniLM-L6-v2 output dimension


def _hf_encode_batch(texts: List[str]) -> np.ndarray:
    """Call HuggingFace Inference API to get embeddings. Batches automatically."""
    import httpx

    headers = {"Authorization": f"Bearer {_HF_API_KEY}"}
    all_embeddings: list = []

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


def _tfidf_encode(texts: List[str]) -> np.ndarray:
    """
    Tier-2 fallback: TF-IDF vectorisation + Truncated SVD (LSA).
    Uses only sklearn/scipy/numpy — no torch, no HF download.
    On first call, fits the vectoriser+SVD on the input texts.
    """
    global _TFIDF_VECTORIZER, _TFIDF_SVD
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    with _TFIDF_LOCK:
        if _TFIDF_VECTORIZER is None:
            logger.info("🔧 Tier-2 fallback: fitting TF-IDF + TruncatedSVD (no torch)")
            # Fit on same corpus — gives per-batch coherent embeddings
            vect = TfidfVectorizer(
                max_features=8000,
                sublinear_tf=True,
                strip_accents="unicode",
                analyzer="word",
                ngram_range=(1, 2),
                min_df=1,
            )
            tfidf_matrix = vect.fit_transform(texts)
            n_components = min(_TFIDF_DIM, tfidf_matrix.shape[1] - 1, tfidf_matrix.shape[0] - 1)
            svd = TruncatedSVD(n_components=n_components, random_state=42)
            svd.fit(tfidf_matrix)
            _TFIDF_VECTORIZER = vect
            _TFIDF_SVD = svd
            logger.info(f"✅ TF-IDF+SVD fitted. Output dim: {n_components}")

    tfidf_matrix = _TFIDF_VECTORIZER.transform(texts)
    embeddings = _TFIDF_SVD.transform(tfidf_matrix).astype("float32")
    return normalize(embeddings, norm="l2")


# ── Legacy compat stub (no-op — torch is gone) ─────────────────────────────
def get_global_model(model_name: str = None) -> None:
    """Deprecated stub kept for import compat. torch is no longer used."""
    logger.warning("get_global_model() called but torch is removed — using TF-IDF fallback")
    return None


class EmbeddingBackend:
    """
    Memory-safe embedding backend.

    Tier 1 — HF Inference API  (HUGGINGFACE_API_KEY set): zero torch, ~5 MB.
    Tier 2 — sklearn TF-IDF+SVD (no key):                 zero torch, ~15 MB.

    encode_batch / encode_parallel interface unchanged — callers unaffected.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or config.MODEL_NAME
        self._use_hf = bool(_HF_API_KEY)
        if self._use_hf:
            logger.info(f"✅ EmbeddingBackend: Tier-1 HuggingFace API ({_HF_MODEL}) — torch not loaded")
        else:
            logger.warning(
                "⚠️  HUGGINGFACE_API_KEY not set — Tier-2 TF-IDF+SVD fallback active (no torch)"
            )

    def _load_model(self):
        """Legacy compat — no-op."""
        pass

    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode texts → float32 embeddings. HF API or TF-IDF, never torch."""
        if not texts:
            return np.array([])

        backend = "HF API" if self._use_hf else "TF-IDF+SVD"
        logger.info(f"Encoding {len(texts)} texts via {backend}")

        if self._use_hf:
            return _hf_encode_batch(texts)
        return _tfidf_encode(texts)

    def encode_parallel(
        self,
        texts: List[str],
        batch_size: int = None,
        num_workers: int = None,
    ) -> np.ndarray:
        """Routes to encode_batch — parallel not needed (API / in-memory ops)."""
        return self.encode_batch(texts, batch_size=batch_size)


def _encode_chunk_worker(texts: List[str], model_name: str, batch_size: int) -> np.ndarray:
    """Legacy stub — redirects to TF-IDF (torch removed)."""
    return _tfidf_encode(texts)
