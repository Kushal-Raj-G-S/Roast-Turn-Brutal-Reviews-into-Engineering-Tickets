"""
Benchmarking Framework for v1 vs v2 Architecture Comparison
Measures performance, quality, and scalability differences.
"""

import logging
import time
import psutil
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np
import json

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkMetrics:
    """Performance and quality metrics for a single run."""
    
    # Identification
    run_id: str
    architecture: str  # v1 or v2
    dataset_name: str
    timestamp: datetime
    
    # Performance metrics
    runtime_seconds: float
    memory_peak_mb: float
    memory_avg_mb: float
    cpu_avg_percent: float
    
    # Processing metrics
    total_reviews: int
    reviews_processed: int
    reviews_filtered: int
    filter_rate: float
    
    # Cluster metrics
    cluster_count: int
    avg_cluster_size: float
    min_cluster_size: int
    max_cluster_size: int
    singleton_clusters: int
    
    # Quality metrics
    high_severity_clusters: int
    medium_severity_clusters: int
    low_severity_clusters: int
    avg_actionability_score: float
    
    # Stage timings (milliseconds)
    stage_timings: Dict[str, int]
    
    # Throughput
    reviews_per_second: float
    clusters_per_second: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BenchmarkMetrics':
        """Create from dictionary."""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class ComparisonReport:
    """Comparison between v1 and v2 benchmarks."""
    
    v1_metrics: BenchmarkMetrics
    v2_metrics: BenchmarkMetrics
    
    # Performance comparison (positive = v2 is better)
    runtime_improvement_pct: float
    memory_improvement_pct: float
    throughput_improvement_pct: float
    
    # Quality comparison
    cluster_count_diff: int
    cluster_count_diff_pct: float
    severity_distribution_similarity: float
    
    # Cluster stability (Jaccard similarity of issue types)
    cluster_stability_score: float
    
    # Overall score
    overall_score: float
    recommendation: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'v1_metrics': self.v1_metrics.to_dict(),
            'v2_metrics': self.v2_metrics.to_dict(),
            'runtime_improvement_pct': self.runtime_improvement_pct,
            'memory_improvement_pct': self.memory_improvement_pct,
            'throughput_improvement_pct': self.throughput_improvement_pct,
            'cluster_count_diff': self.cluster_count_diff,
            'cluster_count_diff_pct': self.cluster_count_diff_pct,
            'severity_distribution_similarity': self.severity_distribution_similarity,
            'cluster_stability_score': self.cluster_stability_score,
            'overall_score': self.overall_score,
            'recommendation': self.recommendation
        }


class PerformanceMonitor:
    """Monitor system resources during benchmark."""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.start_time = None
        self.memory_samples = []
        self.cpu_samples = []
        self.sampling = False
    
    def start(self):
        """Start monitoring."""
        self.start_time = time.time()
        self.memory_samples = []
        self.cpu_samples = []
        self.sampling = True
        self._sample()
    
    def _sample(self):
        """Take a sample of current resource usage."""
        if self.sampling:
            try:
                memory_mb = self.process.memory_info().rss / 1024 / 1024
                cpu_percent = self.process.cpu_percent(interval=0.1)
                
                self.memory_samples.append(memory_mb)
                self.cpu_samples.append(cpu_percent)
            except:
                pass
    
    def sample_periodic(self):
        """Sample periodically during processing."""
        self._sample()
    
    def stop(self) -> Dict[str, float]:
        """Stop monitoring and return metrics."""
        self.sampling = False
        elapsed = time.time() - self.start_time
        
        return {
            'runtime_seconds': elapsed,
            'memory_peak_mb': max(self.memory_samples) if self.memory_samples else 0,
            'memory_avg_mb': np.mean(self.memory_samples) if self.memory_samples else 0,
            'cpu_avg_percent': np.mean(self.cpu_samples) if self.cpu_samples else 0
        }


class BenchmarkRunner:
    """
    Run benchmarks on v1 and v2 architectures.
    Supports both sync and async processing pipelines.
    """
    
    def __init__(self, output_dir: str = "./benchmarks"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def run_v1_benchmark(self, csv_path: str, dataset_name: str) -> BenchmarkMetrics:
        """
        Run benchmark on v1 architecture.
        Uses the legacy bulk processing pipeline.
        """
        logger.info(f"Running v1 benchmark on {dataset_name}")
        
        monitor = PerformanceMonitor()
        monitor.start()
        
        try:
            # Import v1 components
            from app.bulk_processor import BulkProcessor
            from app.config import get_settings
            
            settings = get_settings()
            processor = BulkProcessor()
            
            # Run processing
            start_time = time.time()
            result = processor.process_csv(csv_path)
            runtime = time.time() - start_time
            
            # Stop monitoring
            perf_metrics = monitor.stop()
            
            # Extract metrics
            clusters = result.get('clusters', [])
            
            severity_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
            for cluster in clusters:
                severity = cluster.get('severity', 'LOW')
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            cluster_sizes = [cluster.get('review_count', 0) for cluster in clusters]
            
            metrics = BenchmarkMetrics(
                run_id=f"v1_{dataset_name}_{int(time.time())}",
                architecture="v1",
                dataset_name=dataset_name,
                timestamp=datetime.now(),
                runtime_seconds=runtime,
                memory_peak_mb=perf_metrics['memory_peak_mb'],
                memory_avg_mb=perf_metrics['memory_avg_mb'],
                cpu_avg_percent=perf_metrics['cpu_avg_percent'],
                total_reviews=result.get('total_reviews', 0),
                reviews_processed=result.get('reviews_processed', 0),
                reviews_filtered=result.get('reviews_filtered', 0),
                filter_rate=result.get('filter_rate', 0),
                cluster_count=len(clusters),
                avg_cluster_size=np.mean(cluster_sizes) if cluster_sizes else 0,
                min_cluster_size=min(cluster_sizes) if cluster_sizes else 0,
                max_cluster_size=max(cluster_sizes) if cluster_sizes else 0,
                singleton_clusters=sum(1 for size in cluster_sizes if size == 1),
                high_severity_clusters=severity_counts['HIGH'],
                medium_severity_clusters=severity_counts['MEDIUM'],
                low_severity_clusters=severity_counts['LOW'],
                avg_actionability_score=0.0,  # v1 doesn't have this
                stage_timings=result.get('stage_timings', {}),
                reviews_per_second=result.get('reviews_processed', 0) / runtime if runtime > 0 else 0,
                clusters_per_second=len(clusters) / runtime if runtime > 0 else 0
            )
            
            logger.info(f"v1 benchmark complete: {runtime:.2f}s, {len(clusters)} clusters")
            return metrics
            
        except Exception as e:
            logger.error(f"v1 benchmark failed: {e}", exc_info=True)
            raise
    
    async def run_v2_benchmark(self, csv_path: str, dataset_name: str) -> BenchmarkMetrics:
        """
        Run benchmark on v2 architecture.
        Uses the new domain-driven pipeline.
        """
        logger.info(f"Running v2 benchmark on {dataset_name}")
        
        monitor = PerformanceMonitor()
        monitor.start()
        
        try:
            # Import v2 components
            from src.bootstrap import bootstrap_application
            from src.application.use_cases.bulk_processing_pipeline import BulkProcessingPipeline
            from src.domain.entities import Upload
            from src.domain.value_objects import UploadId, TenantId, UploadStatus
            
            # Bootstrap application
            config, container = bootstrap_application()
            
            # Create pipeline
            pipeline = container.resolve(BulkProcessingPipeline)
            
            # Create upload entity
            upload = Upload(
                id=UploadId.generate(),
                tenant_id=TenantId("benchmark-tenant"),
                file_path=csv_path,
                filename=Path(csv_path).name,
                status=UploadStatus.PENDING
            )
            
            # Run processing
            start_time = time.time()
            metrics_result = await pipeline.execute(upload)
            runtime = time.time() - start_time
            
            # Stop monitoring
            perf_metrics = monitor.stop()
            
            # Extract metrics from pipeline result
            from src.infrastructure.persistence.repositories import PostgresClusterRepository
            from app.database import AsyncSessionLocal
            
            # Get clusters from database
            async with AsyncSessionLocal() as session:
                cluster_repo = PostgresClusterRepository(session)
                clusters = await cluster_repo.get_by_upload(upload.id)
            
            severity_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
            cluster_sizes = []
            actionability_scores = []
            
            for cluster in clusters:
                severity_counts[cluster.severity.value] = severity_counts.get(cluster.severity.value, 0) + 1
                cluster_sizes.append(cluster.metrics.review_count)
                if cluster.metrics.avg_actionability_score:
                    actionability_scores.append(cluster.metrics.avg_actionability_score)
            
            metrics = BenchmarkMetrics(
                run_id=f"v2_{dataset_name}_{int(time.time())}",
                architecture="v2",
                dataset_name=dataset_name,
                timestamp=datetime.now(),
                runtime_seconds=runtime,
                memory_peak_mb=perf_metrics['memory_peak_mb'],
                memory_avg_mb=perf_metrics['memory_avg_mb'],
                cpu_avg_percent=perf_metrics['cpu_avg_percent'],
                total_reviews=metrics_result.total_reviews,
                reviews_processed=metrics_result.reviews_processed,
                reviews_filtered=metrics_result.reviews_filtered,
                filter_rate=metrics_result.reviews_filtered / metrics_result.total_reviews if metrics_result.total_reviews > 0 else 0,
                cluster_count=len(clusters),
                avg_cluster_size=np.mean(cluster_sizes) if cluster_sizes else 0,
                min_cluster_size=min(cluster_sizes) if cluster_sizes else 0,
                max_cluster_size=max(cluster_sizes) if cluster_sizes else 0,
                singleton_clusters=sum(1 for size in cluster_sizes if size == 1),
                high_severity_clusters=severity_counts.get('HIGH', 0),
                medium_severity_clusters=severity_counts.get('MEDIUM', 0),
                low_severity_clusters=severity_counts.get('LOW', 0),
                avg_actionability_score=np.mean(actionability_scores) if actionability_scores else 0,
                stage_timings={stage.value: timing for stage, timing in metrics_result.stage_timings.items()},
                reviews_per_second=metrics_result.reviews_processed / runtime if runtime > 0 else 0,
                clusters_per_second=len(clusters) / runtime if runtime > 0 else 0
            )
            
            logger.info(f"v2 benchmark complete: {runtime:.2f}s, {len(clusters)} clusters")
            return metrics
            
        except Exception as e:
            logger.error(f"v2 benchmark failed: {e}", exc_info=True)
            raise
    
    def compare(self, v1_metrics: BenchmarkMetrics, v2_metrics: BenchmarkMetrics) -> ComparisonReport:
        """
        Compare v1 and v2 metrics and generate report.
        """
        logger.info("Generating comparison report")
        
        # Performance improvements (positive = v2 better)
        runtime_improvement = ((v1_metrics.runtime_seconds - v2_metrics.runtime_seconds) / v1_metrics.runtime_seconds) * 100
        memory_improvement = ((v1_metrics.memory_peak_mb - v2_metrics.memory_peak_mb) / v1_metrics.memory_peak_mb) * 100
        throughput_improvement = ((v2_metrics.reviews_per_second - v1_metrics.reviews_per_second) / v1_metrics.reviews_per_second) * 100
        
        # Cluster differences
        cluster_diff = v2_metrics.cluster_count - v1_metrics.cluster_count
        cluster_diff_pct = (cluster_diff / v1_metrics.cluster_count) * 100 if v1_metrics.cluster_count > 0 else 0
        
        # Severity distribution similarity (cosine similarity)
        v1_dist = np.array([
            v1_metrics.high_severity_clusters,
            v1_metrics.medium_severity_clusters,
            v1_metrics.low_severity_clusters
        ])
        v2_dist = np.array([
            v2_metrics.high_severity_clusters,
            v2_metrics.medium_severity_clusters,
            v2_metrics.low_severity_clusters
        ])
        
        if np.linalg.norm(v1_dist) > 0 and np.linalg.norm(v2_dist) > 0:
            severity_similarity = np.dot(v1_dist, v2_dist) / (np.linalg.norm(v1_dist) * np.linalg.norm(v2_dist))
        else:
            severity_similarity = 0.0
        
        # Cluster stability (simplified - based on cluster count similarity)
        stability_score = 1 - abs(cluster_diff_pct) / 100
        stability_score = max(0, min(1, stability_score))
        
        # Overall score (weighted combination)
        performance_score = (
            (runtime_improvement / 100) * 0.4 +
            (memory_improvement / 100) * 0.2 +
            (throughput_improvement / 100) * 0.2
        )
        quality_score = (
            severity_similarity * 0.5 +
            stability_score * 0.5
        )
        overall_score = (performance_score * 0.6 + quality_score * 0.4) * 100
        
        # Recommendation
        if overall_score > 20:
            recommendation = "STRONGLY RECOMMEND v2 - Significant improvements across metrics"
        elif overall_score > 10:
            recommendation = "RECOMMEND v2 - Notable improvements with good stability"
        elif overall_score > 0:
            recommendation = "CONSIDER v2 - Marginal improvements, monitor in production"
        elif overall_score > -10:
            recommendation = "NEUTRAL - Mixed results, more testing needed"
        else:
            recommendation = "CAUTION - v2 shows regressions, investigate before deployment"
        
        report = ComparisonReport(
            v1_metrics=v1_metrics,
            v2_metrics=v2_metrics,
            runtime_improvement_pct=runtime_improvement,
            memory_improvement_pct=memory_improvement,
            throughput_improvement_pct=throughput_improvement,
            cluster_count_diff=cluster_diff,
            cluster_count_diff_pct=cluster_diff_pct,
            severity_distribution_similarity=severity_similarity,
            cluster_stability_score=stability_score,
            overall_score=overall_score,
            recommendation=recommendation
        )
        
        return report
    
    def save_report(self, report: ComparisonReport, filename: Optional[str] = None):
        """Save comparison report to JSON."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_comparison_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        
        logger.info(f"Report saved to {filepath}")
        return str(filepath)
    
    def print_report(self, report: ComparisonReport):
        """Print formatted comparison report."""
        print("\n" + "=" * 80)
        print("BENCHMARK COMPARISON REPORT")
        print("=" * 80)
        print(f"\nDataset: {report.v1_metrics.dataset_name}")
        print(f"Timestamp: {report.v2_metrics.timestamp}")
        
        print("\n" + "-" * 80)
        print("PERFORMANCE METRICS")
        print("-" * 80)
        print(f"Runtime:")
        print(f"  v1: {report.v1_metrics.runtime_seconds:.2f}s")
        print(f"  v2: {report.v2_metrics.runtime_seconds:.2f}s")
        print(f"  Improvement: {report.runtime_improvement_pct:+.1f}%")
        
        print(f"\nMemory (Peak):")
        print(f"  v1: {report.v1_metrics.memory_peak_mb:.1f} MB")
        print(f"  v2: {report.v2_metrics.memory_peak_mb:.1f} MB")
        print(f"  Improvement: {report.memory_improvement_pct:+.1f}%")
        
        print(f"\nThroughput:")
        print(f"  v1: {report.v1_metrics.reviews_per_second:.1f} reviews/sec")
        print(f"  v2: {report.v2_metrics.reviews_per_second:.1f} reviews/sec")
        print(f"  Improvement: {report.throughput_improvement_pct:+.1f}%")
        
        print("\n" + "-" * 80)
        print("QUALITY METRICS")
        print("-" * 80)
        print(f"Clusters:")
        print(f"  v1: {report.v1_metrics.cluster_count}")
        print(f"  v2: {report.v2_metrics.cluster_count}")
        print(f"  Difference: {report.cluster_count_diff:+d} ({report.cluster_count_diff_pct:+.1f}%)")
        
        print(f"\nSeverity Distribution:")
        print(f"  v1: HIGH={report.v1_metrics.high_severity_clusters}, MED={report.v1_metrics.medium_severity_clusters}, LOW={report.v1_metrics.low_severity_clusters}")
        print(f"  v2: HIGH={report.v2_metrics.high_severity_clusters}, MED={report.v2_metrics.medium_severity_clusters}, LOW={report.v2_metrics.low_severity_clusters}")
        print(f"  Similarity: {report.severity_distribution_similarity:.3f}")
        
        print(f"\nCluster Stability: {report.cluster_stability_score:.3f}")
        
        print("\n" + "=" * 80)
        print(f"OVERALL SCORE: {report.overall_score:.1f}/100")
        print(f"RECOMMENDATION: {report.recommendation}")
        print("=" * 80 + "\n")
