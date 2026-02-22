"""
Observability Module for V3
Metrics tracking, latency monitoring, health endpoints.
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
import numpy as np
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LatencyMetrics:
    """Track latency for different stages."""
    feature_extraction_ms: List[float] = field(default_factory=list)
    ml_scoring_ms: List[float] = field(default_factory=list)
    rule_scoring_ms: List[float] = field(default_factory=list)
    total_scoring_ms: List[float] = field(default_factory=list)
    
    def add(self, stage: str, latency_ms: float):
        """Add latency measurement."""
        if stage == 'feature_extraction':
            self.feature_extraction_ms.append(latency_ms)
        elif stage == 'ml_scoring':
            self.ml_scoring_ms.append(latency_ms)
        elif stage == 'rule_scoring':
            self.rule_scoring_ms.append(latency_ms)
        elif stage == 'total':
            self.total_scoring_ms.append(latency_ms)
    
    def get_stats(self, stage: str) -> Dict[str, float]:
        """Get statistics for a stage."""
        data = getattr(self, f"{stage}_ms", [])
        if not data:
            return {}
        
        return {
            'mean': float(np.mean(data)),
            'p50': float(np.percentile(data, 50)),
            'p95': float(np.percentile(data, 95)),
            'p99': float(np.percentile(data, 99)),
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'count': len(data)
        }
    
    def summarize(self) -> Dict[str, Dict]:
        """Get summary of all stages."""
        return {
            'feature_extraction': self.get_stats('feature_extraction'),
            'ml_scoring': self.get_stats('ml_scoring'),
            'rule_scoring': self.get_stats('rule_scoring'),
            'total': self.get_stats('total')
        }
    
    def reset(self):
        """Reset all metrics."""
        self.feature_extraction_ms.clear()
        self.ml_scoring_ms.clear()
        self.rule_scoring_ms.clear()
        self.total_scoring_ms.clear()


class ObservabilityTracker:
    """
    Track metrics for observability.
    CPU-efficient with rolling windows.
    """
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self.latency_metrics = LatencyMetrics()
        
        # Rolling windows for efficient memory usage
        self.scores = deque(maxlen=max_history)
        self.confidences = deque(maxlen=max_history)
        self.uncertainties = deque(maxlen=max_history)
        self.predictions = deque(maxlen=max_history)
        
        # Counters
        self.total_requests = 0
        self.actionable_count = 0
        self.high_uncertainty_count = 0
        
        # V3: Signal counters
        self.concession_count = 0
        self.monetization_complaint_count = 0
        self.retention_signal_count = 0
        self.feature_request_count = 0
        
        # Timestamps
        self.start_time = time.time()
        self.last_log_time = time.time()
    
    def record_prediction(
        self,
        score: float,
        confidence: float,
        uncertainty: float,
        is_actionable: bool,
        has_concession: bool = False,
        has_monetization_complaint: bool = False,
        has_retention_signal: bool = False,
        feature_request_count: int = 0
    ):
        """Record a prediction and its metadata."""
        self.total_requests += 1
        
        self.scores.append(score)
        self.confidences.append(confidence)
        self.uncertainties.append(uncertainty)
        self.predictions.append(int(is_actionable))
        
        if is_actionable:
            self.actionable_count += 1
        
        if uncertainty > 0.3:
            self.high_uncertainty_count += 1
        
        # V3 signals
        if has_concession:
            self.concession_count += 1
        if has_monetization_complaint:
            self.monetization_complaint_count += 1
        if has_retention_signal:
            self.retention_signal_count += 1
        if feature_request_count > 0:
            self.feature_request_count += feature_request_count
    
    def get_uncertainty_distribution(self) -> Dict[str, any]:
        """Get uncertainty distribution statistics."""
        if len(self.uncertainties) == 0:
            return {}
        
        uncertainties = np.array(self.uncertainties)
        
        # Binned distribution
        bins = [0, 0.1, 0.2, 0.3, 0.5, 1.0]
        hist, _ = np.histogram(uncertainties, bins=bins)
        
        return {
            'mean': float(np.mean(uncertainties)),
            'median': float(np.median(uncertainties)),
            'p95': float(np.percentile(uncertainties, 95)),
            'std': float(np.std(uncertainties)),
            'bins': {
                'very_low (0-0.1)': int(hist[0]),
                'low (0.1-0.2)': int(hist[1]),
                'medium (0.2-0.3)': int(hist[2]),
                'high (0.3-0.5)': int(hist[3]),
                'very_high (0.5-1.0)': int(hist[4])
            },
            'high_uncertainty_rate': float(self.high_uncertainty_count / self.total_requests)
        }
    
    def get_confidence_distribution(self) -> Dict[str, any]:
        """Get confidence distribution statistics."""
        if len(self.confidences) == 0:
            return {}
        
        confidences = np.array(self.confidences)
        
        return {
            'mean': float(np.mean(confidences)),
            'median': float(np.median(confidences)),
            'p05': float(np.percentile(confidences, 5)),
            'p95': float(np.percentile(confidences, 95)),
            'std': float(np.std(confidences))
        }
    
    def get_signal_statistics(self) -> Dict[str, any]:
        """Get V3 signal statistics."""
        if self.total_requests == 0:
            return {}
        
        return {
            'concession_rate': float(self.concession_count / self.total_requests),
            'monetization_complaint_rate': float(self.monetization_complaint_count / self.total_requests),
            'retention_signal_rate': float(self.retention_signal_count / self.total_requests),
            'avg_feature_requests_per_review': float(self.feature_request_count / self.total_requests),
            'counts': {
                'concession': self.concession_count,
                'monetization_complaint': self.monetization_complaint_count,
                'retention_signal': self.retention_signal_count,
                'feature_requests': self.feature_request_count
            }
        }
    
    def get_summary(self) -> Dict[str, any]:
        """Get comprehensive metrics summary."""
        uptime_seconds = time.time() - self.start_time
        
        return {
            'uptime_seconds': uptime_seconds,
            'total_requests': self.total_requests,
            'requests_per_second': self.total_requests / uptime_seconds if uptime_seconds > 0 else 0,
            'actionable_count': self.actionable_count,
            'actionable_rate': self.actionable_count / self.total_requests if self.total_requests > 0 else 0,
            'latency': self.latency_metrics.summarize(),
            'uncertainty_distribution': self.get_uncertainty_distribution(),
            'confidence_distribution': self.get_confidence_distribution(),
            'signal_statistics': self.get_signal_statistics()
        }
    
    def log_summary(self, interval_seconds: int = 300):
        """Log summary if interval has passed."""
        current_time = time.time()
        if current_time - self.last_log_time >= interval_seconds:
            summary = self.get_summary()
            logger.info("="*80)
            logger.info("OBSERVABILITY SUMMARY")
            logger.info("="*80)
            logger.info(f"Total requests: {summary['total_requests']}")
            logger.info(f"Actionable rate: {summary['actionable_rate']:.1%}")
            logger.info(f"Requests/sec: {summary['requests_per_second']:.2f}")
            
            if summary['latency']['total']:
                logger.info(f"Latency (total): p50={summary['latency']['total']['p50']:.1f}ms, p95={summary['latency']['total']['p95']:.1f}ms")
            
            if summary['uncertainty_distribution']:
                logger.info(f"Uncertainty: mean={summary['uncertainty_distribution']['mean']:.3f}, high_rate={summary['uncertainty_distribution']['high_uncertainty_rate']:.1%}")
            
            if summary['signal_statistics']:
                logger.info(f"V3 Signals: retention={summary['signal_statistics']['retention_signal_rate']:.1%}, monetization={summary['signal_statistics']['monetization_complaint_rate']:.1%}")
            
            logger.info("="*80)
            
            self.last_log_time = current_time
    
    def save_metrics(self, output_path: str):
        """Save metrics to JSON file."""
        summary = self.get_summary()
        
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Metrics saved to {output_path}")
    
    def reset(self):
        """Reset all metrics."""
        self.latency_metrics.reset()
        self.scores.clear()
        self.confidences.clear()
        self.uncertainties.clear()
        self.predictions.clear()
        
        self.total_requests = 0
        self.actionable_count = 0
        self.high_uncertainty_count = 0
        
        self.concession_count = 0
        self.monetization_complaint_count = 0
        self.retention_signal_count = 0
        self.feature_request_count = 0
        
        self.start_time = time.time()
        self.last_log_time = time.time()


def create_health_endpoint_data(
    scorer,
    tracker: ObservabilityTracker,
    model_version: str = "v3.0"
) -> Dict[str, any]:
    """
    Create health endpoint data for API.
    
    Args:
        scorer: HybridActionabilityScorer instance
        tracker: ObservabilityTracker instance
        model_version: Model version string
        
    Returns:
        Health data dict
    """
    import psutil
    
    # Model status
    model_status = {
        'version': model_version,
        'online_model_trained': scorer.online_model_trained,
        'batch_model_trained': scorer.batch_model_trained,
        'calibrators_fitted': scorer.calibrators_fitted,
        'calibration_method': scorer.calibration_method,
        'is_trained': scorer.is_trained
    }
    
    # Calibration stats
    calibration_stats = {}
    if scorer.calibrators_fitted:
        calibration_stats['online_fitted'] = True
        calibration_stats['batch_fitted'] = True
        calibration_stats['method'] = scorer.calibration_method
    
    # System metrics
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    
    system_metrics = {
        'cpu_percent': cpu_percent,
        'memory_used_mb': memory.used / (1024 * 1024),
        'memory_percent': memory.percent
    }
    
    # Tracker summary
    tracker_summary = tracker.get_summary()
    
    # Health status
    health_status = 'healthy'
    issues = []
    
    if not scorer.is_trained:
        health_status = 'degraded'
        issues.append('Models not trained')
    
    if cpu_percent > 90:
        health_status = 'degraded'
        issues.append(f'High CPU usage: {cpu_percent:.1f}%')
    
    if memory.percent > 90:
        health_status = 'degraded'
        issues.append(f'High memory usage: {memory.percent:.1f}%')
    
    latency_total = tracker_summary.get('latency', {}).get('total', {})
    if latency_total.get('p95', 0) > 50:  # p95 > 50ms
        health_status = 'degraded'
        issues.append(f"High latency: p95={latency_total['p95']:.1f}ms")
    
    return {
        'status': health_status,
        'issues': issues,
        'model': model_status,
        'calibration': calibration_stats,
        'system': system_metrics,
        'metrics': tracker_summary,
        'timestamp': time.time()
    }
