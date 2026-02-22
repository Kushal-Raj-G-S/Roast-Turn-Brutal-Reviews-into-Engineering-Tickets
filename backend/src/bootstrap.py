"""
Application Bootstrap & Dependency Injection Setup
Wires up all components for production deployment.
"""

import logging
import os
from typing import Optional

from src.infrastructure.dependency_injection import DependencyContainer, ServiceLifetime
from src.infrastructure.messaging.event_bus import create_event_bus, EventBus
from src.infrastructure.embeddings.providers import SentenceTransformerProvider, OpenAIEmbeddingProvider
from src.infrastructure.embeddings.vector_stores import FAISSVectorStore, PineconeVectorStore, QdrantVectorStore
from src.infrastructure.clustering.engines import FAISSClusteringEngine, HDBSCANClusteringEngine
from src.infrastructure.ml.actionability_scorer import MLActionabilityScorer, RuleBasedActionabilityScorer
from src.infrastructure.ml.hybrid_scorer import HybridActionabilityScorer
from src.infrastructure.ranking.strategies import SeverityBasedRankingStrategy

from src.domain.services import (
    IEmbeddingProvider, IVectorStore, IClusteringEngine,
    IActionabilityScorer, IRankingStrategy
)

logger = logging.getLogger(__name__)


class ApplicationConfig:
    """
    Centralized configuration for the application.
    Reads from environment variables with sensible defaults.
    """
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost/roast")
    
    # Feature Flags
    ML_SCORING_ENABLED: bool = os.getenv("ML_SCORING_ENABLED", "false").lower() == "true"
    ML_SCORER_TYPE: str = os.getenv("ML_SCORER_TYPE", "hybrid")  # hybrid, ml, rule_based
    ML_MODEL_DIR: str = os.getenv("ML_MODEL_DIR", "./models/actionability")
    ACTIONABILITY_THRESHOLD: float = float(os.getenv("ACTIONABILITY_THRESHOLD", "0.5"))
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
    ENABLE_ONLINE_LEARNING: bool = os.getenv("ENABLE_ONLINE_LEARNING", "true").lower() == "true"
    AI_ANALYSIS_ENABLED: bool = os.getenv("AI_ANALYSIS_ENABLED", "true").lower() == "true"
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    
    # Embedding Configuration
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "paraphrase-MiniLM-L3-v2")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # Vector Store Configuration
    VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "faiss_local")
    PINECONE_API_KEY: Optional[str] = os.getenv("PINECONE_API_KEY")
    PINECONE_ENV: Optional[str] = os.getenv("PINECONE_ENV")
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: Optional[str] = os.getenv("QDRANT_API_KEY")
    
    # Clustering Configuration
    CLUSTERING_ENGINE: str = os.getenv("CLUSTERING_ENGINE", "faiss")
    CLUSTERING_THRESHOLD: float = float(os.getenv("CLUSTERING_THRESHOLD", "0.3"))
    MIN_CLUSTER_SIZE: int = int(os.getenv("MIN_CLUSTER_SIZE", "1"))
    
    # Message Queue Configuration
    MESSAGE_QUEUE_BACKEND: str = os.getenv("MESSAGE_QUEUE", "memory")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Performance Configuration
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "128"))
    NUM_WORKERS: int = int(os.getenv("NUM_WORKERS", "4"))
    ENABLE_GPU: bool = os.getenv("ENABLE_GPU", "false").lower() == "true"
    
    # Worker Configuration
    WORKER_POLL_INTERVAL: int = int(os.getenv("WORKER_POLL_INTERVAL", "5"))
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))
    
    # File Upload
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
    
    # Observability
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENABLE_TRACING: bool = os.getenv("ENABLE_TRACING", "false").lower() == "true"
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "true").lower() == "true"


def configure_logging(config: ApplicationConfig):
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger.info("Logging configured")


def create_embedding_provider(config: ApplicationConfig) -> IEmbeddingProvider:
    """Factory for embedding provider based on configuration."""
    if config.EMBEDDING_PROVIDER == "openai":
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY required for OpenAI provider")
        logger.info("Using OpenAI embedding provider")
        return OpenAIEmbeddingProvider(
            api_key=config.OPENAI_API_KEY,
            model_name=config.EMBEDDING_MODEL,
            cache_enabled=config.CACHE_ENABLED
        )
    else:
        logger.info(f"Using Sentence Transformer provider: {config.EMBEDDING_MODEL}")
        return SentenceTransformerProvider(
            model_name=config.EMBEDDING_MODEL,
            cache_enabled=config.CACHE_ENABLED,
            batch_size=config.BATCH_SIZE,
            num_workers=config.NUM_WORKERS
        )


def create_vector_store(config: ApplicationConfig) -> IVectorStore:
    """Factory for vector store based on configuration."""
    backend = config.VECTOR_BACKEND
    
    if backend == "faiss_local" or backend == "faiss":
        logger.info("Using FAISS local vector store")
        return FAISSVectorStore(use_gpu=config.ENABLE_GPU)
    
    elif backend == "pinecone":
        if not config.PINECONE_API_KEY or not config.PINECONE_ENV:
            raise ValueError("PINECONE_API_KEY and PINECONE_ENV required")
        logger.info("Using Pinecone vector store")
        return PineconeVectorStore(
            api_key=config.PINECONE_API_KEY,
            environment=config.PINECONE_ENV
        )
    
    elif backend == "qdrant":
        logger.info(f"Using Qdrant vector store: {config.QDRANT_URL}")
        return QdrantVectorStore(
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY
        )
    
    else:
        raise ValueError(f"Unsupported vector backend: {backend}")


def create_clustering_engine(config: ApplicationConfig) -> IClusteringEngine:
    """Factory for clustering engine based on configuration."""
    engine = config.CLUSTERING_ENGINE
    
    if engine == "faiss":
        logger.info("Using FAISS clustering engine")
        return FAISSClusteringEngine(metric="cosine")
    
    elif engine == "hdbscan":
        logger.info("Using HDBSCAN clustering engine")
        return HDBSCANClusteringEngine(
            min_cluster_size=config.MIN_CLUSTER_SIZE
        )
    
    else:
        raise ValueError(f"Unsupported clustering engine: {engine}")


def create_actionability_scorer(config: ApplicationConfig) -> IActionabilityScorer:
    """Factory for actionability scorer."""
    scorer_type = config.ML_SCORER_TYPE if config.ML_SCORING_ENABLED else "rule_based"
    
    if scorer_type == "hybrid":
        logger.info("Using hybrid actionability scorer (rule-based + ML ensemble)")
        return HybridActionabilityScorer(
            threshold=config.ACTIONABILITY_THRESHOLD,
            confidence_threshold=config.CONFIDENCE_THRESHOLD,
            model_dir=config.ML_MODEL_DIR,
            enable_online_learning=config.ENABLE_ONLINE_LEARNING
        )
    elif scorer_type == "ml":
        logger.info("Using ML actionability scorer")
        return MLActionabilityScorer(
            threshold=config.ACTIONABILITY_THRESHOLD,
            model_path=os.path.join(config.ML_MODEL_DIR, "actionability_model.pkl")
        )
    else:
        logger.info("Using rule-based actionability scorer")
        return RuleBasedActionabilityScorer(threshold=config.ACTIONABILITY_THRESHOLD)


def create_ranking_strategy(config: ApplicationConfig) -> IRankingStrategy:
    """Factory for ranking strategy."""
    logger.info("Using severity-based ranking strategy")
    return SeverityBasedRankingStrategy()


def setup_container(config: ApplicationConfig) -> DependencyContainer:
    """
    Setup dependency injection container with all services.
    
    This is the composition root - where all dependencies are wired together.
    """
    container = DependencyContainer()
    
    logger.info("Setting up dependency injection container")
    
    # Register configuration
    container.register_singleton(
        ApplicationConfig,
        instance=config
    )
    
    # Register core services as singletons
    container.register_singleton(
        IEmbeddingProvider,
        factory=lambda c: create_embedding_provider(config)
    )
    
    container.register_singleton(
        IVectorStore,
        factory=lambda c: create_vector_store(config)
    )
    
    container.register_singleton(
        IClusteringEngine,
        factory=lambda c: create_clustering_engine(config)
    )
    
    container.register_singleton(
        IActionabilityScorer,
        factory=lambda c: create_actionability_scorer(config)
    )
    
    container.register_singleton(
        IRankingStrategy,
        factory=lambda c: create_ranking_strategy(config)
    )
    
    # Register event bus
    event_bus = create_event_bus(
        backend=config.MESSAGE_QUEUE_BACKEND,
        redis_url=config.REDIS_URL,
        max_size=1000
    )
    container.register_singleton(EventBus, instance=event_bus)
    
    # Register repositories (scoped per request/session)
    # Note: Repositories are created with session dependency injection in FastAPI
    # They don't need to be in the container for now
    
    logger.info("Dependency injection container configured successfully")
    return container


def bootstrap_application() -> DependencyContainer:
    """
    Bootstrap the entire application.
    
    This is the main entry point for application initialization.
    Call this once at startup.
    """
    # Load configuration
    config = ApplicationConfig()
    
    # Configure logging
    configure_logging(config)
    
    logger.info("🚀 Bootstrapping Roast Review Intelligence Platform")
    logger.info(f"Environment Configuration:")
    logger.info(f"  - Database: {config.DATABASE_URL[:30]}...")
    logger.info(f"  - Embedding Provider: {config.EMBEDDING_PROVIDER}")
    logger.info(f"  - Vector Backend: {config.VECTOR_BACKEND}")
    logger.info(f"  - Clustering Engine: {config.CLUSTERING_ENGINE}")
    logger.info(f"  - Message Queue: {config.MESSAGE_QUEUE_BACKEND}")
    logger.info(f"  - ML Scoring: {config.ML_SCORING_ENABLED}")
    logger.info(f"  - AI Analysis: {config.AI_ANALYSIS_ENABLED}")
    logger.info(f"  - GPU Enabled: {config.ENABLE_GPU}")
    
    # Setup dependency injection
    container = setup_container(config)
    
    logger.info("✅ Application bootstrap complete")
    
    return container


# Example usage
if __name__ == "__main__":
    # Bootstrap the application
    container = bootstrap_application()
    
    # Resolve and test components
    embedding_provider = container.resolve(IEmbeddingProvider)
    logger.info(f"Embedding dimension: {embedding_provider.get_dimension()}")
    
    clustering_engine = container.resolve(IClusteringEngine)
    logger.info(f"Clustering engine: {clustering_engine.__class__.__name__}")
    
    event_bus = container.resolve(EventBus)
    logger.info(f"Event bus: {event_bus.__class__.__name__}")
