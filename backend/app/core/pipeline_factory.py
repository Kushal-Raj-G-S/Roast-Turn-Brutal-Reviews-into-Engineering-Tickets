"""
Builds a BulkProcessingPipeline using the exact same DI container and
Postgres repositories the FastAPI v2 route (src/api/routes/upload_v2.py)
already uses. Exists so the Airflow DAG (airflow/dags/roast_pipeline_dag.py)
never re-implements or forks how the pipeline's dependencies are wired —
both the API and the DAG call this one function.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from src.application.use_cases.bulk_processing_pipeline import BulkProcessingPipeline
from src.bootstrap import bootstrap_application
from src.domain.services import IClusteringEngine, IEmbeddingProvider, IRankingStrategy
from src.infrastructure.dependency_injection import DependencyContainer
from src.infrastructure.messaging.bus_provider import get_event_bus
from src.infrastructure.persistence.repositories import (
    PostgresClusterRepository,
    PostgresUploadRepository,
)

_container: DependencyContainer | None = None


def get_container() -> DependencyContainer:
    global _container
    if _container is None:
        _container = bootstrap_application()
    return _container


@asynccontextmanager
async def build_bulk_pipeline() -> AsyncIterator[BulkProcessingPipeline]:
    """
    Async context manager: opens its own DB session (Airflow tasks run in
    separate processes, so they can't share the FastAPI request-scoped
    session get_session() provides) and yields a fully-wired pipeline.
    """
    from app.database.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        container = get_container()

        upload_repo = PostgresUploadRepository(session)
        cluster_repo = PostgresClusterRepository(session)
        embedding_provider = container.resolve(IEmbeddingProvider)
        clustering_engine = container.resolve(IClusteringEngine)
        ranking_strategy = container.resolve(IRankingStrategy)

        # The pipeline publishes a domain event at every stage; passing the
        # real bus here is what makes those publishes live (they were dead
        # code while every call site passed event_bus=None).
        event_bus = await get_event_bus()

        pipeline = BulkProcessingPipeline(
            upload_repo=upload_repo,
            cluster_repo=cluster_repo,
            embedding_provider=embedding_provider,
            clustering_engine=clustering_engine,
            ranking_strategy=ranking_strategy,
            actionability_scorer=None,
            ai_analysis_service=None,
            file_storage=None,
            event_bus=event_bus,
        )
        yield pipeline
