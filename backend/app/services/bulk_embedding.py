"""
Embedding backend — three-tier, best-quality-first:

  Tier 0 (default): sentence-transformers, local, CPU-only torch build.
                     Real transformer embeddings (`all-MiniLM-L6-v2`), free,
                     open-source, no API key, no per-request network call.
                     Model loads once per process and is reused for every
                     upload (this caching is correct — unlike a per-upload
                     TF-IDF vocabulary, a pretrained transformer's weights
                     are fixed and don't need to be refit per corpus).

  Tier 1 (opt-in):   HuggingFace Inference API — used only if
                     EMBEDDING_BACKEND=hf_api is explicitly set (e.g. for a
                     memory-constrained host where local torch isn't
                     affordable). Same underlying model, hosted remotely.

  Tier 2 (fallback): sklearn TF-IDF + TruncatedSVD — used only if neither of
                     the above is available (e.g. torch failed to import).
                     Much lower quality; fit fresh per upload.
"""

import logging
import os
import time
from typing import List, Optional

import numpy as np

from app.core.config import config

logger = logging.getLogger(__name__)

_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

# Set EMBEDDING_BACKEND=hf_api to use the hosted API tier instead of loading
# torch locally (e.g. on a host too memory-constrained for a local model).
_FORCE_HF_API = os.getenv("EMBEDDING_BACKEND", "").strip().lower() == "hf_api"

# ── Tier 1: HuggingFace Inference API ──────────────────────────────────────
_HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
_HF_API_URL = f"https://api-inference.huggingface.co/models/{_MODEL_ID}"
_HF_BATCH_SIZE = 64

# ── Tier 0: local sentence-transformers model (loaded once, reused) ───────
_ST_MODEL: Optional[object] = None
_ST_DIM = 384   # all-MiniLM-L6-v2 output dimension

# ── Tier 2: sklearn TF-IDF + SVD fallback ──────────────────────────────────
_TFIDF_DIM = 384


class _HFEndpointGone(Exception):
    """Raised when HF Inference API returns 410 — endpoint permanently deprecated."""


# App store reviews are short (a few sentences); all-MiniLM-L6-v2 defaults
# to a 256-token max length, which pads/tokenizes every batch to whatever
# the longest review in it is. Capping this to 128 measurably cuts CPU
# encode time on large uploads (200k+ reviews) without truncating anything
# that isn't already an outlier-length review.
_MAX_SEQ_LENGTH = int(os.getenv("EMBEDDING_MAX_SEQ_LENGTH", "128"))

# Set EMBEDDING_BACKEND=torch to skip the ONNX attempt entirely (escape
# hatch for a host/CPU where the pre-quantized ONNX export misbehaves).
_FORCE_TORCH = os.getenv("EMBEDDING_BACKEND", "").strip().lower() == "torch"

# Pre-quantized int8 ONNX export of this exact model, published on the HF
# hub. AVX2 is present on effectively every x86_64 CPU made since ~2013
# (unlike AVX-512, which many modern consumer chips disable), so this is
# the safe choice of quantized variant. Benchmarked locally: ~20-25% faster
# than plain torch on a 4000-review batch, same output shape/quality.
_ONNX_QUANT_FILE = "onnx/model_quint8_avx2.onnx"


def _load_sentence_transformer():
    """Load the local sentence-transformers model once per process.

    Tries the ONNX int8-quantized export first (faster CPU inference via
    onnxruntime, needs the optional `optimum[onnxruntime]` dependency).
    Falls back to plain torch if that's unavailable or fails to load for
    any reason — this must never be the thing that breaks embedding.
    """
    global _ST_MODEL
    if _ST_MODEL is not None:
        return _ST_MODEL

    from sentence_transformers import SentenceTransformer

    if not _FORCE_TORCH:
        try:
            logger.info(f"🔧 Loading ONNX int8-quantized model: {_MODEL_ID} ({_ONNX_QUANT_FILE})")
            _ST_MODEL = SentenceTransformer(
                _MODEL_ID, device="cpu", backend="onnx",
                model_kwargs={"file_name": _ONNX_QUANT_FILE},
            )
            _ST_MODEL.max_seq_length = _MAX_SEQ_LENGTH
            logger.info(
                f"✅ Local embedding model loaded (ONNX int8 quantized, CPU, "
                f"max_seq_length={_MAX_SEQ_LENGTH})"
            )
            return _ST_MODEL
        except Exception as e:
            logger.warning(f"⚠️  ONNX quantized backend unavailable ({e}) — falling back to torch")
            _ST_MODEL = None

    import torch
    logger.info(f"🔧 Loading local sentence-transformers model: {_MODEL_ID}")
    _ST_MODEL = SentenceTransformer(_MODEL_ID, device="cpu")
    _ST_MODEL.max_seq_length = _MAX_SEQ_LENGTH
    # Make sure torch is actually using every CPU core for inference —
    # left at its default this can silently sit at 1 thread depending
    # on how the process was launched (e.g. under uvicorn --reload).
    torch.set_num_threads(os.cpu_count() or 4)
    logger.info(
        f"✅ Local embedding model loaded (CPU torch, {torch.get_num_threads()} threads, "
        f"max_seq_length={_MAX_SEQ_LENGTH})"
    )
    return _ST_MODEL


def _st_encode(texts: List[str], batch_size: int = 64, show_progress: bool = False) -> np.ndarray:
    """Tier 0: real transformer embeddings via a local sentence-transformers model."""
    model = _load_sentence_transformer()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype("float32")


def _hf_encode_batch(texts: List[str]) -> np.ndarray:
    """Call HuggingFace Inference API to get embeddings. Batches automatically.

    Raises _HFEndpointGone on 410 so callers can fall through to the next tier.
    """
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
                if resp.status_code == 410:
                    raise _HFEndpointGone(
                        f"HF Inference API endpoint gone (410): {_HF_API_URL} — "
                        "falling back to next tier"
                    )
                if resp.status_code == 503:
                    wait = resp.json().get("estimated_time", 20)
                    logger.info(f"HF model warming up, waiting {wait}s...")
                    time.sleep(min(wait, 30))
                    continue
                resp.raise_for_status()
                all_embeddings.extend(resp.json())
                break
            except _HFEndpointGone:
                raise  # propagate immediately, no retries
            except Exception as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"HF API failed after {retries} attempts: {e}") from e
                time.sleep(2 ** attempt)

    return np.array(all_embeddings, dtype="float32")


def _tfidf_encode(texts: List[str]) -> np.ndarray:
    """
    Tier-2 fallback: TF-IDF vectorisation + Truncated SVD (LSA).
    Uses only sklearn/scipy/numpy — no torch, no HF download.

    Fits a fresh vectoriser+SVD on THIS call's texts every time — the
    vocabulary must come from the upload being processed, not from whatever
    unrelated upload happened to run first on this server process.
    """
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    logger.info(f"🔧 Fitting TF-IDF + TruncatedSVD on {len(texts)} texts (no torch)")
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
    embeddings = svd.fit_transform(tfidf_matrix).astype("float32")
    logger.info(f"✅ TF-IDF+SVD fitted. Output dim: {n_components}")

    return normalize(embeddings, norm="l2")


class EmbeddingBackend:
    """
    Best-quality-first embedding backend.

    Tier 0 — local sentence-transformers (default): real embeddings, free, no network call.
    Tier 1 — HF Inference API (EMBEDDING_BACKEND=hf_api): same model, hosted remotely.
    Tier 2 — sklearn TF-IDF+SVD: automatic fallback if torch/sentence-transformers
             fails to import (e.g. not installed on a constrained host).

    encode_batch / encode_parallel interface unchanged — callers unaffected.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or config.MODEL_NAME
        self._use_hf = _FORCE_HF_API and bool(_HF_API_KEY)
        self._use_local = False

        if self._use_hf:
            logger.info(f"✅ EmbeddingBackend: Tier-1 HuggingFace API ({_MODEL_ID})")
            return

        try:
            _load_sentence_transformer()
            self._use_local = True
            logger.info(f"✅ EmbeddingBackend: Tier-0 local sentence-transformers ({_MODEL_ID}, CPU)")
        except Exception as e:
            logger.warning(f"⚠️  Local sentence-transformers unavailable ({e}) — falling back")
            if bool(_HF_API_KEY):
                self._use_hf = True
                logger.info(f"✅ EmbeddingBackend: Tier-1 HuggingFace API ({_MODEL_ID})")
            else:
                logger.warning("⚠️  No HUGGINGFACE_API_KEY either — Tier-2 TF-IDF+SVD fallback active")

    def _load_model(self):
        """Legacy compat — no-op (model loading is lazy, handled internally)."""
        pass

    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode texts → float32 embeddings. Local model → HF API → TF-IDF fallback."""
        if not texts:
            return np.array([])

        if self._use_local:
            logger.info(f"Encoding {len(texts)} texts via local sentence-transformers")
            try:
                return _st_encode(texts, batch_size=batch_size or 64, show_progress=show_progress)
            except Exception as e:
                logger.warning(f"⚠️  Local embedding failed ({e}) — falling back")
                self._use_local = False

        if self._use_hf:
            logger.info(f"Encoding {len(texts)} texts via HF API")
            try:
                return _hf_encode_batch(texts)
            except _HFEndpointGone as e:
                logger.warning(f"⚠️  {e}")
                logger.warning("Permanently disabling HF API for this process — using TF-IDF+SVD")
                self._use_hf = False  # don't try HF again this session

        logger.info(f"Encoding {len(texts)} texts via TF-IDF+SVD")
        return _tfidf_encode(texts)

    def encode_parallel(
        self,
        texts: List[str],
        batch_size: int = None,
        num_workers: int = None,
    ) -> np.ndarray:
        """Routes to encode_batch — parallel not needed (local model / API / in-memory ops)."""
        return self.encode_batch(texts, batch_size=batch_size)


def get_global_model(model_name: str = None):
    """Legacy compat — returns the local sentence-transformers model if available."""
    try:
        return _load_sentence_transformer()
    except Exception:
        logger.warning("get_global_model() called but no local model is available")
        return None


def _encode_chunk_worker(texts: List[str], model_name: str, batch_size: int) -> np.ndarray:
    """Legacy stub — routes through the same tiered logic as encode_batch."""
    try:
        return _st_encode(texts, batch_size=batch_size)
    except Exception:
        return _tfidf_encode(texts)
