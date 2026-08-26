"""
LLM observability for the RCA agent.

Tier 1: Langfuse (free cloud tier, or self-hosted) — used when
        LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set. Gives a full
        trace UI: every agent step, prompt, output, latency, cost.

Tier 2: Local JSONL trace log — zero setup, zero account needed. Every
        agent run appends a structured trace to ./traces/rca_traces.jsonl
        so the pipeline is still fully observable out of the box.
"""

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TRACE_DIR = Path("./traces")
_TRACE_FILE = _TRACE_DIR / "rca_traces.jsonl"

_USE_LANGFUSE = bool(os.getenv("LANGFUSE_PUBLIC_KEY")) and bool(os.getenv("LANGFUSE_SECRET_KEY"))
_langfuse_client: Optional[object] = None


def _get_langfuse():
    global _langfuse_client
    if _langfuse_client is None:
        from langfuse import Langfuse
        _langfuse_client = Langfuse()
        logger.info("✅ Observability: Langfuse tracing active")
    return _langfuse_client


class Trace:
    """One end-to-end agent run. Use `.span()` for each node/step inside it."""

    def __init__(self, name: str, metadata: dict[str, Any]):
        self.name = name
        self.metadata = metadata
        self.trace_id = str(uuid.uuid4())
        self.spans: list[dict[str, Any]] = []
        self._start = time.time()
        self._lf_trace = None

        if _USE_LANGFUSE:
            try:
                lf = _get_langfuse()
                self._lf_trace = lf.trace(id=self.trace_id, name=name, metadata=metadata)
            except Exception as e:
                logger.warning(f"⚠️  Langfuse trace() failed ({e}) — using local trace log only")

    @contextmanager
    def span(self, name: str, input_data: Any = None):
        start = time.time()
        record = {"name": name, "input": _safe(input_data)}
        lf_span = None
        if self._lf_trace is not None:
            try:
                lf_span = self._lf_trace.span(name=name, input=_safe(input_data))
            except Exception:
                lf_span = None
        try:
            yield record
        finally:
            record["duration_ms"] = round((time.time() - start) * 1000, 1)
            self.spans.append(record)
            if lf_span is not None:
                try:
                    lf_span.end(output=record.get("output"))
                except Exception:
                    pass

    def finish(self, output: Any = None) -> str:
        """Write the local trace record and close the Langfuse trace. Returns trace_id."""
        self.metadata["total_duration_ms"] = round((time.time() - self._start) * 1000, 1)
        _TRACE_DIR.mkdir(exist_ok=True)
        try:
            with open(_TRACE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "trace_id": self.trace_id,
                    "name": self.name,
                    "metadata": self.metadata,
                    "spans": self.spans,
                    "output": _safe(output),
                }, default=str) + "\n")
        except Exception as e:
            logger.warning(f"⚠️  Failed to write local trace log: {e}")

        if self._lf_trace is not None:
            try:
                self._lf_trace.update(output=_safe(output))
            except Exception:
                pass

        return self.trace_id


def _safe(value: Any, max_len: int = 2000) -> Any:
    """Truncate large payloads before logging them."""
    if value is None:
        return None
    text = str(value)
    return text[:max_len] + ("…" if len(text) > max_len else "")


def start_trace(name: str, metadata: Optional[dict[str, Any]] = None) -> Trace:
    return Trace(name, metadata or {})
