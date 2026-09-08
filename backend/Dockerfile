# Multi-stage build for the Roast backend.
#
# Why multi-stage matters here specifically: torch + onnxruntime +
# sentence-transformers pull in build toolchains and multi-GB wheels. A
# single-stage image lands around 5-6GB, which means slow GKE pulls, slow
# HPA scale-up (the thing we added the autoscaler for), and real registry
# cost. Compiling into a venv in the builder and copying only that venv
# into a clean runtime cuts the shipped image substantially.
#
# The ONNX-quantized embedding stage (SentenceTransformerProvider) is the
# CPU-bound part of the pipeline, so this image is what
# k8s/embedding-deployment.yaml scales horizontally under load.

# ---------- builder ----------
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-ONLY torch, installed first and deliberately from PyTorch's CPU
# wheel index.
#
# This is not a micro-optimization. On Linux, plain `pip install torch`
# resolves to the CUDA build and drags in the whole NVIDIA GPU runtime as
# transitive deps — nvidia-cublas alone is 423 MB, plus cuda-cupti,
# cuda-nvrtc, cudnn, nccl and friends: several GB of GPU libraries in an
# image that never sees a GPU. Roast's inference is CPU-only by design
# (faiss-cpu, ONNX int8 quantization on CPU — see requirements.txt).
#
# The bloat isn't just disk: a multi-GB image makes GKE node pulls slow,
# which directly undermines the HorizontalPodAutoscaler in
# k8s/embedding-deployment.yaml — pods that take minutes to pull can't
# absorb a burst. Verified by watching the build actually download them.
#
# Installed as its own layer before requirements.txt so the (large, rarely
# changing) torch layer stays cached across application code changes, and
# so the requirements install below sees torch already satisfied and does
# not pull the CUDA variant.
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir "torch>=2.9.0" \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# ---------- runtime ----------
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Keep HF/sentence-transformers model cache on a writable, predictable
    # path so it can be backed by a volume instead of re-downloading the
    # model on every pod start.
    HF_HOME=/home/roast/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/roast/.cache/huggingface

# libgomp1 is required at runtime by torch/onnxruntime; curl is for the
# container healthcheck. No compilers in the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 10001 roast

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=roast:roast . .

RUN mkdir -p /home/roast/.cache/huggingface \
    && chown -R roast:roast /home/roast /app

USER roast

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Single uvicorn worker per container: replica count is Kubernetes' job
# (see the HPA), and multiple workers each loading the embedding model
# would multiply memory per pod for no throughput gain on a CPU-bound
# workload.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
