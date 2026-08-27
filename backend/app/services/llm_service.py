"""
LLM service backed by NVIDIA's OpenAI-compatible endpoint.

The rest of the backend keeps calling ``generate(prompt, max_tokens=...)``;
this service now routes all analysis through the NVIDIA model configured in
the environment.
"""

import asyncio
import logging
import os
import time
from collections import deque
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

NVIDIA_API_URL = os.getenv("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1")
# meta/llama-3.1-8b-instruct reached end-of-life on NVIDIA's side on
# 2026-08-26 and now 410s on every call. nemotron-3-super-120b-a12b is
# verified (2026-08-27) to support both plain generation and Instructor
# structured/tool-calling output on this account's catalog -- several other
# candidates that answer fine (e.g. meta/llama-3.2-11b-vision-instruct)
# return a non-OpenAI-compatible tool-call format Instructor can't parse, and
# a "smaller/faster" alternative (nemotron-3.5-lightning-30b-a3b) was
# measured SLOWER and less reliable in the full 5-step RCA agent pipeline
# (64-118s per cluster, one outright truncation failure) than this one
# (~15-45s per cluster once warm). See NEW_ARCHITECTURE_CHANGES.md.
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")

# Sentinel returned by generate() on total failure. Exposed as a constant so
# callers can distinguish "the model actually said this" from "the call
# failed" instead of treating this string as real generated content.
FALLBACK_MESSAGE = "AI explanation temporarily unavailable. Please try again in a moment."


def _persona_style_instructions(persona_label: Optional[str]) -> str:
    """
    Concrete, family-specific reasoning-style directives for the debug-center
    playground's "model style" picker. "Write like {name}" alone is too
    vague for a small model to actually act on -- it can't imitate a model
    it's never seen. These instead describe an observable STRUCTURAL trait
    real users associate with each family (terse vs step-by-step vs hedged,
    etc.), which the model genuinely can follow, so different picks produce
    differently-shaped answers instead of the same paragraph with a
    different name pasted at the top.
    """
    if not persona_label:
        return ""
    p = persona_label.lower()
    if "deepseek" in p or "qwq" in p or "r1" in p or "reasoning" in p:
        return (
            "Think step-by-step out loud before concluding: lay out 2-3 numbered "
            "intermediate reasoning steps, then state the final root cause explicitly "
            "on its own line."
        )
    if "mistral" in p or "mixtral" in p:
        return "Be terse and efficient: short declarative sentences only, no hedging, no filler."
    if "gemma" in p or "google" in p:
        return (
            "Be cautious about uncertainty: explicitly flag where the evidence is thin using "
            "phrases like 'it's possible that' or 'this can't be confirmed from the review alone', "
            "rather than asserting a single cause flatly."
        )
    if "gpt-oss" in p or "openai" in p:
        return "Be confident and direct: state the single most likely cause in the first sentence, then justify it in one more."
    if "nemotron" in p or "nvidia" in p:
        return "Frame the explanation in systems terms — name the likely subsystem, API layer, cache, or resource involved, not just 'a bug'."
    if "glm" in p or "zhipu" in p:
        return "Enumerate 2-3 plausible causes as a short ranked list first, then state which is most likely and why."
    if "kimi" in p or "moonshot" in p:
        return "Explain it conversationally, as if narrating the likely sequence of events to a teammate over chat."
    if "granite" in p or "ibm" in p:
        return "Use a formal, enterprise tone and explicitly name the business/user impact and risk level."
    if "jamba" in p or "ai21" in p:
        return "Consider the problem from two different angles (e.g. client-side vs server-side) before picking one as most likely."
    if "yi" in p or "qwen" in p:
        return "Be balanced: briefly acknowledge one alternative explanation before committing to the most likely one."
    return "Reason in your own distinct voice — do not imitate a generic template response."


def _temperature_instruction(effective_temperature: float) -> str:
    """Concrete (not just adjective) behavioral directive tied to temperature."""
    if effective_temperature >= 0.6:
        return "Be exploratory: name at least one non-obvious or unconventional explanation in addition to the likely one."
    if effective_temperature >= 0.35:
        return "Allow moderate speculation beyond the literal text where it's reasonable."
    return "Be strict and literal: state only what the evidence directly supports, with no speculation."


class LLMService:
    """Production-grade LLM service with rate limiting and NVIDIA inference."""

    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY")

        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not found in environment variables")

        self.api_url = NVIDIA_API_URL
        self.model = NVIDIA_MODEL
        self.timeout = 15.0  # 15 second timeout per request

        # This was previously set but never actually passed to the client --
        # dead code. With no client-side timeout, a slow/unresponsive model
        # (e.g. an invalid model id whose gateway hangs instead of failing
        # fast) could block for the SDK's own default (10 minutes), not 15s.
        # Discovered while testing the debug-center playground against
        # several bad model ids: one hung the test script for minutes.
        #
        # max_retries=0: the SDK client retries internally by default (its
        # own default is 2), which nests INSIDE _call_nvidia_api's own
        # 2-attempt retry loop below -- under real load (NVIDIA returning
        # 503s during a heavy background RCA batch) the two retry layers
        # stacked to 64s before a single test-stub click finally failed,
        # instead of failing in a predictable ~30s. We already retry at our
        # own layer with backoff; retrying at both layers only multiplies
        # worst-case latency without adding real resilience.
        self.client = AsyncOpenAI(base_url=self.api_url, api_key=self.api_key, timeout=self.timeout, max_retries=0)

        # NVIDIA's free-tier account limit is 40 requests/min (confirmed by
        # the client) -- 35 leaves headroom so we self-throttle BEFORE
        # hitting NVIDIA's own 429s, instead of just reacting to them. This
        # only works because every caller shares ONE LLMService instance
        # (via get_llm_service()) -- a fresh instance starts an empty
        # window and can't see what other concurrent calls already sent.
        self.rate_limit = 35
        self.rate_window = 60.0
        self.request_timestamps: deque[float] = deque()
        self._rate_limit_lock = asyncio.Lock()

        logger.info(f"LLM Service initialized with NVIDIA model {self.model}")
        logger.info(f"Rate limit: {self.rate_limit} requests per {self.rate_window}s")
    
    async def _wait_for_rate_limit(self):
        """
        Wait if necessary to respect rate limits.
        Uses sliding window algorithm.
        """
        async with self._rate_limit_lock:
            now = time.time()
            
            # Remove timestamps outside the current window
            while self.request_timestamps and self.request_timestamps[0] < now - self.rate_window:
                self.request_timestamps.popleft()
            
            # Check if we've hit the rate limit
            if len(self.request_timestamps) >= self.rate_limit:
                # Calculate wait time until oldest request expires
                oldest_request = self.request_timestamps[0]
                wait_time = self.rate_window - (now - oldest_request)
                
                if wait_time > 0:
                    logger.warning(
                        f"⏱️  Rate limit reached ({self.rate_limit}/{self.rate_window}s). "
                        f"Waiting {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)
                    # Clean up again after waiting
                    now = time.time()
                    while self.request_timestamps and self.request_timestamps[0] < now - self.rate_window:
                        self.request_timestamps.popleft()
            
            # Record this request
            self.request_timestamps.append(time.time())

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 600,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        persona_label: Optional[str] = None,
    ) -> str:
        """
        Generic text generation through the NVIDIA model.
        Returns the raw string response, or a fallback message on total failure.
        `temperature` genuinely changes sampling. `model` genuinely changes
        which model is actually called -- use with care: most model ids on
        NVIDIA's public catalog are NOT invokable on every account/key (an
        earlier version of the debug-center playground called `model=`
        directly with 19 "popular" ids and 16 of them 404/410'd or hung,
        wasting real time on every single run). `persona_label` is the safe
        alternative for a UI that wants to offer many "model" choices without
        that risk: it never touches the real API `model` field, it only
        flavors the system prompt so the one real (fast, verified) model
        writes in a different voice per label.
        """
        await self._wait_for_rate_limit()
        try:
            response = await self._call_nvidia_api(
                prompt, max_tokens, model=model, temperature=temperature, persona_label=persona_label
            )
            if response:
                return response
        except Exception as e:
            logger.warning(f"generate() NVIDIA call failed on {model or self.model}: {e}")

        logger.error("❌ NVIDIA model failed")
        return FALLBACK_MESSAGE

    async def _call_nvidia_api(
        self,
        prompt: str,
        max_tokens: int = 600,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        persona_label: Optional[str] = None,
    ) -> Optional[str]:
        """Call NVIDIA's OpenAI-compatible API with a small retry window."""
        max_retries = 2
        effective_model = model or self.model
        effective_temperature = 0.2 if temperature is None else temperature

        system_content = "You are an expert software engineer analyzing app reviews to identify root causes and suggest fixes."
        # Only append this when the caller explicitly asked for a persona or
        # overrode temperature (i.e. the debug-center playground) --
        # production RCA calls always pass neither, so this never changes
        # their behavior. Without it, different temperature/persona choices
        # can produce suspiciously similar output since the prompt itself
        # never signals that anything should differ. Each directive below is
        # a concrete, followable behavior (not just "sound like X"), which is
        # what actually makes a small model's output structurally different.
        if persona_label is not None or temperature is not None:
            persona_instruction = _persona_style_instructions(persona_label)
            temp_instruction = _temperature_instruction(effective_temperature)
            system_content += (
                f" {persona_instruction} {temp_instruction} "
                f"(Style reference: {persona_label or effective_model}. Temperature: {effective_temperature:.1f}.)"
            )

        for attempt in range(max_retries):
            try:
                completion = await self.client.chat.completions.create(
                    model=effective_model,
                    messages=[
                        {
                            "role": "system",
                            "content": system_content,
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    temperature=effective_temperature,
                    top_p=0.7,
                    max_tokens=max_tokens,
                    stream=False,
                )

                if completion.choices:
                    content = completion.choices[0].message.content
                    return content if content else None
                return None

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        return None
    

# Global instance (initialized lazily)
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create global LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
