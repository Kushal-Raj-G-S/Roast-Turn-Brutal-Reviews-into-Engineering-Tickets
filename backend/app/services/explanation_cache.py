"""
In-memory store for pre-generated per-severity category explanations.

Key: (upload_id, severity) → {"status": str, "explanation": str}

Status values: "pending" | "generating" | "done" | "failed"

Lives for the lifetime of the server process. If the server restarts
the frontend triggers a fresh re-generation via POST /severity-explanations/generate.

Eviction: LRU cap of MAX_UPLOADS entries — oldest upload evicted when cap is exceeded.
"""

from collections import OrderedDict
from typing import Literal

SeverityStatus = Literal["pending", "generating", "done", "failed", "not_started"]

MAX_UPLOADS = 50  # Maximum upload_ids retained in memory

# OrderedDict preserves insertion order; last-used key is moved to end on access.
_store: OrderedDict[int, dict[str, dict]] = OrderedDict()


def _touch(upload_id: int) -> None:
    """Move upload_id to most-recently-used position; evict oldest if over cap."""
    if upload_id in _store:
        _store.move_to_end(upload_id)
    if len(_store) > MAX_UPLOADS:
        _store.popitem(last=False)  # Remove least-recently-used entry


def set_status(upload_id: int, severity: str, status: SeverityStatus) -> None:
    if upload_id not in _store:
        _store[upload_id] = {}
    if severity not in _store[upload_id]:
        _store[upload_id][severity] = {}
    _store[upload_id][severity]["status"] = status
    _touch(upload_id)


def set_explanation(upload_id: int, severity: str, explanation: str) -> None:
    if upload_id not in _store:
        _store[upload_id] = {}
    _store[upload_id][severity] = {"status": "done", "explanation": explanation}
    _touch(upload_id)


def get(upload_id: int, severity: str) -> dict | None:
    result = _store.get(upload_id, {}).get(severity)
    if result is not None:
        _touch(upload_id)
    return result


def get_all(upload_id: int) -> dict[str, dict]:
    if upload_id in _store:
        _touch(upload_id)
    return dict(_store.get(upload_id, {}))
