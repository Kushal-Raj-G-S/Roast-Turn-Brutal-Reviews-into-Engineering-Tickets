"""
LLM Service with cascading fallback across multiple providers.
Handles API failures, rate limits, and model unavailability gracefully.
"""

import os
import httpx
import logging
import time
import asyncio
from typing import Optional
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class ModelProvider(str, Enum):
    """LLM model configurations with fallback priority."""
    PRIMARY = "provider-3/deepseek-r1-0528"          # Best reasoning model
    FALLBACK_1 = "provider-2/deepseek-v3.1-tee"      # Fast reasoning alternative with TEE
    FALLBACK_2 = "provider-3/deepseek-v3"            # DeepSeek v3 stable
    FALLBACK_3 = "provider-3/llama-4-maverick"       # Strong general model
    FALLBACK_4 = "provider-2/gpt-oss-120b-tee"       # Large context, reliable


# Groq fallback models (used when ALL A4F models fail)
GROQ_MODELS = [
    "llama-3.3-70b-versatile",                        # Best overall
    "meta-llama/llama-4-maverick-17b-128e-instruct",  # Fast + powerful
    "qwen/qwen3-32b",                                 # Strong reasoning
    "llama-3.1-8b-instant",                           # Ultra-fast last resort
]
GROQ_API_URL = "https://api.groq.com/openai/v1"


class CircuitBreaker:
    """Circuit breaker to temporarily skip failing models."""
    
    def __init__(self, failure_threshold: int = 3, timeout_seconds: int = 300):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failures: Dict[str, int] = {}
        self.blocked_until: Dict[str, datetime] = {}
    
    def record_failure(self, model: str):
        """Record a failure for a model."""
        self.failures[model] = self.failures.get(model, 0) + 1
        if self.failures[model] >= self.failure_threshold:
            self.blocked_until[model] = datetime.now() + timedelta(seconds=self.timeout_seconds)
            logger.warning(f"Circuit breaker OPEN for {model} - blocked for {self.timeout_seconds}s")
    
    def record_success(self, model: str):
        """Reset failure count on success."""
        self.failures[model] = 0
        if model in self.blocked_until:
            del self.blocked_until[model]
    
    def is_blocked(self, model: str) -> bool:
        """Check if model is currently blocked."""
        if model not in self.blocked_until:
            return False
        if datetime.now() > self.blocked_until[model]:
            # Timeout expired, reset
            del self.blocked_until[model]
            self.failures[model] = 0
            return False
        return True


class LLMService:
    """Production-grade LLM service with intelligent fallback and rate limiting."""
    
    def __init__(self):
        self.api_key = os.getenv("A4F_API_KEY")
        self.api_url = os.getenv("A4F_API_URL", "https://api.a4f.co/v1")
        
        if not self.api_key:
            raise ValueError("A4F_API_KEY not found in environment variables")
        
        # Groq fallback credentials
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not set — Groq fallback disabled")
        self.groq_api_url = GROQ_API_URL
        self.groq_models = GROQ_MODELS
        self.groq_circuit_breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=120)
        
        self.models = [
            ModelProvider.PRIMARY,
            ModelProvider.FALLBACK_1,
            ModelProvider.FALLBACK_2,
            ModelProvider.FALLBACK_3,
            ModelProvider.FALLBACK_4,
        ]
        
        self.circuit_breaker = CircuitBreaker()
        self.timeout = 15.0  # 15 second timeout per request (FASTER)
        
        # Rate limiting: DISABLED for max speed (using fast models)
        self.rate_limit = 100  # Max requests per window (effectively unlimited)
        self.rate_window = 60.0  # Window in seconds (1 minute)
        self.request_timestamps: deque = deque()  # Track request times
        self._rate_limit_lock = asyncio.Lock()  # Thread-safe rate limiting
        
        logger.info(f"LLM Service initialized with {len(self.models)} A4F models + {len(self.groq_models)} Groq fallback models")
        logger.info(f"Rate limit: {self.rate_limit} requests per {self.rate_window}s")
    
    async def _wait_for_rate_limit(self):
        """
        Wait if necessary to respect rate limits (5 req/min).
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

    async def generate(self, prompt: str, max_tokens: int = 600) -> str:
        """
        Generic text generation with multi-model fallback.
        Tries A4F models first, then falls back to Groq if all A4F models fail.
        Returns the raw string response, or a fallback message on total failure.
        """
        # --- Tier 1: A4F models ---
        for model in self.models:
            model_name = model.value
            if self.circuit_breaker.is_blocked(model_name):
                continue
            await self._wait_for_rate_limit()
            try:
                response = await self._call_api(model_name, prompt)
                if response:
                    self.circuit_breaker.record_success(model_name)
                    return response
            except Exception as e:
                logger.warning(f"generate() failed on {model_name}: {e}")
                self.circuit_breaker.record_failure(model_name)

        # --- Tier 2: Groq fallback ---
        logger.warning("⚠️ All A4F models failed — switching to Groq fallback")
        for groq_model in self.groq_models:
            if self.groq_circuit_breaker.is_blocked(groq_model):
                continue
            try:
                response = await self._call_groq_api(groq_model, prompt, max_tokens)
                if response:
                    self.groq_circuit_breaker.record_success(groq_model)
                    logger.info(f"✅ Groq fallback succeeded with {groq_model}")
                    return response
            except Exception as e:
                logger.warning(f"generate() Groq fallback failed on {groq_model}: {e}")
                self.groq_circuit_breaker.record_failure(groq_model)

        logger.error("❌ All A4F and Groq models failed")
        return "AI explanation temporarily unavailable. Please try again in a moment."

    async def _call_groq_api(self, model: str, prompt: str, max_tokens: int = 600) -> Optional[str]:
        """Call Groq API (OpenAI-compatible). Single attempt, no retry — fail fast for fallback speed."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.groq_api_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert software engineer analyzing app reviews to identify root causes and suggest fixes."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": max_tokens,
                },
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                },
                timeout=30.0  # Groq is fast; 30s is generous
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content if content else None

    async def _call_api(self, model: str, prompt: str) -> Optional[str]:
        """Call A4F API with retry logic."""
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/chat/completions",
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are an expert software engineer analyzing app reviews to identify root causes and suggest fixes."
                                },
                                {
                                    "role": "user",
                                    "content": prompt
                                }
                            ],
                            "temperature": 0.3,  # Lower temp for more consistent analysis
                            "max_tokens": 500,  # REDUCED for faster responses
                        },
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        timeout=self.timeout
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Extract response content
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return content if content else None
                    
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retry {attempt + 1}/{max_retries} after {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
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


# For async context, need asyncio import
import asyncio
