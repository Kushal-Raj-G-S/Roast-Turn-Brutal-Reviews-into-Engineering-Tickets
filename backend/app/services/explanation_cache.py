"""
In-memory store for pre-generated per-severity category explanations.

Key: (upload_id, severity) → {"status": str, "explanation": str}

Status values: "pending" | "generating" | "done" | "failed"

Lives for the lifetime of the server process. If the server restarts
the frontend triggers a fresh re-generation via POST /severity-explanations/generate.
"""

from typing import Literal

SeverityStatus = Literal["pending", "generating", "done", "failed", "not_started"]

_store: dict[int, dict[str, dict]] = {}


def set_status(upload_id: int, severity: str, status: SeverityStatus) -> None:
    if upload_id not in _store:
        _store[upload_id] = {}
    if severity not in _store[upload_id]:
        _store[upload_id][severity] = {}
    _store[upload_id][severity]["status"] = status


def set_explanation(upload_id: int, severity: str, explanation: str) -> None:
    if upload_id not in _store:
        _store[upload_id] = {}
    _store[upload_id][severity] = {"status": "done", "explanation": explanation}


def get(upload_id: int, severity: str) -> dict | None:
    return _store.get(upload_id, {}).get(severity)


def get_all(upload_id: int) -> dict[str, dict]:
    return dict(_store.get(upload_id, {}))
