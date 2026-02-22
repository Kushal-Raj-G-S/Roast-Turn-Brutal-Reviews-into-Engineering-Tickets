"""
Degradation Detection Module

Monitors system health and detects degradation:
- Cluster count drastic changes
- Uncertainty spikes
- Actionable rate anomalies
- Performance degradation

Generates alerts when metrics deviate from baseline.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DegradationAlert:
    """Alert for detected degradation."""
    severity: str  # 'critical', 'high', 'medium', 'low'
    metric: str
    message: str
    baseline_value: Optional[float] = None
    current_value: Optional[float] = None
    change_pct: Optional[float] = None
    threshold_exceeded: Optional[str] = None


@dataclass
class BaselineMetrics:
    """Baseline metrics for comparison."""
    cluster_count: int
    avg_cluster_size: float
    actionable_rate: float
    avg_uncertainty: float
    high_uncertainty_rate: float
    avg_latency_ms: float
    success_rate: float


@dataclass
class DegradationReport:
    """Report of detected degradations."""
    test_name: str
    timestamp: str
    baseline_metrics: BaselineMetrics
    current_metrics: BaselineMetrics
    alerts: List[DegradationAlert] = field(default_factory=list)
    overall_health: str = "healthy"  # 'healthy', 'degraded', 'critical'


class DegradationDetector:
    """
    Detects system degradation by comparing metrics against baselines.
    
    Thresholds:
    - Cluster count: ±30% change = alert
    - Uncertainty: +50% high-uncertainty reviews = alert
    - Actionable rate: ±20% change = alert
    - Latency: +100% = alert
    - Success rate: -5% = alert
    """
    
    # Thresholds for alerts
    CLUSTER_COUNT_THRESHOLD = 0.30  # 30% change
    UNCERTAINTY_SPIKE_THRESHOLD = 0.50  # 50% increase in high-uncertainty
    ACTIONABLE_RATE_THRESHOLD = 0.20  # 20% change
    LATENCY_THRESHOLD = 1.00  # 100% increase (2x slower)
    SUCCESS_RATE_THRESHOLD = 0.05  # 5% drop
    
    def __init__(self):
        self.baselines: Dict[str, BaselineMetrics] = {}
    
    def set_baseline(
        self,
        baseline_name: str,
        cluster_count: int,
        avg_cluster_size: float,
        actionable_rate: float,
        avg_uncertainty: float,
        high_uncertainty_rate: float,
        avg_latency_ms: float,
        success_rate: float = 1.0
    ):
        """
        Set baseline metrics for comparison.
        
        Args:
            baseline_name: Name of the baseline (e.g., 'clean_data')
            cluster_count: Number of clusters
            avg_cluster_size: Average reviews per cluster
            actionable_rate: Fraction of actionable reviews
            avg_uncertainty: Mean uncertainty score
            high_uncertainty_rate: Fraction with uncertainty > 0.3
            avg_latency_ms: Average processing time per review
            success_rate: Processing success rate
        """
        self.baselines[baseline_name] = BaselineMetrics(
            cluster_count=cluster_count,
            avg_cluster_size=avg_cluster_size,
            actionable_rate=actionable_rate,
            avg_uncertainty=avg_uncertainty,
            high_uncertainty_rate=high_uncertainty_rate,
            avg_latency_ms=avg_latency_ms,
            success_rate=success_rate
        )
        logger.info(f"Set baseline '{baseline_name}': {cluster_count} clusters, "
                   f"{actionable_rate:.1%} actionable, {avg_latency_ms:.1f}ms latency")
    
    def detect_degradation(
        self,
        test_name: str,
        baseline_name: str,
        current_cluster_count: int,
        current_avg_cluster_size: float,
        current_actionable_rate: float,
        current_avg_uncertainty: float,
        current_high_uncertainty_rate: float,
        current_avg_latency_ms: float,
        current_success_rate: float = 1.0
    ) -> DegradationReport:
        """
        Detect degradation by comparing current metrics to baseline.
        
        Returns:
            DegradationReport with alerts
        """
        if baseline_name not in self.baselines:
            logger.error(f"Baseline '{baseline_name}' not found")
            return DegradationReport(
                test_name=test_name,
                timestamp=pd.Timestamp.now().isoformat(),
                baseline_metrics=BaselineMetrics(0, 0, 0, 0, 0, 0, 0),
                current_metrics=BaselineMetrics(0, 0, 0, 0, 0, 0, 0),
                alerts=[DegradationAlert(
                    severity='critical',
                    metric='baseline',
                    message=f"Baseline '{baseline_name}' not found"
                )]
            )
        
        baseline = self.baselines[baseline_name]
        current = BaselineMetrics(
            cluster_count=current_cluster_count,
            avg_cluster_size=current_avg_cluster_size,
            actionable_rate=current_actionable_rate,
            avg_uncertainty=current_avg_uncertainty,
            high_uncertainty_rate=current_high_uncertainty_rate,
            avg_latency_ms=current_avg_latency_ms,
            success_rate=current_success_rate
        )
        
        alerts = []
        
        # 1. Check cluster count change
        if baseline.cluster_count > 0:
            cluster_change_pct = ((current.cluster_count - baseline.cluster_count) 
                                 / baseline.cluster_count)
            if abs(cluster_change_pct) > self.CLUSTER_COUNT_THRESHOLD:
                severity = 'high' if abs(cluster_change_pct) > 0.5 else 'medium'
                direction = 'increased' if cluster_change_pct > 0 else 'decreased'
                alerts.append(DegradationAlert(
                    severity=severity,
                    metric='cluster_count',
                    message=f"Cluster count {direction} by {abs(cluster_change_pct):.0%} "
                           f"({baseline.cluster_count} → {current.cluster_count})",
                    baseline_value=float(baseline.cluster_count),
                    current_value=float(current.cluster_count),
                    change_pct=cluster_change_pct * 100,
                    threshold_exceeded=f">{self.CLUSTER_COUNT_THRESHOLD:.0%}"
                ))
        
        # 2. Check uncertainty spike
        if baseline.high_uncertainty_rate > 0:
            uncertainty_change = ((current.high_uncertainty_rate - baseline.high_uncertainty_rate)
                                 / baseline.high_uncertainty_rate)
            if uncertainty_change > self.UNCERTAINTY_SPIKE_THRESHOLD:
                alerts.append(DegradationAlert(
                    severity='high',
                    metric='uncertainty',
                    message=f"High-uncertainty reviews increased by {uncertainty_change:.0%} "
                           f"({baseline.high_uncertainty_rate:.1%} → {current.high_uncertainty_rate:.1%})",
                    baseline_value=baseline.high_uncertainty_rate,
                    current_value=current.high_uncertainty_rate,
                    change_pct=uncertainty_change * 100,
                    threshold_exceeded=f">{self.UNCERTAINTY_SPIKE_THRESHOLD:.0%}"
                ))
        
        # 3. Check actionable rate anomaly
        if baseline.actionable_rate > 0:
            actionable_change_pct = ((current.actionable_rate - baseline.actionable_rate)
                                    / baseline.actionable_rate)
            if abs(actionable_change_pct) > self.ACTIONABLE_RATE_THRESHOLD:
                severity = 'medium'
                direction = 'increased' if actionable_change_pct > 0 else 'decreased'
                alerts.append(DegradationAlert(
                    severity=severity,
                    metric='actionable_rate',
                    message=f"Actionable rate {direction} by {abs(actionable_change_pct):.0%} "
                           f"({baseline.actionable_rate:.1%} → {current.actionable_rate:.1%})",
                    baseline_value=baseline.actionable_rate,
                    current_value=current.actionable_rate,
                    change_pct=actionable_change_pct * 100,
                    threshold_exceeded=f">{self.ACTIONABLE_RATE_THRESHOLD:.0%}"
                ))
        
        # 4. Check latency increase
        if baseline.avg_latency_ms > 0:
            latency_change_pct = ((current.avg_latency_ms - baseline.avg_latency_ms)
                                 / baseline.avg_latency_ms)
            if latency_change_pct > self.LATENCY_THRESHOLD:
                alerts.append(DegradationAlert(
                    severity='high',
                    metric='latency',
                    message=f"Latency increased by {latency_change_pct:.0%} "
                           f"({baseline.avg_latency_ms:.1f}ms → {current.avg_latency_ms:.1f}ms)",
                    baseline_value=baseline.avg_latency_ms,
                    current_value=current.avg_latency_ms,
                    change_pct=latency_change_pct * 100,
                    threshold_exceeded=f">{self.LATENCY_THRESHOLD:.0%}"
                ))
        
        # 5. Check success rate drop
        success_rate_change = current.success_rate - baseline.success_rate
        if success_rate_change < -self.SUCCESS_RATE_THRESHOLD:
            alerts.append(DegradationAlert(
                severity='critical',
                metric='success_rate',
                message=f"Success rate dropped by {abs(success_rate_change):.1%} "
                       f"({baseline.success_rate:.1%} → {current.success_rate:.1%})",
                baseline_value=baseline.success_rate,
                current_value=current.success_rate,
                change_pct=success_rate_change * 100,
                threshold_exceeded=f"<{-self.SUCCESS_RATE_THRESHOLD:.0%}"
            ))
        
        # Determine overall health
        overall_health = "healthy"
        if any(a.severity == 'critical' for a in alerts):
            overall_health = "critical"
        elif any(a.severity == 'high' for a in alerts):
            overall_health = "degraded"
        elif len(alerts) > 0:
            overall_health = "degraded"
        
        report = DegradationReport(
            test_name=test_name,
            timestamp=pd.Timestamp.now().isoformat(),
            baseline_metrics=baseline,
            current_metrics=current,
            alerts=alerts,
            overall_health=overall_health
        )
        
        logger.info(f"Degradation detection complete: {len(alerts)} alerts, health={overall_health}")
        
        return report
    
    def detect_from_results(
        self,
        test_name: str,
        baseline_name: str,
        results_csv: str,
        clusters_csv: Optional[str] = None,
        robustness_report: Optional[Any] = None
    ) -> DegradationReport:
        """
        Detect degradation from result files.
        
        Args:
            test_name: Name of the test
            baseline_name: Name of baseline to compare against
            results_csv: Path to scoring results CSV
            clusters_csv: Optional path to clustering results
            robustness_report: Optional robustness test report
            
        Returns:
            DegradationReport
        """
        try:
            results_df = pd.read_csv(results_csv)
        except Exception as e:
            logger.error(f"Failed to load results: {e}")
            return DegradationReport(
                test_name=test_name,
                timestamp=pd.Timestamp.now().isoformat(),
                baseline_metrics=BaselineMetrics(0, 0, 0, 0, 0, 0, 0),
                current_metrics=BaselineMetrics(0, 0, 0, 0, 0, 0, 0),
                alerts=[DegradationAlert(
                    severity='critical',
                    metric='file_error',
                    message=f"Failed to load results: {e}"
                )]
            )
        
        # Extract metrics from results
        actionable_rate = 0.0
        avg_uncertainty = 0.0
        high_uncertainty_rate = 0.0
        
        if 'is_actionable' in results_df.columns:
            actionable_rate = results_df['is_actionable'].mean()
        
        if 'uncertainty' in results_df.columns:
            uncertainties = results_df['uncertainty'].dropna()
            if len(uncertainties) > 0:
                avg_uncertainty = uncertainties.mean()
                high_uncertainty_rate = (uncertainties > 0.3).mean()
        
        # Cluster metrics
        cluster_count = 0
        avg_cluster_size = 0.0
        if clusters_csv:
            try:
                clusters_df = pd.read_csv(clusters_csv)
                cluster_col = 'cluster_id' if 'cluster_id' in clusters_df.columns else 'cluster_label'
                if cluster_col in clusters_df.columns:
                    cluster_sizes = clusters_df[cluster_col].value_counts()
                    cluster_count = len(cluster_sizes)
                    avg_cluster_size = cluster_sizes.mean() if len(cluster_sizes) > 0 else 0.0
            except Exception as e:
                logger.warning(f"Failed to load clusters: {e}")
        
        # Latency and success rate
        avg_latency_ms = 0.0
        success_rate = 1.0
        if robustness_report:
            if 'total' in robustness_report.latency_by_stage:
                avg_latency_ms = robustness_report.latency_by_stage['total'].mean_ms
            success_rate = robustness_report.success_rate
        
        return self.detect_degradation(
            test_name=test_name,
            baseline_name=baseline_name,
            current_cluster_count=cluster_count,
            current_avg_cluster_size=avg_cluster_size,
            current_actionable_rate=actionable_rate,
            current_avg_uncertainty=avg_uncertainty,
            current_high_uncertainty_rate=high_uncertainty_rate,
            current_avg_latency_ms=avg_latency_ms,
            current_success_rate=success_rate
        )


def generate_degradation_report_md(report: DegradationReport) -> str:
    """
    Generate Markdown report for degradation detection.
    
    Args:
        report: DegradationReport
        
    Returns:
        Markdown string
    """
    lines = [
        f"# Degradation Detection Report: {report.test_name}",
        "",
        f"**Timestamp**: {report.timestamp}",
        f"**Overall Health**: {report.overall_health.upper()}",
        "",
        "## Summary",
        f"- **Total Alerts**: {len(report.alerts)}",
        f"- **Critical**: {sum(1 for a in report.alerts if a.severity == 'critical')}",
        f"- **High**: {sum(1 for a in report.alerts if a.severity == 'high')}",
        f"- **Medium**: {sum(1 for a in report.alerts if a.severity == 'medium')}",
        f"- **Low**: {sum(1 for a in report.alerts if a.severity == 'low')}",
        "",
    ]
    
    if report.alerts:
        lines.extend([
            "## Alerts",
            ""
        ])
        
        for alert in sorted(report.alerts, key=lambda a: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}[a.severity]):
            emoji = {
                'critical': '🚨',
                'high': '⚠️',
                'medium': '⚡',
                'low': 'ℹ️'
            }[alert.severity]
            
            lines.append(f"### {emoji} {alert.severity.upper()}: {alert.metric}")
            lines.append(f"**Message**: {alert.message}")
            if alert.baseline_value is not None:
                lines.append(f"- Baseline: {alert.baseline_value:.4f}")
                lines.append(f"- Current: {alert.current_value:.4f}")
                lines.append(f"- Change: {alert.change_pct:+.1f}%")
            if alert.threshold_exceeded:
                lines.append(f"- Threshold: {alert.threshold_exceeded}")
            lines.append("")
    else:
        lines.extend([
            "## ✅ No Degradation Detected",
            "",
            "All metrics are within acceptable thresholds.",
            ""
        ])
    
    lines.extend([
        "## Baseline vs Current Metrics",
        "",
        "| Metric | Baseline | Current | Change |",
        "|--------|----------|---------|--------|",
        f"| Cluster Count | {report.baseline_metrics.cluster_count} | {report.current_metrics.cluster_count} | {_format_change(report.baseline_metrics.cluster_count, report.current_metrics.cluster_count)} |",
        f"| Avg Cluster Size | {report.baseline_metrics.avg_cluster_size:.1f} | {report.current_metrics.avg_cluster_size:.1f} | {_format_change(report.baseline_metrics.avg_cluster_size, report.current_metrics.avg_cluster_size)} |",
        f"| Actionable Rate | {report.baseline_metrics.actionable_rate:.1%} | {report.current_metrics.actionable_rate:.1%} | {_format_change(report.baseline_metrics.actionable_rate, report.current_metrics.actionable_rate)} |",
        f"| Avg Uncertainty | {report.baseline_metrics.avg_uncertainty:.3f} | {report.current_metrics.avg_uncertainty:.3f} | {_format_change(report.baseline_metrics.avg_uncertainty, report.current_metrics.avg_uncertainty)} |",
        f"| High Uncertainty Rate | {report.baseline_metrics.high_uncertainty_rate:.1%} | {report.current_metrics.high_uncertainty_rate:.1%} | {_format_change(report.baseline_metrics.high_uncertainty_rate, report.current_metrics.high_uncertainty_rate)} |",
        f"| Avg Latency (ms) | {report.baseline_metrics.avg_latency_ms:.1f} | {report.current_metrics.avg_latency_ms:.1f} | {_format_change(report.baseline_metrics.avg_latency_ms, report.current_metrics.avg_latency_ms)} |",
        f"| Success Rate | {report.baseline_metrics.success_rate:.1%} | {report.current_metrics.success_rate:.1%} | {_format_change(report.baseline_metrics.success_rate, report.current_metrics.success_rate)} |",
        ""
    ])
    
    return "\n".join(lines)


def _format_change(baseline: float, current: float) -> str:
    """Format percentage change for table."""
    if baseline == 0:
        return "N/A"
    change_pct = ((current - baseline) / baseline) * 100
    if abs(change_pct) < 0.1:
        return "~0%"
    sign = "+" if change_pct > 0 else ""
    return f"{sign}{change_pct:.1f}%"
