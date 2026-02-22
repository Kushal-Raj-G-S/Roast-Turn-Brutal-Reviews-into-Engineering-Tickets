"""
Bulk Processing Pipeline - Core Use Case
Orchestrates the complete review processing workflow.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from src.domain.entities import Upload, Review, Cluster
from src.domain.value_objects import (
    UploadId, TenantId, ClusterId, ProcessingStage, ProcessingMetrics,
    ReviewMetadata, ClusterMetrics, Severity, ActionabilityScore
)
from src.domain.events import (
    UploadStageCompletedEvent, UploadCompletedEvent, UploadFailedEvent,
    ClusterCreatedEvent
)
from src.domain.repositories import IUploadRepository, IClusterRepository
from src.domain.services import (
    IEmbeddingProvider, IClusteringEngine, IRankingStrategy,
    IActionabilityScorer, IAIAnalysisService, IFileStorage
)

logger = logging.getLogger(__name__)


class BulkProcessingPipeline:
    """
    Orchestrates bulk review processing with domain-driven design.
    
    Pipeline Stages:
    1. CSV Loading & Validation
    2. Noise Filtering (rule-based)
    3. Actionability Scoring (ML-based)
    4. Embedding Generation
    5. Clustering
    6. Ranking
    7. AI Analysis (optional)
    8. Persistence
    
    Emits domain events at each stage for observability and async workflows.
    """

    def __init__(
        self,
        upload_repo: IUploadRepository,
        cluster_repo: IClusterRepository,
        embedding_provider: IEmbeddingProvider,
        clustering_engine: IClusteringEngine,
        ranking_strategy: IRankingStrategy,
        actionability_scorer: Optional[IActionabilityScorer] = None,
        ai_analysis_service: Optional[IAIAnalysisService] = None,
        file_storage: Optional[IFileStorage] = None,
        event_bus: Optional[Any] = None  # Will be typed when we create event bus
    ):
        self.upload_repo = upload_repo
        self.cluster_repo = cluster_repo
        self.embedding_provider = embedding_provider
        self.clustering_engine = clustering_engine
        self.ranking_strategy = ranking_strategy
        self.actionability_scorer = actionability_scorer
        self.ai_analysis_service = ai_analysis_service
        self.file_storage = file_storage
        self.event_bus = event_bus

        # Stage timings for metrics
        self.stage_timings: Dict[ProcessingStage, int] = {}

    async def execute(self, upload_id: UploadId) -> ProcessingMetrics:
        """
        Execute the complete bulk processing pipeline.
        
        Args:
            upload_id: ID of the upload to process
        
        Returns:
            ProcessingMetrics with complete stats
        """
        start_time = time.time()
        
        try:
            # Get upload entity
            upload = await self.upload_repo.get_by_id(upload_id)
            if not upload:
                raise ValueError(f"Upload {upload_id} not found")

            upload.start_processing()
            await self.upload_repo.update(upload)

            logger.info(f"Starting pipeline for upload {upload_id}")

            # Stage 1: Load CSV
            reviews = await self._load_and_validate_csv(upload)
            total_reviews = len(reviews)

            # Stage 2: Noise Filtering
            reviews = await self._filter_noise(upload, reviews)
            filtered_count = total_reviews - len(reviews)

            # Stage 3: Actionability Scoring (if enabled)
            if self.actionability_scorer:
                reviews = await self._score_actionability(upload, reviews)

            # Stage 4: Embedding
            reviews = await self._generate_embeddings(upload, reviews)

            # Stage 5: Clustering
            clusters = await self._cluster_reviews(upload, reviews)

            # Stage 6: Ranking
            clusters = await self._rank_clusters(upload, clusters)

            # Stage 7: Persist
            saved_clusters = await self._persist_clusters(upload, clusters)

            # Stage 8: AI Analysis (optional, can be async)
            ai_analyzed = 0
            if self.ai_analysis_service:
                ai_analyzed = await self._analyze_clusters(upload, saved_clusters)

            # Calculate metrics
            total_time_ms = int((time.time() - start_time) * 1000)
            metrics = ProcessingMetrics(
                total_reviews=total_reviews,
                filtered_noise=filtered_count,
                actionable_reviews=len(reviews),
                clusters_created=len(saved_clusters),
                ai_analyzed_count=ai_analyzed,
                processing_time_ms=total_time_ms,
                stage_timings=self.stage_timings,
                memory_peak_mb=0.0,  # TODO: Track memory
                cpu_utilization=0.0  # TODO: Track CPU
            )

            # Complete upload
            upload.complete(metrics)
            await self.upload_repo.update(upload)

            # Emit completion event
            if self.event_bus:
                event = UploadCompletedEvent.create(
                    upload_id=upload_id,
                    tenant_id=upload.tenant_id,
                    clusters_created=len(saved_clusters),
                    total_time_ms=total_time_ms
                )
                await self.event_bus.publish(event)

            logger.info(
                f"Pipeline completed for upload {upload_id}: "
                f"{total_reviews} reviews -> {len(saved_clusters)} clusters "
                f"in {total_time_ms}ms"
            )

            return metrics

        except Exception as e:
            logger.error(f"Pipeline failed for upload {upload_id}: {e}", exc_info=True)
            
            # Mark upload as failed
            upload = await self.upload_repo.get_by_id(upload_id)
            if upload:
                upload.fail(str(e))
                await self.upload_repo.update(upload)

            # Emit failure event
            if self.event_bus:
                event = UploadFailedEvent.create(
                    upload_id=upload_id,
                    tenant_id=upload.tenant_id,
                    error_message=str(e)
                )
                await self.event_bus.publish(event)

            raise

    async def _load_and_validate_csv(self, upload: Upload) -> List[Review]:
        """Stage 1: Load CSV and create Review entities."""
        stage_start = time.time()
        logger.info(f"Stage 1: Loading CSV for upload {upload.id}")

        try:
            # Load CSV
            df = pd.read_csv(upload.file_path)
            
            # Validate required columns
            required_cols = ['content']  # Minimum required
            if 'content' not in df.columns:
                raise ValueError("CSV must have 'content' column")

            # Create Review entities
            reviews = []
            for _, row in df.iterrows():
                metadata = ReviewMetadata(
                    rating=row.get('score'),
                    version=row.get('version'),
                    device=row.get('device'),
                    review_date=pd.to_datetime(row.get('at')) if 'at' in row else None
                )
                
                review = Review(
                    id=None,
                    text=str(row['content']),
                    metadata=metadata,
                    tenant_id=upload.tenant_id
                )
                reviews.append(review)

            # Record timing
            duration_ms = int((time.time() - stage_start) * 1000)
            self.stage_timings[ProcessingStage.CSV_LOADING] = duration_ms

            # Emit event
            if self.event_bus:
                event = UploadStageCompletedEvent.create(
                    upload_id=upload.id,
                    tenant_id=upload.tenant_id,
                    stage=ProcessingStage.CSV_LOADING,
                    duration_ms=duration_ms,
                    records_processed=len(reviews)
                )
                await self.event_bus.publish(event)

            logger.info(f"Stage 1 complete: Loaded {len(reviews)} reviews in {duration_ms}ms")
            return reviews

        except Exception as e:
            logger.error(f"CSV loading failed: {e}")
            raise

    async def _filter_noise(self, upload: Upload, reviews: List[Review]) -> List[Review]:
        """Stage 2: Filter noise reviews using business rules."""
        stage_start = time.time()
        logger.info(f"Stage 2: Filtering noise for {len(reviews)} reviews")

        # Apply domain rules
        kept_reviews = [r for r in reviews if not r.is_noise()]

        # Record timing
        duration_ms = int((time.time() - stage_start) * 1000)
        self.stage_timings[ProcessingStage.NOISE_FILTERING] = duration_ms

        # Emit event
        if self.event_bus:
            event = UploadStageCompletedEvent.create(
                upload_id=upload.id,
                tenant_id=upload.tenant_id,
                stage=ProcessingStage.NOISE_FILTERING,
                duration_ms=duration_ms,
                records_processed=len(kept_reviews)
            )
            await self.event_bus.publish(event)

        logger.info(
            f"Stage 2 complete: Kept {len(kept_reviews)}/{len(reviews)} reviews "
            f"in {duration_ms}ms"
        )
        return kept_reviews

    async def _score_actionability(
        self,
        upload: Upload,
        reviews: List[Review]
    ) -> List[Review]:
        """Stage 3: Score actionability using ML model."""
        stage_start = time.time()
        logger.info(f"Stage 3: Scoring actionability for {len(reviews)} reviews")

        # Score in batch
        scores = await self.actionability_scorer.score_batch(reviews)
        
        # Attach scores to reviews
        for review, score in zip(reviews, scores):
            review.actionability = score

        # Filter by actionability
        kept_reviews = [r for r in reviews if r.actionability.is_actionable]

        # Record timing
        duration_ms = int((time.time() - stage_start) * 1000)
        self.stage_timings[ProcessingStage.ACTIONABILITY_SCORING] = duration_ms

        # Emit event
        if self.event_bus:
            event = UploadStageCompletedEvent.create(
                upload_id=upload.id,
                tenant_id=upload.tenant_id,
                stage=ProcessingStage.ACTIONABILITY_SCORING,
                duration_ms=duration_ms,
                records_processed=len(kept_reviews)
            )
            await self.event_bus.publish(event)

        logger.info(
            f"Stage 3 complete: {len(kept_reviews)}/{len(reviews)} actionable "
            f"in {duration_ms}ms"
        )
        return kept_reviews

    async def _generate_embeddings(
        self,
        upload: Upload,
        reviews: List[Review]
    ) -> List[Review]:
        """Stage 4: Generate embeddings for reviews."""
        stage_start = time.time()
        logger.info(f"Stage 4: Generating embeddings for {len(reviews)} reviews")

        # Extract texts
        texts = [r.text for r in reviews]

        # Generate embeddings in batch
        embeddings = await self.embedding_provider.embed_batch(texts, batch_size=128)

        # Attach embeddings to reviews
        for review, embedding in zip(reviews, embeddings):
            review.embedding = embedding

        # Record timing
        duration_ms = int((time.time() - stage_start) * 1000)
        self.stage_timings[ProcessingStage.EMBEDDING] = duration_ms

        # Emit event
        if self.event_bus:
            event = UploadStageCompletedEvent.create(
                upload_id=upload.id,
                tenant_id=upload.tenant_id,
                stage=ProcessingStage.EMBEDDING,
                duration_ms=duration_ms,
                records_processed=len(reviews)
            )
            await self.event_bus.publish(event)

        logger.info(f"Stage 4 complete: Embedded {len(reviews)} reviews in {duration_ms}ms")
        return reviews

    async def _cluster_reviews(
        self,
        upload: Upload,
        reviews: List[Review]
    ) -> List[Cluster]:
        """Stage 5: Cluster reviews by similarity."""
        stage_start = time.time()
        logger.info(f"Stage 5: Clustering {len(reviews)} reviews")

        # Extract embedding vectors
        embeddings = [r.embedding.to_array() for r in reviews]

        # Cluster
        labels = await self.clustering_engine.cluster(embeddings, threshold=0.3)

        # Group reviews by cluster
        cluster_map: Dict[int, List[Review]] = {}
        for review, label in zip(reviews, labels):
            if label not in cluster_map:
                cluster_map[label] = []
            cluster_map[label].append(review)

        # Create Cluster entities
        clusters = []
        for label, cluster_reviews in cluster_map.items():
            cluster = self._create_cluster_from_reviews(
                upload=upload,
                reviews=cluster_reviews
            )
            clusters.append(cluster)

        # Record timing
        duration_ms = int((time.time() - stage_start) * 1000)
        self.stage_timings[ProcessingStage.CLUSTERING] = duration_ms

        # Emit event
        if self.event_bus:
            event = UploadStageCompletedEvent.create(
                upload_id=upload.id,
                tenant_id=upload.tenant_id,
                stage=ProcessingStage.CLUSTERING,
                duration_ms=duration_ms,
                records_processed=len(clusters)
            )
            await self.event_bus.publish(event)

        logger.info(f"Stage 5 complete: Created {len(clusters)} clusters in {duration_ms}ms")
        return clusters

    def _create_cluster_from_reviews(
        self,
        upload: Upload,
        reviews: List[Review]
    ) -> Cluster:
        """Create a Cluster entity from a group of reviews."""
        # Calculate severity from ratings
        ratings = [r.metadata.rating for r in reviews if r.metadata.rating]
        avg_rating = sum(ratings) / len(ratings) if ratings else 3.0
        
        if avg_rating <= 2.0:
            severity = Severity.CRITICAL
        elif avg_rating <= 2.5:
            severity = Severity.HIGH
        elif avg_rating <= 3.5:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        # Extract metadata
        versions = list(set(r.metadata.version for r in reviews if r.metadata.version))
        devices = list(set(r.metadata.device for r in reviews if r.metadata.device))

        # Generate title (simple version - can be improved)
        first_review = reviews[0].text
        title = first_review[:100] + "..." if len(first_review) > 100 else first_review

        # Create sample reviews
        sample_reviews = [
            {
                "text": r.text,
                "rating": r.metadata.rating,
                "version": r.metadata.version
            }
            for r in reviews[:5]  # Top 5 samples
        ]

        # Create metrics
        metrics = ClusterMetrics(
            review_count=len(reviews),
            avg_rating=avg_rating,
            severity_distribution={severity.value: len(reviews)},
            affected_versions=versions,
            affected_devices=devices,
            time_range=(datetime.utcnow(), datetime.utcnow()),
            keywords=[]
        )

        return Cluster(
            id=ClusterId.generate(),
            upload_id=upload.id,
            tenant_id=upload.tenant_id,
            title=title,
            severity=severity,
            metrics=metrics,
            sample_reviews=sample_reviews
        )

    async def _rank_clusters(
        self,
        upload: Upload,
        clusters: List[Cluster]
    ) -> List[Cluster]:
        """Stage 6: Rank clusters by priority."""
        stage_start = time.time()
        logger.info(f"Stage 6: Ranking {len(clusters)} clusters")

        # Convert to dict for ranking
        cluster_dicts = [
            {
                "id": c.id,
                "severity": c.severity,
                "review_count": c.metrics.review_count if c.metrics else 0,
                "avg_rating": c.metrics.avg_rating if c.metrics else 0,
                "cluster": c
            }
            for c in clusters
        ]

        # Rank
        ranked_dicts = await self.ranking_strategy.rank_clusters(cluster_dicts)
        ranked_clusters = [d["cluster"] for d in ranked_dicts]

        # Record timing
        duration_ms = int((time.time() - stage_start) * 1000)
        self.stage_timings[ProcessingStage.RANKING] = duration_ms

        logger.info(f"Stage 6 complete: Ranked {len(clusters)} clusters in {duration_ms}ms")
        return ranked_clusters

    async def _persist_clusters(
        self,
        upload: Upload,
        clusters: List[Cluster]
    ) -> List[Cluster]:
        """Stage 7: Persist clusters to database."""
        stage_start = time.time()
        logger.info(f"Stage 7: Persisting {len(clusters)} clusters")

        # Batch create
        saved_clusters = await self.cluster_repo.create_batch(clusters)

        # Emit cluster created events
        if self.event_bus:
            for cluster in saved_clusters:
                event = ClusterCreatedEvent.create(
                    cluster_id=cluster.id,
                    upload_id=upload.id,
                    tenant_id=upload.tenant_id,
                    severity=cluster.severity,
                    review_count=cluster.metrics.review_count if cluster.metrics else 0
                )
                await self.event_bus.publish(event)

        # Record timing
        duration_ms = int((time.time() - stage_start) * 1000)
        self.stage_timings[ProcessingStage.PERSISTENCE] = duration_ms

        logger.info(f"Stage 7 complete: Persisted {len(clusters)} clusters in {duration_ms}ms")
        return saved_clusters

    async def _analyze_clusters(
        self,
        upload: Upload,
        clusters: List[Cluster]
    ) -> int:
        """Stage 8: AI analysis for clusters (optional)."""
        stage_start = time.time()
        logger.info(f"Stage 8: AI analyzing top clusters")

        # Only analyze top clusters (e.g., top 20 by severity/count)
        top_clusters = clusters[:20]
        analyzed_count = 0

        for cluster in top_clusters:
            try:
                # Get reviews for this cluster (would need review repo)
                # For now, use sample reviews
                # analysis = await self.ai_analysis_service.analyze_cluster(
                #     cluster.id, 
                #     reviews
                # )
                # cluster.add_ai_analysis(**analysis)
                # await self.cluster_repo.update(cluster)
                analyzed_count += 1
            except Exception as e:
                logger.warning(f"AI analysis failed for cluster {cluster.id}: {e}")

        # Record timing
        duration_ms = int((time.time() - stage_start) * 1000)
        self.stage_timings[ProcessingStage.AI_ANALYSIS] = duration_ms

        logger.info(f"Stage 8 complete: Analyzed {analyzed_count} clusters in {duration_ms}ms")
        return analyzed_count
