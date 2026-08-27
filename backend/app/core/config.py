"""
Configuration module for Roast bulk processing pipeline.
Loads settings from environment variables with sensible defaults.
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration for bulk review processing."""
    
    # Database
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it in your .env file (see README.md)."
        )
    
    # Embedding model
    MODEL_NAME: str = os.getenv(
        "MODEL_NAME",
        "paraphrase-MiniLM-L3-v2"  # Fast, small model (128 dims)
    )
    
    # Batch processing
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "128"))  # Reduced from 256 to prevent crashes
    NUM_WORKERS: int = int(os.getenv("NUM_WORKERS", "1"))  # Single worker to prevent multiprocessing crashes
    
    # Clustering parameters
    COSINE_THRESHOLD: float = float(os.getenv("COSINE_THRESHOLD", "0.3"))
    MIN_TEXT_LENGTH: int = int(os.getenv("MIN_TEXT_LENGTH", "25"))
    
    # Noise filtering
    MIN_SCORE_FOR_NOISE: int = 4  # Reviews >= 4 stars can be marked as noise
    
    # Background worker
    WORKER_POLL_INTERVAL: int = int(os.getenv("WORKER_POLL_INTERVAL", "5"))  # seconds
    
    # File uploads
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))

    # Base URL of the deployed frontend -- used to build a real clickable
    # link in outbound alerts (Discord/Slack) so "Upload #45" is actually
    # reachable instead of an opaque internal id.
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # Negative keywords (reviews with these are NEVER noise)
    NEGATIVE_KEYWORDS = [
        "crash", "crashes", "bug", "error", "issue", "not working",
        "not opening", "lag", "slow", "subscription", "paid", "cant",
        "doesn't", "problem", "annoying", "glitch", "freezes", "stuck",
        "broken", "fix", "terrible", "horrible", "awful", "worst",
        "hate", "bad", "useless", "waste", "refund", "delete"
    ]
    
    # Positive-only patterns (noise if ONLY these appear)
    POSITIVE_PATTERNS = [
        "good", "nice", "best", "very good", "superb", "amazing",
        "helpful", "awesome", "love this app", "great", "excellent",
        "perfect", "fantastic", "wonderful", "outstanding"
    ]
    
    @classmethod
    def ensure_upload_dir(cls):
        """Create upload directory if it doesn't exist."""
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)


config = Config()
