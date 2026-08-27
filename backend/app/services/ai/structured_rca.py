"""
Structured RCA output via Instructor — the LLM is forced to return a
validated Pydantic object instead of free-form text we then regex/guess our
way through. If the model's output doesn't fit the schema, Instructor
automatically retries with the validation error fed back to the model.
"""

import logging
import os
from typing import Optional

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

NVIDIA_API_URL = os.getenv("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1")
# See llm_service.py for why this default changed -- the old one is EOL'd.
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")


class RootCauseHypothesis(BaseModel):
    likelihood: str = Field(description="high | medium | low")
    scope: str = Field(description="functional | performance | UX | monetization | stability | unknown")
    explanation: str = Field(description="2-4 sentences grounded in the provided review evidence")
    suggested_severity: str = Field(description="CRITICAL | HIGH | MEDIUM | LOW")
    severity_reason: str = Field(description="1-2 sentences justifying the suggested severity")


class AffectedSurface(BaseModel):
    client_ui: str = ""
    client_logic: str = ""
    network_api: str = ""
    backend_service: str = ""
    config_experiments: str = ""


class StructuredRCA(BaseModel):
    """The full 7-section RCA, machine-validated instead of hand-parsed."""

    hypothesis: RootCauseHypothesis
    affected_surface: AffectedSurface
    reproduction_steps: list[str] = Field(description="Minimal numbered repro steps, assumptions marked explicitly")
    diagnostic_checklist: list[str] = Field(description="What logs/metrics/flags an engineer should check first")
    suggested_fix: str = Field(description="Concrete, actionable fix recommendation")
    prevention: str = Field(description="Tests or monitoring that would have caught this earlier")
    notes: str = Field(default="", description="Uncertainties or additional data needed")
    confidence: float = Field(ge=0.0, le=1.0, description="Model's own confidence in this analysis, 0-1")


_client: Optional[object] = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError("NVIDIA_API_KEY not set — cannot generate structured RCA")
        raw_client = AsyncOpenAI(base_url=NVIDIA_API_URL, api_key=api_key)
        # instructor.from_openai patches the client so response_model= "just works".
        # TOOLS mode (native function-calling) is far more reliable than JSON mode
        # for smaller models like an 8B instruct model — JSON mode occasionally had
        # the model echo the schema itself back instead of filling it in.
        _client = instructor.from_openai(raw_client, mode=instructor.Mode.TOOLS)
    return _client


async def generate_structured_rca(prompt: str, max_retries: int = 2) -> StructuredRCA:
    """
    Calls the NVIDIA model through Instructor with response_model=StructuredRCA.
    Raises on total failure — callers should catch and fall back to the
    plain-text RCA path.
    """
    client = _get_client()
    result = await client.chat.completions.create(
        model=NVIDIA_MODEL,
        response_model=StructuredRCA,
        max_retries=max_retries,
        temperature=0.2,
        # 1800 was fine for the original 8B instruct model; the current
        # reasoning model (nemotron-3-super-120b-a12b) spends a real chunk
        # of the budget on hidden chain-of-thought before the structured
        # output, and was observed truncating under real load ("Structured
        # finalize failed... using draft hypothesis as fallback" -- see
        # NEW_ARCHITECTURE_CHANGES.md). Matches the budget repro_stub_
        # generator.py needed for the same reason.
        max_tokens=3000,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior mobile/full-stack engineer performing root cause analysis "
                    "on production issues surfaced from app store reviews. Ground every claim in "
                    "the evidence given. Never invent specific modules or SDKs unless clearly implied."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return result
