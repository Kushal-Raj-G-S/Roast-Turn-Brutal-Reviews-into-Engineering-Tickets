"""
Robustness Testing Module

Tracks system performance under stress conditions:
- Latency per stage (feature extraction, ML scoring, rule scoring)
- Memory usage during processing
- Uncertainty distribution changes
- Cluster stability across corrupted data
"""

import logging
import time
import psutil
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class LatencyStats:
    """Latency statistics for a processing stage."""
    stage_name: str
    samples: List[float] = field(default_factory=list)
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    total_time_s: float = 0.0


@dataclass
class MemoryStats:
    """Memory usage statistics."""
    baseline_mb: float
    peak_mb: float
    final_mb: float
    increase_mb: float
    increase_pct: float


@dataclass
class UncertaintyDistribution:
    """Distribution of uncertainty scores."""
    mean: float
    median: float
    std: float
    p25: float
    p75: float
    p95: float
    bins: Dict[str, int] = field(default_factory=dict)  # e.g., "0.0-0.2": 100
    high_uncertainty_rate: float = 0.0  # > 0.3


@dataclass
class ClusterStabilityMetrics:
    """Metrics for cluster stability analysis."""
    num_clusters: int
    avg_cluster_size: float
    cluster_size_std: float
    largest_cluster_size: int
    smallest_cluster_size: int
    singleton_rate: float  # Clusters with 1 member
    cluster_distribution: Dict[int, int] = field(default_factory=dict)  # size -> count


@dataclass
class RobustnessTestReport:
    """Complete robustness test report."""
    test_name: str
    dataset_name: str
    total_reviews: int
    processed_reviews: int
    failed_reviews: int
    success_rate: float
    
    # Performance metrics
    latency_by_stage: Dict[str, LatencyStats] = field(default_factory=dict)
    memory_stats: Optional[MemoryStats] = None
    total_runtime_s: float = 0.0
    throughput_reviews_per_sec: float = 0.0
    
    # Quality metrics
    uncertainty_distribution: Optional[UncertaintyDistribution] = None
    cluster_stability: Optional[ClusterStabilityMetrics] = None
    
    # Scoring metrics
    actionable_rate: float = 0.0
    avg_score: float = 0.0
    avg_confidence: float = 0.0
    
    # Degradation indicators
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    bottlenecks: List[str] = field(default_factory=list)


class RobustnessTestRunner:
    """
    Runs robustness tests on corrupted/stress datasets.
    
    Tracks performance, memory, and quality metrics.
    """
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.baseline_memory_mb = self._get_memory_mb()
    
    def run_test(
        self,
        test_name: str,
        dataset_path: str,
        scorer,
        max_reviews: Optional[int] = None
    ) -> RobustnessTestReport:
        """
        Run robustness test on a dataset.
        
        Args:
            test_name: Name of the test
            dataset_path: Path to CSV dataset
            scorer: HybridActionabilityScorer instance
            max_reviews: Optional limit on reviews to process
            
        Returns:
            RobustnessTestReport with all metrics
        """
        logger.info(f"Starting robustness test: {test_name}")
        logger.info(f"Dataset: {dataset_path}")
        
        # Load dataset
        try:
            df = pd.read_csv(dataset_path)
        except Exception as e:
            logger.error(f"Failed to load dataset: {e}")
            return self._create_error_report(test_name, dataset_path, str(e))
        
        if max_reviews:
            df = df.head(max_reviews)
        
        total_reviews = len(df)
        logger.info(f"Processing {total_reviews} reviews...")
        
        # Start test
        test_start = time.time()
        baseline_memory = self._get_memory_mb()
        
        # Track metrics
        latency_tracker = defaultdict(list)
        results = []
        failed_count = 0
        peak_memory = baseline_memory
        
        # Process reviews
        for idx, row in df.iterrows():
            try:
                # Prepare review
                review_data = {
                    'id': row.get('reviewId', f'review_{idx}'),
                    'text': str(row.get('content', '')),
                    'rating': int(row.get('score', 3))
                }
                
                # Track per-stage latency
                stage_times = {}
                
                # Feature extraction
                t0 = time.time()
                from src.infrastructure.ml.feature_engineering import FeatureExtractor
                extractor = FeatureExtractor()
                features = extractor.extract(review_data['text'], review_data['rating'])
                stage_times['feature_extraction'] = (time.time() - t0) * 1000
                
                # ML scoring (with scorer if available)
                t0 = time.time()
                if hasattr(scorer, 'score'):
                    from src.domain.entities import Review
                    from src.domain.value_objects import ReviewMetadata
                    metadata = ReviewMetadata(rating=review_data['rating'])
                    review = Review(
                        id=review_data['id'],
                        text=review_data['text'],
                        metadata=metadata
                    )
                    result = scorer.score(review)
                    
                    results.append({
                        'review_id': review_data['id'],
                        'score': result.score,
                        'confidence': result.confidence,
                        'uncertainty': result.uncertainty,
                        'is_actionable': result.is_actionable,
                        'has_concession': features.has_concession,
                        'has_monetization_complaint': features.has_monetization_complaint,
                        'has_retention_signal': features.has_retention_signal
                    })
                else:
                    # Fallback for testing without full scorer
                    results.append({
                        'review_id': review_data['id'],
                        'score': 0.5,
                        'confidence': 0.8,
                        'uncertainty': 0.2,
                        'is_actionable': True,
                        'has_concession': features.has_concession,
                        'has_monetization_complaint': features.has_monetization_complaint,
                        'has_retention_signal': features.has_retention_signal
                    })
                
                stage_times['total'] = (time.time() - t0) * 1000
                
                # Record latencies
                for stage, latency_ms in stage_times.items():
                    latency_tracker[stage].append(latency_ms)
                
                # Track memory
                current_memory = self._get_memory_mb()
                if current_memory > peak_memory:
                    peak_memory = current_memory
            
            except Exception as e:
                logger.warning(f"Failed to process review {idx}: {e}")
                failed_count += 1
        
        test_end = time.time()
        total_runtime = test_end - test_start
        final_memory = self._get_memory_mb()
        
        processed_reviews = len(results)
        success_rate = processed_reviews / total_reviews if total_reviews > 0 else 0.0
        
        logger.info(f"Test complete: {processed_reviews}/{total_reviews} processed ({success_rate:.1%})")
        
        # Compute latency stats
        latency_stats = {}
        for stage, samples in latency_tracker.items():
            if samples:
                latency_stats[stage] = LatencyStats(
                    stage_name=stage,
                    samples=samples,
                    mean_ms=np.mean(samples),
                    median_ms=np.median(samples),
                    p95_ms=np.percentile(samples, 95),
                    p99_ms=np.percentile(samples, 99),
                    min_ms=np.min(samples),
                    max_ms=np.max(samples),
                    total_time_s=np.sum(samples) / 1000
                )
        
        # Memory stats
        memory_stats = MemoryStats(
            baseline_mb=baseline_memory,
            peak_mb=peak_memory,
            final_mb=final_memory,
            increase_mb=peak_memory - baseline_memory,
            increase_pct=((peak_memory - baseline_memory) / baseline_memory * 100) if baseline_memory > 0 else 0.0
        )
        
        # Uncertainty distribution
        uncertainties = [r['uncertainty'] for r in results if 'uncertainty' in r]
        uncertainty_dist = None
        if uncertainties:
            uncertainty_dist = self._compute_uncertainty_distribution(uncertainties)
        
        # Scoring metrics
        actionable_count = sum(1 for r in results if r.get('is_actionable', False))
        actionable_rate = actionable_count / len(results) if results else 0.0
        avg_score = np.mean([r['score'] for r in results]) if results else 0.0
        avg_confidence = np.mean([r['confidence'] for r in results]) if results else 0.0
        
        # Detect bottlenecks
        bottlenecks = []
        for stage, stats in latency_stats.items():
            if stats.p95_ms > 50:  # >50ms at p95 is slow
                bottlenecks.append(f"{stage}: p95={stats.p95_ms:.1f}ms (slow)")
        
        if memory_stats.increase_pct > 50:
            bottlenecks.append(f"Memory increased by {memory_stats.increase_pct:.0f}% (high)")
        
        # Generate alerts
        alerts = []
        if success_rate < 0.95:
            alerts.append({
                'severity': 'high',
                'message': f"Low success rate: {success_rate:.1%}"
            })
        if uncertainty_dist and uncertainty_dist.high_uncertainty_rate > 0.5:
            alerts.append({
                'severity': 'medium',
                'message': f"High uncertainty rate: {uncertainty_dist.high_uncertainty_rate:.1%}"
            })
        if actionable_rate < 0.1 or actionable_rate > 0.9:
            alerts.append({
                'severity': 'medium',
                'message': f"Unusual actionable rate: {actionable_rate:.1%}"
            })
        
        # Create report
        report = RobustnessTestReport(
            test_name=test_name,
            dataset_name=os.path.basename(dataset_path),
            total_reviews=total_reviews,
            processed_reviews=processed_reviews,
            failed_reviews=failed_count,
            success_rate=success_rate,
            latency_by_stage=latency_stats,
            memory_stats=memory_stats,
            total_runtime_s=total_runtime,
            throughput_reviews_per_sec=processed_reviews / total_runtime if total_runtime > 0 else 0.0,
            uncertainty_distribution=uncertainty_dist,
            actionable_rate=actionable_rate,
            avg_score=avg_score,
            avg_confidence=avg_confidence,
            alerts=alerts,
            bottlenecks=bottlenecks
        )
        
        return report
    
    def compare_tests(
        self,
        baseline_report: RobustnessTestReport,
        test_report: RobustnessTestReport
    ) -> Dict[str, Any]:
        """
        Compare two test reports to detect degradation.
        
        Returns:
            Comparison dict with changes and alerts
        """
        comparison = {
            'baseline': baseline_report.test_name,
            'test': test_report.test_name,
            'changes': {},
            'degradation_alerts': []
        }
        
        # Compare success rate
        success_rate_change = test_report.success_rate - baseline_report.success_rate
        comparison['changes']['success_rate'] = {
            'baseline': baseline_report.success_rate,
            'test': test_report.success_rate,
            'change': success_rate_change,
            'change_pct': (success_rate_change / baseline_report.success_rate * 100) if baseline_report.success_rate > 0 else 0.0
        }
        if success_rate_change < -0.05:  # 5% drop
            comparison['degradation_alerts'].append({
                'severity': 'high',
                'metric': 'success_rate',
                'message': f"Success rate dropped by {abs(success_rate_change):.1%}"
            })
        
        # Compare latency
        for stage in baseline_report.latency_by_stage:
            if stage in test_report.latency_by_stage:
                baseline_p95 = baseline_report.latency_by_stage[stage].p95_ms
                test_p95 = test_report.latency_by_stage[stage].p95_ms
                latency_change_pct = ((test_p95 - baseline_p95) / baseline_p95 * 100) if baseline_p95 > 0 else 0.0
                
                comparison['changes'][f'{stage}_latency'] = {
                    'baseline_p95': baseline_p95,
                    'test_p95': test_p95,
                    'change_pct': latency_change_pct
                }
                
                if latency_change_pct > 50:  # 50% slower
                    comparison['degradation_alerts'].append({
                        'severity': 'medium',
                        'metric': f'{stage}_latency',
                        'message': f"{stage} latency increased by {latency_change_pct:.0f}%"
                    })
        
        # Compare memory
        if baseline_report.memory_stats and test_report.memory_stats:
            memory_change_pct = ((test_report.memory_stats.peak_mb - baseline_report.memory_stats.peak_mb) 
                                / baseline_report.memory_stats.peak_mb * 100) if baseline_report.memory_stats.peak_mb > 0 else 0.0
            comparison['changes']['memory'] = {
                'baseline_peak_mb': baseline_report.memory_stats.peak_mb,
                'test_peak_mb': test_report.memory_stats.peak_mb,
                'change_pct': memory_change_pct
            }
            
            if memory_change_pct > 100:  # 100% more memory
                comparison['degradation_alerts'].append({
                    'severity': 'high',
                    'metric': 'memory',
                    'message': f"Memory usage increased by {memory_change_pct:.0f}%"
                })
        
        # Compare uncertainty
        if baseline_report.uncertainty_distribution and test_report.uncertainty_distribution:
            uncertainty_change = test_report.uncertainty_distribution.high_uncertainty_rate - baseline_report.uncertainty_distribution.high_uncertainty_rate
            comparison['changes']['uncertainty'] = {
                'baseline_high_rate': baseline_report.uncertainty_distribution.high_uncertainty_rate,
                'test_high_rate': test_report.uncertainty_distribution.high_uncertainty_rate,
                'change': uncertainty_change
            }
            
            if uncertainty_change > 0.2:  # 20% increase
                comparison['degradation_alerts'].append({
                    'severity': 'medium',
                    'metric': 'uncertainty',
                    'message': f"High uncertainty rate increased by {uncertainty_change:.1%}"
                })
        
        return comparison
    
    def _compute_uncertainty_distribution(self, uncertainties: List[float]) -> UncertaintyDistribution:
        """Compute uncertainty distribution statistics."""
        uncertainties_array = np.array(uncertainties)
        
        # Bin counts
        bins = {
            '0.0-0.1': np.sum((uncertainties_array >= 0.0) & (uncertainties_array < 0.1)),
            '0.1-0.2': np.sum((uncertainties_array >= 0.1) & (uncertainties_array < 0.2)),
            '0.2-0.3': np.sum((uncertainties_array >= 0.2) & (uncertainties_array < 0.3)),
            '0.3-0.5': np.sum((uncertainties_array >= 0.3) & (uncertainties_array < 0.5)),
            '0.5-1.0': np.sum((uncertainties_array >= 0.5) & (uncertainties_array <= 1.0)),
        }
        
        high_uncertainty_rate = np.sum(uncertainties_array > 0.3) / len(uncertainties_array)
        
        return UncertaintyDistribution(
            mean=float(np.mean(uncertainties_array)),
            median=float(np.median(uncertainties_array)),
            std=float(np.std(uncertainties_array)),
            p25=float(np.percentile(uncertainties_array, 25)),
            p75=float(np.percentile(uncertainties_array, 75)),
            p95=float(np.percentile(uncertainties_array, 95)),
            bins={k: int(v) for k, v in bins.items()},
            high_uncertainty_rate=high_uncertainty_rate
        )
    
    def _get_memory_mb(self) -> float:
        """Get current process memory usage in MB."""
        return self.process.memory_info().rss / 1024 / 1024
    
    def _create_error_report(self, test_name: str, dataset_name: str, error: str) -> RobustnessTestReport:
        """Create error report when test fails to initialize."""
        return RobustnessTestReport(
            test_name=test_name,
            dataset_name=dataset_name,
            total_reviews=0,
            processed_reviews=0,
            failed_reviews=0,
            success_rate=0.0,
            alerts=[{
                'severity': 'critical',
                'message': f"Test initialization failed: {error}"
            }]
        )


def analyze_cluster_stability(
    clusters_csv: str,
    min_cluster_size: int = 5
) -> ClusterStabilityMetrics:
    """
    Analyze cluster stability from clustering results.
    
    Args:
        clusters_csv: Path to CSV with cluster results
        min_cluster_size: Minimum cluster size to consider
        
    Returns:
        ClusterStabilityMetrics
    """
    try:
        df = pd.read_csv(clusters_csv)
    except Exception as e:
        logger.error(f"Failed to load clusters: {e}")
        return ClusterStabilityMetrics(
            num_clusters=0,
            avg_cluster_size=0.0,
            cluster_size_std=0.0,
            largest_cluster_size=0,
            smallest_cluster_size=0,
            singleton_rate=0.0
        )
    
    # Assuming cluster_id or cluster_label column
    cluster_col = 'cluster_id' if 'cluster_id' in df.columns else 'cluster_label'
    if cluster_col not in df.columns:
        logger.error(f"Missing cluster column in {clusters_csv}")
        return ClusterStabilityMetrics(
            num_clusters=0,
            avg_cluster_size=0.0,
            cluster_size_std=0.0,
            largest_cluster_size=0,
            smallest_cluster_size=0,
            singleton_rate=0.0
        )
    
    # Compute cluster sizes
    cluster_sizes = df[cluster_col].value_counts().to_dict()
    sizes = list(cluster_sizes.values())
    
    num_clusters = len(cluster_sizes)
    singleton_count = sum(1 for size in sizes if size == 1)
    singleton_rate = singleton_count / num_clusters if num_clusters > 0 else 0.0
    
    # Size distribution
    size_distribution = {}
    for size in sizes:
        size_distribution[size] = size_distribution.get(size, 0) + 1
    
    return ClusterStabilityMetrics(
        num_clusters=num_clusters,
        avg_cluster_size=float(np.mean(sizes)) if sizes else 0.0,
        cluster_size_std=float(np.std(sizes)) if sizes else 0.0,
        largest_cluster_size=max(sizes) if sizes else 0,
        smallest_cluster_size=min(sizes) if sizes else 0,
        singleton_rate=singleton_rate,
        cluster_distribution=size_distribution
    )
