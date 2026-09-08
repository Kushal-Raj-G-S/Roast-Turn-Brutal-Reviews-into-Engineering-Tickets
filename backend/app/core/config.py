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

    # Web Push (browser push notifications) -- self-generated VAPID keypair,
    # no third-party push service, no cost. Stored as the raw 32-byte EC
    # private scalar, base64url-encoded (pywebpush's Vapid.from_string()
    # only accepts this raw form or a headerless base64url DER blob --
    # NOT a normal PEM string, which it fails to parse despite looking
    # like a reasonable thing to pass it).
    VAPID_PRIVATE_KEY: Optional[str] = os.getenv("VAPID_PRIVATE_KEY")
    VAPID_PUBLIC_KEY: Optional[str] = os.getenv("VAPID_PUBLIC_KEY")
    VAPID_SUBJECT: str = os.getenv("VAPID_SUBJECT", "mailto:admin@roast.systems")

    # Email (Resend) -- free tier, 3000 emails/month, no card required.
    # RESEND_FROM_EMAIL defaults to Resend's shared onboarding domain, which
    # sends immediately with zero DNS setup.
    RESEND_API_KEY: Optional[str] = os.getenv("RESEND_API_KEY")
    RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "Roast <onboarding@resend.dev>")
    
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
    
    # ------------------------------------------------------------------
    # Data platform: Kafka ingest, GCS staging, BigQuery warehouse
    # ------------------------------------------------------------------
    # Event bus backend: "memory" (dev), "redis", or "kafka" (production).
    # Selects which IMessageQueue implementation create_event_bus() builds.
    EVENT_BUS_BACKEND: str = os.getenv("EVENT_BUS_BACKEND", "memory")

    # Start the event consumers (src/infrastructure/messaging/consumers.py)
    # at app startup. Default OFF because the consumers require the
    # processed_events inbox table — run
    # migrations/create_processed_events.sql first, then enable. Turning
    # this on before the migration would make every consumed event fail
    # into the DLQ.
    EVENT_CONSUMERS_ENABLED: bool = os.getenv(
        "EVENT_CONSUMERS_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Kafka. Works against any Kafka-protocol broker: a local Docker broker
    # (PLAINTEXT) or a managed one such as Upstash/Confluent (SASL_SSL).
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "roast-workers")
    KAFKA_SECURITY_PROTOCOL: str = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    KAFKA_SASL_MECHANISM: Optional[str] = os.getenv("KAFKA_SASL_MECHANISM")
    KAFKA_SASL_USERNAME: Optional[str] = os.getenv("KAFKA_SASL_USERNAME")
    KAFKA_SASL_PASSWORD: Optional[str] = os.getenv("KAFKA_SASL_PASSWORD")

    # GCP. GCS holds inter-stage Parquet payloads (embeddings are far too
    # large to pass through Airflow XCom); BigQuery is the analytical sink.
    GCP_PROJECT_ID: Optional[str] = os.getenv("GCP_PROJECT_ID")
    GCS_STAGING_BUCKET: Optional[str] = os.getenv("GCS_STAGING_BUCKET")
    BIGQUERY_DATASET: str = os.getenv("BIGQUERY_DATASET", "roast_warehouse")
    BIGQUERY_LOCATION: str = os.getenv("BIGQUERY_LOCATION", "US")

    # Tags pipeline runs so the dbt regression model can diff v1/v2/v3
    # shadow deployments against each other.
    PIPELINE_VERSION: str = os.getenv("PIPELINE_VERSION", "v1")

    @classmethod
    def event_bus_kwargs(cls) -> dict:
        """Backend-specific kwargs for create_event_bus(cls.EVENT_BUS_BACKEND, **kwargs)."""
        if cls.EVENT_BUS_BACKEND == "kafka":
            return {
                "bootstrap_servers": cls.KAFKA_BOOTSTRAP_SERVERS,
                "consumer_group": cls.KAFKA_CONSUMER_GROUP,
                "security_protocol": cls.KAFKA_SECURITY_PROTOCOL,
                "sasl_mechanism": cls.KAFKA_SASL_MECHANISM,
                "sasl_username": cls.KAFKA_SASL_USERNAME,
                "sasl_password": cls.KAFKA_SASL_PASSWORD,
            }
        if cls.EVENT_BUS_BACKEND == "redis":
            return {"redis_url": os.getenv("REDIS_URL", "redis://localhost:6379")}
        return {}

    @classmethod
    def require_gcp(cls) -> None:
        """Fail fast with a clear message rather than deep inside a GCP client call."""
        missing = [
            name for name in ("GCP_PROJECT_ID", "GCS_STAGING_BUCKET")
            if not getattr(cls, name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required GCP settings: {', '.join(missing)}. "
                "Set them in .env — see docs/PLATFORM_REARCHITECTURE.md."
            )

    @classmethod
    def ensure_upload_dir(cls):
        """Create upload directory if it doesn't exist."""
        os.makedirs(cls.UPLOAD_DIR, exist_ok=True)


config = Config()
