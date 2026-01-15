"""
Roast LLM Router - Resilient Multi-Model Orchestration Service
===============================================================
Implements cascading fallback, retry logic, structured output parsing,
and comprehensive error handling for Root Cause Analysis generation.

Design Pattern: Strategy Pattern with Fallback Chain
"""

import os
import re
import time
from typing import List, Dict, Optional
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Load environment variables
load_dotenv()


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class ModelTimeoutError(Exception):
    """Raised when an LLM API call times out."""
    pass


class RateLimitError(Exception):
    """Raised when the API returns HTTP 429 (rate limited)."""
    pass


class ProviderDownError(Exception):
    """Raised when the provider returns HTTP 5xx (server error)."""
    pass


class InvalidRequestError(Exception):
    """Raised when the API returns HTTP 4xx (client error)."""
    pass


class JSONExtractionError(Exception):
    """Raised when JSON cannot be extracted from model response."""
    pass


class InvalidRCAFormatError(Exception):
    """Raised when the extracted JSON doesn't match RCAResult schema."""
    pass


class AllModelsFailedError(Exception):
    """Raised when all models in the fallback chain have failed."""
    pass


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class RCAResult(BaseModel):
    """
    Root Cause Analysis result from LLM.
    Strictly validated Pydantic model for structured output.
    """
    ticket_title: str = Field(
        ..., 
        min_length=5, 
        max_length=200,
        description="Concise technical title for the ticket"
    )
    root_cause_hypothesis: str = Field(
        ..., 
        min_length=10,
        description="Technical explanation of likely failure point"
    )
    reproduction_steps: List[str] = Field(
        default_factory=list,
        description="Steps to reproduce the issue"
    )
    technical_priority: str = Field(
        ...,
        pattern=r"^(Critical|High|Medium|Low)$",
        description="Priority level: Critical, High, Medium, or Low"
    )
    suggested_fix: str = Field(
        ..., 
        min_length=10,
        description="Actionable recommendation for engineers"
    )


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

@dataclass
class ModelConfig:
    """Configuration for an LLM model tier."""
    name: str
    provider: str
    tier: str
    timeout: int
    max_tokens: int


MODELS: List[ModelConfig] = [
    ModelConfig(
        name="deepseek-r1-0528",
        provider="provider-3",
        tier="reasoning",
        timeout=30,
        max_tokens=2048,
    ),
    ModelConfig(
        name="llama-3.3-70b-instruct",
        provider="provider-5",
        tier="general",
        timeout=20,
        max_tokens=1536,
    ),
    ModelConfig(
        name="qwen3-32b",
        provider="provider-5",
        tier="speed",
        timeout=15,
        max_tokens=1024,
    ),
]


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

RCA_SYSTEM_PROMPT = """You are a Senior Site Reliability Engineer and Product Analyst.

Your task: Analyze the following user complaints from an app and deduce the technical root cause.

**Output Format (Strict JSON):**
{
  "ticket_title": "Concise technical title (e.g., 'NullPointerException in Auth Flow')",
  "root_cause_hypothesis": "Technical explanation of likely failure point",
  "reproduction_steps": ["Step 1", "Step 2", ...],
  "technical_priority": "Critical" | "High" | "Medium" | "Low",
  "suggested_fix": "Actionable recommendation for engineers"
}

**Rules:**
- Output ONLY valid JSON.
- Do not include markdown formatting or commentary outside the JSON object.
- Base priority on: frequency (how many reviews) + severity (sentiment/rating)."""


# =============================================================================
# LLM ROUTER CLASS
# =============================================================================

class LLMRouter:
    """
    Resilient LLM orchestration service with cascading fallback.
    
    Implements the Strategy Pattern where each model is a strategy,
    and the router tries strategies sequentially until success.
    
    Features:
    - Automatic retry with exponential backoff
    - Cascading fallback across multiple models
    - Structured JSON extraction and validation
    - Comprehensive logging and error handling
    
    Example:
        router = LLMRouter()
        rca = await router.generate_rca([
            "App crashes on login",
            "Login page freezes",
            "Can't sign in anymore"
        ])
    """
    
    def __init__(self) -> None:
        """
        Initialize the LLM Router.
        
        Loads API credentials from environment, sets up HTTP client,
        and configures logging.
        
        Raises:
            ValueError: If A4F_API_KEY is not set in environment.
        """
        # Load API credentials
        self._api_key = os.getenv("A4F_API_KEY")
        self._base_url = os.getenv("A4F_API_URL", "https://api.a4f.co/v1")
        
        if not self._api_key:
            raise ValueError("A4F_API_KEY environment variable is not set")
        
        # Initialize async HTTP client
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        
        # Configure logging
        self._setup_logging()
        
        logger.info("LLMRouter initialized with {} models", len(MODELS))
    
    def _setup_logging(self) -> None:
        """
        Configure loguru for structured logging.
        
        Sets up file output to logs/llm.log with rotation and retention.
        """
        import sys
        from pathlib import Path
        
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Remove default handler and add custom ones
        logger.remove()
        
        # Console handler (INFO+)
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        )
        
        # File handler (DEBUG+)
        logger.add(
            log_dir / "llm.log",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            rotation="10 MB",
            retention="7 days",
            compression="zip",
        )
    
    def _build_payload(
        self, 
        model_config: ModelConfig, 
        system_prompt: str, 
        user_message: str
    ) -> Dict:
        """
        Construct the OpenAI-compatible API payload.
        
        Args:
            model_config: Configuration for the target model.
            system_prompt: System message setting the context.
            user_message: User message with the actual query.
        
        Returns:
            Dict containing the API request payload.
        """
        return {
            "model": f"{model_config.provider}/{model_config.name}",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "max_tokens": model_config.max_tokens,
            "response_format": {"type": "json_object"},
        }
    
    async def _call_api(
        self, 
        model_config: ModelConfig, 
        payload: Dict,
        attempt_number: int = 1
    ) -> str:
        """
        Make an API call to the LLM provider with retry logic.
        
        Uses tenacity for automatic retry with exponential backoff
        (2s, 4s, 8s) on transient failures.
        
        Args:
            model_config: Configuration for the target model.
            payload: The API request payload.
            attempt_number: Current attempt number for logging.
        
        Returns:
            The raw response content from the model.
        
        Raises:
            ModelTimeoutError: If the request times out.
            RateLimitError: If rate limited (HTTP 429).
            ProviderDownError: If server error (HTTP 5xx).
            InvalidRequestError: If client error (HTTP 4xx).
        """
        model_name = model_config.name
        start_time = time.time()
        
        logger.info(
            "Calling {} (attempt {}, timeout={}s)...",
            model_name, attempt_number, model_config.timeout
        )
        
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                timeout=httpx.Timeout(float(model_config.timeout)),
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug(
                "Response from {}: status={}, latency={:.0f}ms",
                model_name, response.status_code, elapsed_ms
            )
            
            # Handle HTTP errors
            if response.status_code == 429:
                logger.warning("{} rate limited (429)", model_name)
                raise RateLimitError(f"{model_name} rate limited")
            
            if response.status_code >= 500:
                logger.warning("{} server error ({})", model_name, response.status_code)
                raise ProviderDownError(f"{model_name} returned {response.status_code}")
            
            if response.status_code >= 400:
                error_detail = response.text[:200]
                logger.error("{} client error ({}): {}", model_name, response.status_code, error_detail)
                raise InvalidRequestError(f"{model_name} returned {response.status_code}: {error_detail}")
            
            # Extract content
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            logger.debug("{} response length: {} chars", model_name, len(content))
            return content
            
        except httpx.TimeoutException as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning(
                "{} timed out after {:.0f}ms: {}",
                model_name, elapsed_ms, str(e)
            )
            raise ModelTimeoutError(f"{model_name} timed out after {elapsed_ms:.0f}ms")
        
        except httpx.RequestError as e:
            logger.error("{} request error: {}", model_name, str(e))
            raise ProviderDownError(f"{model_name} request failed: {e}")
    
    async def _call_api_with_retry(
        self, 
        model_config: ModelConfig, 
        payload: Dict
    ) -> str:
        """
        Call API with tenacity retry wrapper.
        
        Retries up to 3 times with exponential backoff (2s, 4s, 8s)
        on transient failures (timeout, rate limit, provider down).
        
        Args:
            model_config: Configuration for the target model.
            payload: The API request payload.
        
        Returns:
            The raw response content from the model.
        
        Raises:
            ModelTimeoutError: If all retries time out.
            RateLimitError: If rate limited after all retries.
            ProviderDownError: If server error after all retries.
            InvalidRequestError: If client error (no retry).
        """
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=8),
            retry=retry_if_exception_type((ModelTimeoutError, RateLimitError, ProviderDownError)),
            reraise=True,
        )
        async def _inner() -> str:
            return await self._call_api(model_config, payload)
        
        return await _inner()
    
    def _clean_json(self, raw_text: str) -> str:
        """
        Extract clean JSON from potentially messy model output.
        
        Handles common model behaviors:
        - JSON wrapped in markdown code fences
        - JSON preceded/followed by commentary text
        - Nested JSON objects
        
        Args:
            raw_text: Raw response text from the model.
        
        Returns:
            Clean JSON string.
        
        Raises:
            JSONExtractionError: If no valid JSON can be extracted.
        """
        text = raw_text.strip()
        
        # Try 1: Direct parse (already clean JSON)
        if text.startswith("{") and text.endswith("}"):
            return text
        
        # Try 2: Extract from markdown code fences
        code_fence_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        fence_match = re.search(code_fence_pattern, text)
        if fence_match:
            extracted = fence_match.group(1).strip()
            if extracted.startswith("{"):
                logger.debug("Extracted JSON from code fence")
                return extracted
        
        # Try 3: Find JSON object with regex (handles nested braces)
        json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
        json_match = re.search(json_pattern, text, re.DOTALL)
        if json_match:
            extracted = json_match.group(0)
            logger.debug("Extracted JSON via regex pattern")
            return extracted
        
        # Try 4: Find anything between first { and last }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            extracted = text[first_brace:last_brace + 1]
            logger.debug("Extracted JSON via brace matching")
            return extracted
        
        # Failed to extract
        logger.error("Failed to extract JSON from response: {}", text[:200])
        raise JSONExtractionError(f"Could not extract JSON from response: {text[:100]}...")
    
    def _validate_rca(self, json_str: str) -> RCAResult:
        """
        Validate extracted JSON against the RCAResult schema.
        
        Uses Pydantic V2's strict validation to ensure the response
        matches the expected structure.
        
        Args:
            json_str: Clean JSON string to validate.
        
        Returns:
            Validated RCAResult instance.
        
        Raises:
            InvalidRCAFormatError: If validation fails.
        """
        try:
            return RCAResult.model_validate_json(json_str)
        except ValidationError as e:
            logger.error("RCA validation failed: {}", str(e))
            logger.debug("Raw JSON that failed validation: {}", json_str[:500])
            raise InvalidRCAFormatError(f"Invalid RCA format: {e}")
    
    async def generate_rca(self, reviews: List[str]) -> RCAResult:
        """
        Generate Root Cause Analysis from a list of user reviews.
        
        Implements cascading fallback: tries each model in sequence
        until one succeeds. Handles all failure modes gracefully.
        
        Args:
            reviews: List of user review texts to analyze.
                    Only the first 10 reviews are used to limit context.
        
        Returns:
            RCAResult containing the structured analysis.
        
        Raises:
            AllModelsFailedError: If all models fail to generate valid RCA.
        
        Example:
            rca = await router.generate_rca([
                "App crashes every time I try to export",
                "Export feature is completely broken",
                "Can't export my data, app freezes"
            ])
            print(rca.ticket_title)
            # "Export Feature Causes Application Crash"
        """
        # Prepare input: limit to first 10 reviews
        limited_reviews = reviews[:10]
        user_message = "\n---\n".join(limited_reviews)
        
        logger.info(
            "Generating RCA for {} reviews (using {} models)",
            len(limited_reviews), len(MODELS)
        )
        
        errors_encountered: List[str] = []
        
        # Fallback loop through models
        for model in MODELS:
            model_name = model.name
            
            try:
                # Build payload
                payload = self._build_payload(model, RCA_SYSTEM_PROMPT, user_message)
                
                # Call API with retry
                raw_response = await self._call_api_with_retry(model, payload)
                
                # Extract and clean JSON
                clean_json = self._clean_json(raw_response)
                
                # Validate against schema
                rca = self._validate_rca(clean_json)
                
                logger.success("✓ RCA generated using {} (tier: {})", model_name, model.tier)
                return rca
                
            except (ModelTimeoutError, RateLimitError, ProviderDownError) as e:
                error_msg = f"{model_name}: {type(e).__name__} - {str(e)}"
                errors_encountered.append(error_msg)
                logger.warning("✗ {} failed: {}. Trying next model...", model_name, e)
                continue
                
            except JSONExtractionError as e:
                error_msg = f"{model_name}: JSONExtractionError - {str(e)}"
                errors_encountered.append(error_msg)
                logger.warning("✗ {} returned unparseable response. Trying next...", model_name)
                continue
                
            except InvalidRCAFormatError as e:
                error_msg = f"{model_name}: InvalidRCAFormatError - {str(e)}"
                errors_encountered.append(error_msg)
                logger.error("✗ {} returned invalid JSON structure. Trying next...", model_name)
                continue
                
            except InvalidRequestError as e:
                error_msg = f"{model_name}: InvalidRequestError - {str(e)}"
                errors_encountered.append(error_msg)
                logger.error("✗ {} rejected request: {}. Trying next...", model_name, e)
                continue
        
        # All models failed
        logger.critical(
            "All {} models failed. Errors: {}",
            len(MODELS), "; ".join(errors_encountered)
        )
        raise AllModelsFailedError(
            f"All {len(MODELS)} models failed to generate RCA. "
            f"Errors: {'; '.join(errors_encountered)}"
        )
    
    async def close(self) -> None:
        """
        Close the HTTP client gracefully.
        
        Should be called when shutting down the application
        to release connection resources.
        """
        await self._client.aclose()
        logger.info("LLMRouter closed")
    
    async def __aenter__(self) -> "LLMRouter":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Global router instance (lazy initialization)
_router_instance: Optional[LLMRouter] = None


async def get_llm_router() -> LLMRouter:
    """
    Get or create the global LLMRouter instance.
    
    Used for dependency injection in FastAPI.
    
    Returns:
        The singleton LLMRouter instance.
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = LLMRouter()
    return _router_instance


async def generate_rca_from_reviews(reviews: List[str]) -> RCAResult:
    """
    Convenience function to generate RCA without managing router lifecycle.
    
    Args:
        reviews: List of user review texts to analyze.
    
    Returns:
        RCAResult containing the structured analysis.
    
    Example:
        from app.llm import generate_rca_from_reviews
        
        rca = await generate_rca_from_reviews([
            "App crashes on startup",
            "Can't open the app anymore"
        ])
    """
    router = await get_llm_router()
    return await router.generate_rca(reviews)
