"""
Drift Dashboard and Alerting Module

Provides temporal drift visualization, anomaly alerts, and emerging risk reporting.
Aggregates data from drift detection, concept drift, and adversarial detection.

Author: V3 System
Created: 2026-02-22
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import json
from pathlib import Path

from .drift_detection import DriftReport, DataDriftDetector
from .concept_drift import ConceptDriftReport, ConceptDriftDetector
from .adversarial_detection import AdversarialReport, AdversarialDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """Alert rule definition"""
    name: str
    metric: str
    threshold: float
    comparison: str  # 'gt', 'lt', 'eq', 'ne'
    severity: str  # 'info', 'warning', 'critical'
    description: str
    enabled: bool = True


@dataclass
class Alert:
    """Generated alert"""
    alert_id: str
    timestamp: str
    rule_name: str
    severity: str
    metric: str
    current_value: float
    threshold: float
    message: str
    details: Dict = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class DashboardMetrics:
    """Aggregated metrics for dashboard"""
    timestamp: str
    
    # Data drift metrics
    embedding_psi: float
    vocabulary_change_pct: float
    sentiment_shift: float
    
    # Concept drift metrics
    emerging_clusters: int
    disappeared_clusters: int
    growing_clusters: int
    cluster_stability_score: float
    
    # Adversarial metrics
    fake_positive_rate: float
    sarcasm_rate: float
    spam_rate: float
    coordinated_burst_count: int
    
    # Overall health
    overall_health_score: float
    risk_level: str  # 'low', 'medium', 'high', 'critical'


@dataclass
class DashboardReport:
    """Comprehensive dashboard report"""
    report_id: str
    timestamp: str
    period: str
    metrics: DashboardMetrics
    active_alerts: List[Alert]
    drift_report: Optional[DriftReport]
    concept_report: Optional[ConceptDriftReport]
    adversarial_report: Optional[AdversarialReport]
    trends: Dict[str, List[float]]
    recommendations: List[str]


class DriftDashboard:
    """
    Aggregates and visualizes drift detection results.
    
    Features:
    - Unified metrics from all drift detectors
    - Configurable alert rules
    - Temporal trend tracking
    - Risk scoring and prioritization
    - Report generation (Markdown, JSON)
    """
    
    # Default alert rules
    DEFAULT_ALERT_RULES = [
        AlertRule(
            name='high_embedding_drift',
            metric='embedding_psi',
            threshold=0.25,
            comparison='gt',
            severity='critical',
            description='Embedding distribution has drifted significantly'
        ),
        AlertRule(
            name='high_vocabulary_change',
            metric='vocabulary_change_pct',
            threshold=0.20,
            comparison='gt',
            severity='warning',
            description='Vocabulary has changed significantly'
        ),
        AlertRule(
            name='sentiment_degradation',
            metric='sentiment_shift',
            threshold=-0.5,
            comparison='lt',
            severity='warning',
            description='User sentiment has degraded'
        ),
        AlertRule(
            name='many_emerging_clusters',
            metric='emerging_clusters',
            threshold=3,
            comparison='gt',
            severity='warning',
            description='Multiple new complaint categories detected'
        ),
        AlertRule(
            name='high_fake_positive_rate',
            metric='fake_positive_rate',
            threshold=0.10,
            comparison='gt',
            severity='critical',
            description='High rate of fake positive reviews detected'
        ),
        AlertRule(
            name='coordinated_attacks',
            metric='coordinated_burst_count',
            threshold=2,
            comparison='gt',
            severity='critical',
            description='Multiple coordinated review bursts detected'
        ),
        AlertRule(
            name='low_cluster_stability',
            metric='cluster_stability_score',
            threshold=0.5,
            comparison='lt',
            severity='warning',
            description='Cluster structure is unstable'
        ),
    ]
    
    def __init__(self, alert_rules: Optional[List[AlertRule]] = None):
        """
        Initialize drift dashboard.
        
        Args:
            alert_rules: Custom alert rules (uses defaults if None)
        """
        self.alert_rules = alert_rules or self.DEFAULT_ALERT_RULES
        self.metrics_history: List[DashboardMetrics] = []
        self.alerts_history: List[Alert] = []
        logger.info(f"Initialized DriftDashboard with {len(self.alert_rules)} alert rules")
    
    def create_dashboard_report(
        self,
        drift_report: Optional[DriftReport] = None,
        concept_report: Optional[ConceptDriftReport] = None,
        adversarial_report: Optional[AdversarialReport] = None,
        period: str = "current"
    ) -> DashboardReport:
        """
        Create comprehensive dashboard report from individual reports.
        
        Args:
            drift_report: Data drift detection report
            concept_report: Concept drift detection report
            adversarial_report: Adversarial detection report
            period: Period label for report
            
        Returns:
            DashboardReport with aggregated metrics and alerts
        """
        timestamp = datetime.now().isoformat()
        report_id = f"dashboard_{timestamp.replace(':', '-').replace('.', '-')}"
        
        # Extract metrics
        metrics = self._extract_metrics(drift_report, concept_report, adversarial_report, timestamp)
        
        # Store in history
        self.metrics_history.append(metrics)
        
        # Check alert rules
        active_alerts = self._check_alert_rules(metrics)
        
        # Store alerts in history
        self.alerts_history.extend(active_alerts)
        
        # Calculate trends
        trends = self._calculate_trends()
        
        # Generate recommendations
        recommendations = self._generate_dashboard_recommendations(
            metrics, active_alerts, drift_report, concept_report, adversarial_report
        )
        
        return DashboardReport(
            report_id=report_id,
            timestamp=timestamp,
            period=period,
            metrics=metrics,
            active_alerts=active_alerts,
            drift_report=drift_report,
            concept_report=concept_report,
            adversarial_report=adversarial_report,
            trends=trends,
            recommendations=recommendations
        )
    
    def _extract_metrics(
        self,
        drift_report: Optional[DriftReport],
        concept_report: Optional[ConceptDriftReport],
        adversarial_report: Optional[AdversarialReport],
        timestamp: str
    ) -> DashboardMetrics:
        """Extract and aggregate metrics from all reports"""
        
        # Data drift metrics
        embedding_psi = 0.0
        vocabulary_change_pct = 0.0
        sentiment_shift = 0.0
        
        if drift_report:
            if drift_report.embedding_drift:
                embedding_psi = drift_report.embedding_drift.psi_score
            if drift_report.vocabulary_drift:
                vocabulary_change_pct = drift_report.vocabulary_drift.new_words_ratio
            if drift_report.sentiment_drift:
                sentiment_shift = drift_report.sentiment_drift.mean_shift
        
        # Concept drift metrics
        emerging_clusters = 0
        disappeared_clusters = 0
        growing_clusters = 0
        cluster_stability_score = 1.0
        
        if concept_report:
            emerging_clusters = len(concept_report.emerging_clusters)
            disappeared_clusters = len(concept_report.disappeared_clusters)
            growing_clusters = len(concept_report.growing_clusters)
            
            # Calculate cluster stability (inverse of drift)
            if concept_report.total_baseline_clusters > 0:
                stable_ratio = len(concept_report.stable_clusters) / concept_report.total_baseline_clusters
                cluster_stability_score = stable_ratio
        
        # Adversarial metrics
        fake_positive_rate = 0.0
        sarcasm_rate = 0.0
        spam_rate = 0.0
        coordinated_burst_count = 0
        
        if adversarial_report:
            total = adversarial_report.total_reviews
            if total > 0:
                fake_positive_rate = adversarial_report.fake_positive_count / total
                sarcasm_rate = adversarial_report.sarcasm_count / total
                spam_rate = adversarial_report.spam_count / total
            coordinated_burst_count = len(adversarial_report.coordinated_bursts)
        
        # Calculate overall health score
        health_score = self._calculate_health_score(
            embedding_psi, vocabulary_change_pct, sentiment_shift,
            emerging_clusters, cluster_stability_score,
            fake_positive_rate, spam_rate, coordinated_burst_count
        )
        
        # Determine risk level
        risk_level = self._determine_risk_level(health_score)
        
        return DashboardMetrics(
            timestamp=timestamp,
            embedding_psi=embedding_psi,
            vocabulary_change_pct=vocabulary_change_pct,
            sentiment_shift=sentiment_shift,
            emerging_clusters=emerging_clusters,
            disappeared_clusters=disappeared_clusters,
            growing_clusters=growing_clusters,
            cluster_stability_score=cluster_stability_score,
            fake_positive_rate=fake_positive_rate,
            sarcasm_rate=sarcasm_rate,
            spam_rate=spam_rate,
            coordinated_burst_count=coordinated_burst_count,
            overall_health_score=health_score,
            risk_level=risk_level
        )
    
    def _calculate_health_score(
        self,
        embedding_psi: float,
        vocab_change: float,
        sentiment_shift: float,
        emerging_clusters: int,
        cluster_stability: float,
        fake_rate: float,
        spam_rate: float,
        coordinated_count: int
    ) -> float:
        """
        Calculate overall health score (0-1, higher is better).
        
        Considers all drift and adversarial metrics.
        """
        score = 1.0
        
        # Data drift penalties
        if embedding_psi > 0.25:
            score -= 0.3
        elif embedding_psi > 0.1:
            score -= 0.1
        
        if vocab_change > 0.3:
            score -= 0.2
        elif vocab_change > 0.15:
            score -= 0.1
        
        if abs(sentiment_shift) > 0.5:
            score -= 0.2
        elif abs(sentiment_shift) > 0.3:
            score -= 0.1
        
        # Concept drift penalties
        if emerging_clusters > 5:
            score -= 0.2
        elif emerging_clusters > 3:
            score -= 0.1
        
        if cluster_stability < 0.5:
            score -= 0.2
        elif cluster_stability < 0.7:
            score -= 0.1
        
        # Adversarial penalties
        if fake_rate > 0.15:
            score -= 0.3
        elif fake_rate > 0.1:
            score -= 0.15
        
        if spam_rate > 0.1:
            score -= 0.2
        elif spam_rate > 0.05:
            score -= 0.1
        
        if coordinated_count > 2:
            score -= 0.3
        elif coordinated_count > 0:
            score -= 0.1
        
        return max(0.0, score)
    
    def _determine_risk_level(self, health_score: float) -> str:
        """Determine risk level from health score"""
        if health_score >= 0.8:
            return 'low'
        elif health_score >= 0.6:
            return 'medium'
        elif health_score >= 0.4:
            return 'high'
        else:
            return 'critical'
    
    def _check_alert_rules(self, metrics: DashboardMetrics) -> List[Alert]:
        """Check all alert rules against current metrics"""
        alerts = []
        
        for rule in self.alert_rules:
            if not rule.enabled:
                continue
            
            # Get metric value
            metric_value = getattr(metrics, rule.metric, None)
            if metric_value is None:
                continue
            
            # Check threshold
            triggered = False
            if rule.comparison == 'gt' and metric_value > rule.threshold:
                triggered = True
            elif rule.comparison == 'lt' and metric_value < rule.threshold:
                triggered = True
            elif rule.comparison == 'eq' and metric_value == rule.threshold:
                triggered = True
            elif rule.comparison == 'ne' and metric_value != rule.threshold:
                triggered = True
            
            if triggered:
                alert = Alert(
                    alert_id=f"{rule.name}_{metrics.timestamp}",
                    timestamp=metrics.timestamp,
                    rule_name=rule.name,
                    severity=rule.severity,
                    metric=rule.metric,
                    current_value=float(metric_value),
                    threshold=rule.threshold,
                    message=f"{rule.description} (current: {metric_value:.3f}, threshold: {rule.threshold})",
                    details={'comparison': rule.comparison}
                )
                alerts.append(alert)
        
        return alerts
    
    def _calculate_trends(self, window_size: int = 10) -> Dict[str, List[float]]:
        """Calculate trends from metrics history"""
        trends = {}
        
        if len(self.metrics_history) < 2:
            return trends
        
        # Get recent metrics
        recent = self.metrics_history[-window_size:]
        
        # Extract trend for each metric
        metrics_to_track = [
            'embedding_psi', 'vocabulary_change_pct', 'sentiment_shift',
            'emerging_clusters', 'cluster_stability_score',
            'fake_positive_rate', 'spam_rate', 'overall_health_score'
        ]
        
        for metric_name in metrics_to_track:
            values = [getattr(m, metric_name, 0.0) for m in recent]
            trends[metric_name] = values
        
        return trends
    
    def _generate_dashboard_recommendations(
        self,
        metrics: DashboardMetrics,
        alerts: List[Alert],
        drift_report: Optional[DriftReport],
        concept_report: Optional[ConceptDriftReport],
        adversarial_report: Optional[AdversarialReport]
    ) -> List[str]:
        """Generate actionable recommendations based on all reports"""
        recommendations = []
        
        # Critical alerts first
        critical_alerts = [a for a in alerts if a.severity == 'critical']
        if critical_alerts:
            recommendations.append(
                f"🚨 URGENT: {len(critical_alerts)} critical alerts require immediate attention"
            )
        
        # Data drift recommendations
        if drift_report and drift_report.recommendations:
            recommendations.extend(drift_report.recommendations[:2])
        
        # Concept drift recommendations
        if concept_report and concept_report.recommendations:
            recommendations.extend(concept_report.recommendations[:2])
        
        # Adversarial recommendations
        if adversarial_report and adversarial_report.recommendations:
            recommendations.extend(adversarial_report.recommendations[:2])
        
        # Overall health recommendations
        if metrics.overall_health_score < 0.5:
            recommendations.append(
                "⚠️ System health is degraded. Review all drift and adversarial reports immediately."
            )
        elif metrics.overall_health_score < 0.7:
            recommendations.append(
                "📊 System health is acceptable but monitoring recommended."
            )
        
        if not recommendations:
            recommendations.append("✅ All systems healthy. Continue normal monitoring.")
        
        return recommendations[:10]  # Limit to top 10
    
    def save_dashboard_report(
        self,
        report: DashboardReport,
        output_dir: str
    ) -> None:
        """Save dashboard report to JSON and Markdown"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save JSON
        json_path = output_path / f"{report.report_id}.json"
        self._save_json_report(report, str(json_path))
        
        # Save Markdown
        md_path = output_path / f"{report.report_id}.md"
        self.generate_markdown_dashboard(report, str(md_path))
        
        logger.info(f"Dashboard report saved to {output_dir}")
    
    def _save_json_report(self, report: DashboardReport, output_path: str) -> None:
        """Save dashboard report to JSON"""
        try:
            report_dict = {
                'report_id': report.report_id,
                'timestamp': report.timestamp,
                'period': report.period,
                'metrics': {
                    'timestamp': report.metrics.timestamp,
                    'embedding_psi': report.metrics.embedding_psi,
                    'vocabulary_change_pct': report.metrics.vocabulary_change_pct,
                    'sentiment_shift': report.metrics.sentiment_shift,
                    'emerging_clusters': report.metrics.emerging_clusters,
                    'disappeared_clusters': report.metrics.disappeared_clusters,
                    'growing_clusters': report.metrics.growing_clusters,
                    'cluster_stability_score': report.metrics.cluster_stability_score,
                    'fake_positive_rate': report.metrics.fake_positive_rate,
                    'sarcasm_rate': report.metrics.sarcasm_rate,
                    'spam_rate': report.metrics.spam_rate,
                    'coordinated_burst_count': report.metrics.coordinated_burst_count,
                    'overall_health_score': report.metrics.overall_health_score,
                    'risk_level': report.metrics.risk_level
                },
                'active_alerts': [
                    {
                        'alert_id': a.alert_id,
                        'severity': a.severity,
                        'metric': a.metric,
                        'current_value': a.current_value,
                        'threshold': a.threshold,
                        'message': a.message
                    }
                    for a in report.active_alerts
                ],
                'recommendations': report.recommendations,
                'trends': report.trends
            }
            
            with open(output_path, 'w') as f:
                json.dump(report_dict, f, indent=2)
            
        except Exception as e:
            logger.error(f"Error saving JSON report: {e}")
            raise
    
    def generate_markdown_dashboard(
        self,
        report: DashboardReport,
        output_path: str
    ) -> None:
        """Generate comprehensive Markdown dashboard"""
        try:
            lines = []
            lines.append("# 📊 Drift Detection Dashboard")
            lines.append(f"\n**Report ID:** {report.report_id}")
            lines.append(f"**Generated:** {report.timestamp}")
            lines.append(f"**Period:** {report.period}")
            
            # Overall status
            risk_emoji = {'low': '✅', 'medium': '⚡', 'high': '⚠️', 'critical': '🚨'}
            lines.append(f"\n## Overall System Health")
            lines.append(f"\n{risk_emoji.get(report.metrics.risk_level, '❓')} **Health Score: {report.metrics.overall_health_score:.2f}** (Risk: {report.metrics.risk_level.upper()})")
            
            # Active alerts
            if report.active_alerts:
                lines.append(f"\n## 🚨 Active Alerts ({len(report.active_alerts)})")
                
                # Group by severity
                by_severity = {}
                for alert in report.active_alerts:
                    by_severity.setdefault(alert.severity, []).append(alert)
                
                for severity in ['critical', 'warning', 'info']:
                    if severity in by_severity:
                        sev_emoji = {'critical': '🔥', 'warning': '⚠️', 'info': 'ℹ️'}
                        lines.append(f"\n### {sev_emoji.get(severity, '❓')} {severity.upper()}")
                        for alert in by_severity[severity]:
                            lines.append(f"\n- **{alert.rule_name}**: {alert.message}")
            else:
                lines.append(f"\n## ✅ No Active Alerts")
            
            # Key metrics
            lines.append(f"\n## 📈 Key Metrics")
            
            lines.append(f"\n### Data Drift")
            lines.append(f"- **Embedding PSI:** {report.metrics.embedding_psi:.4f}")
            lines.append(f"- **Vocabulary Change:** {report.metrics.vocabulary_change_pct*100:.1f}%")
            lines.append(f"- **Sentiment Shift:** {report.metrics.sentiment_shift:+.3f}")
            
            lines.append(f"\n### Concept Drift")
            lines.append(f"- **Emerging Clusters:** {report.metrics.emerging_clusters}")
            lines.append(f"- **Disappeared Clusters:** {report.metrics.disappeared_clusters}")
            lines.append(f"- **Growing Clusters:** {report.metrics.growing_clusters}")
            lines.append(f"- **Cluster Stability:** {report.metrics.cluster_stability_score:.2f}")
            
            lines.append(f"\n### Adversarial Content")
            lines.append(f"- **Fake Positive Rate:** {report.metrics.fake_positive_rate*100:.1f}%")
            lines.append(f"- **Sarcasm Rate:** {report.metrics.sarcasm_rate*100:.1f}%")
            lines.append(f"- **Spam Rate:** {report.metrics.spam_rate*100:.1f}%")
            lines.append(f"- **Coordinated Bursts:** {report.metrics.coordinated_burst_count}")
            
            # Trends
            if report.trends:
                lines.append(f"\n## 📉 Trends")
                for metric, values in report.trends.items():
                    if values:
                        trend_direction = "↗️" if values[-1] > values[0] else "↘️"
                        lines.append(f"- **{metric}**: {trend_direction} {values[0]:.3f} → {values[-1]:.3f}")
            
            # Recommendations
            if report.recommendations:
                lines.append(f"\n## 💡 Recommendations")
                for i, rec in enumerate(report.recommendations, 1):
                    lines.append(f"\n{i}. {rec}")
            
            # Individual reports summary
            if report.drift_report:
                lines.append(f"\n## 📊 Data Drift Summary")
                lines.append(f"- Drift Detected: {'Yes ⚠️' if report.drift_report.overall_drift_detected else 'No ✅'}")
                lines.append(f"- Severity: {report.drift_report.overall_severity}")
            
            if report.concept_report:
                lines.append(f"\n## 🔄 Concept Drift Summary")
                lines.append(f"- Total Clusters: {report.concept_report.total_current_clusters}")
                lines.append(f"- Drift Detected: {'Yes ⚠️' if report.concept_report.concept_drift_detected else 'No ✅'}")
                lines.append(f"- Business Impact: {report.concept_report.business_impact}")
            
            if report.adversarial_report:
                lines.append(f"\n## 🛡️ Adversarial Detection Summary")
                lines.append(f"- Total Reviews: {report.adversarial_report.total_reviews}")
                lines.append(f"- High Risk: {len(report.adversarial_report.high_risk_reviews)}")
                lines.append(f"- Clean Reviews: {report.adversarial_report.detection_summary['clean_reviews']}")
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            logger.info(f"Markdown dashboard saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error generating markdown dashboard: {e}")
            raise
    
    def get_alert_summary(self) -> Dict[str, int]:
        """Get summary of alerts in history"""
        summary = {
            'total': len(self.alerts_history),
            'critical': sum(1 for a in self.alerts_history if a.severity == 'critical'),
            'warning': sum(1 for a in self.alerts_history if a.severity == 'warning'),
            'info': sum(1 for a in self.alerts_history if a.severity == 'info'),
            'acknowledged': sum(1 for a in self.alerts_history if a.acknowledged)
        }
        return summary
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged"""
        for alert in self.alerts_history:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                logger.info(f"Alert {alert_id} acknowledged")
                return True
        return False
