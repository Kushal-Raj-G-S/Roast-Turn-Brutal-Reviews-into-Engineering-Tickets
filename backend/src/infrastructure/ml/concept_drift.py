"""
Concept Drift Detection Module

Tracks cluster evolution, emerging complaint categories, and business signal changes over time.
Detects shifts in product pain points and monitors cluster stability.

Author: V3 System
Created: 2026-02-22
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict, Counter
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ClusterSnapshot:
    """Snapshot of cluster state at a point in time"""
    timestamp: str
    cluster_id: str
    cluster_theme: str
    size: int
    avg_severity: float
    avg_actionability: float
    avg_sentiment: float
    top_keywords: List[str]
    representative_reviews: List[str]


@dataclass
class ClusterEvolution:
    """Tracks how a cluster evolves over time"""
    cluster_id: str
    baseline_snapshot: ClusterSnapshot
    current_snapshot: Optional[ClusterSnapshot]
    status: str  # 'stable', 'growing', 'shrinking', 'disappeared', 'merged'
    size_change_pct: float
    severity_change: float
    actionability_change: float
    sentiment_change: float
    theme_similarity: float
    drift_detected: bool


@dataclass
class EmergingCluster:
    """Newly detected cluster not present in baseline"""
    cluster_id: str
    first_seen: str
    snapshot: ClusterSnapshot
    growth_rate: float
    urgency_score: float
    potential_risk: str  # 'low', 'medium', 'high', 'critical'


@dataclass
class ConceptDriftReport:
    """Comprehensive concept drift report"""
    report_id: str
    timestamp: str
    baseline_period: str
    current_period: str
    total_baseline_clusters: int
    total_current_clusters: int
    stable_clusters: List[ClusterEvolution]
    growing_clusters: List[ClusterEvolution]
    shrinking_clusters: List[ClusterEvolution]
    disappeared_clusters: List[ClusterEvolution]
    emerging_clusters: List[EmergingCluster]
    concept_drift_detected: bool
    drift_severity: str
    business_impact: str
    alerts: List[str]
    recommendations: List[str]


class ConceptDriftDetector:
    """
    Detects concept drift by tracking cluster evolution over time.
    
    Features:
    - Cluster theme comparison across time windows
    - Detection of emerging complaint categories
    - Monitoring of disappearing clusters
    - Severity and business signal tracking
    - Lightweight text similarity using keyword overlap
    """
    
    # Thresholds
    SIZE_CHANGE_THRESHOLD = 0.30  # 30% change in cluster size
    SEVERITY_CHANGE_THRESHOLD = 0.15  # 15% change in severity
    THEME_SIMILARITY_THRESHOLD = 0.5  # 50% keyword overlap to match themes
    EMERGING_CLUSTER_MIN_SIZE = 10  # Minimum size to flag as emerging
    CRITICAL_CLUSTER_SIZE = 100  # Size threshold for critical alert
    
    def __init__(self):
        """Initialize concept drift detector"""
        self.baseline_clusters: Dict[str, ClusterSnapshot] = {}
        self.baseline_timestamp = None
        self.cluster_history: List[Dict[str, ClusterSnapshot]] = []
        logger.info("Initialized ConceptDriftDetector")
    
    def set_baseline(
        self,
        clusters_df: pd.DataFrame,
        timestamp: Optional[str] = None
    ) -> None:
        """
        Set baseline cluster state.
        
        Args:
            clusters_df: DataFrame with columns: cluster_id, theme, reviewId, severity, 
                        actionability, score, content
            timestamp: Timestamp for baseline
        """
        timestamp = timestamp or datetime.now().isoformat()
        
        try:
            snapshots = self._create_cluster_snapshots(clusters_df, timestamp)
            self.baseline_clusters = {s.cluster_id: s for s in snapshots}
            self.baseline_timestamp = timestamp
            
            logger.info(f"Baseline set: {len(self.baseline_clusters)} clusters at {timestamp}")
            
        except Exception as e:
            logger.error(f"Error setting baseline: {e}")
            raise
    
    def detect_concept_drift(
        self,
        current_clusters_df: pd.DataFrame,
        current_period: str,
        timestamp: Optional[str] = None
    ) -> ConceptDriftReport:
        """
        Detect concept drift by comparing current clusters to baseline.
        
        Args:
            current_clusters_df: Current cluster data
            current_period: Label for current period
            timestamp: Timestamp for detection
            
        Returns:
            ConceptDriftReport with cluster evolution analysis
        """
        if not self.baseline_clusters:
            raise ValueError("Baseline not set. Call set_baseline() first.")
        
        timestamp = timestamp or datetime.now().isoformat()
        report_id = f"concept_drift_{timestamp.replace(':', '-').replace('.', '-')}"
        
        try:
            # Create current snapshots
            current_snapshots = self._create_cluster_snapshots(current_clusters_df, timestamp)
            current_clusters_map = {s.cluster_id: s for s in current_snapshots}
            
            # Track cluster evolution
            stable = []
            growing = []
            shrinking = []
            disappeared = []
            emerging = []
            
            # Analyze baseline clusters
            for baseline_id, baseline_snap in self.baseline_clusters.items():
                # Find matching cluster in current period
                current_snap = current_clusters_map.get(baseline_id)
                
                if current_snap is None:
                    # Check if cluster merged or truly disappeared
                    matched_cluster = self._find_matching_cluster(
                        baseline_snap, 
                        current_snapshots
                    )
                    
                    if matched_cluster:
                        current_snap = matched_cluster
                    
                evolution = self._analyze_cluster_evolution(
                    baseline_snap, 
                    current_snap
                )
                
                if evolution.status == 'stable':
                    stable.append(evolution)
                elif evolution.status == 'growing':
                    growing.append(evolution)
                elif evolution.status == 'shrinking':
                    shrinking.append(evolution)
                elif evolution.status == 'disappeared':
                    disappeared.append(evolution)
            
            # Find emerging clusters
            baseline_ids = set(self.baseline_clusters.keys())
            current_ids = set(current_clusters_map.keys())
            new_cluster_ids = current_ids - baseline_ids
            
            for cluster_id in new_cluster_ids:
                current_snap = current_clusters_map[cluster_id]
                
                # Check if it's truly new or just unmatched
                if not self._is_similar_to_baseline(current_snap, self.baseline_clusters.values()):
                    if current_snap.size >= self.EMERGING_CLUSTER_MIN_SIZE:
                        emerging_cluster = self._create_emerging_cluster(
                            current_snap, 
                            timestamp
                        )
                        emerging.append(emerging_cluster)
            
            # Determine drift severity
            concept_drift_detected = (
                len(disappeared) > 0 or
                len(emerging) > 0 or
                len(growing) >= 3 or
                len(shrinking) >= 3
            )
            
            drift_severity = self._calculate_drift_severity(
                disappeared, emerging, growing, shrinking
            )
            
            business_impact = self._assess_business_impact(
                disappeared, emerging, growing, shrinking
            )
            
            # Generate alerts and recommendations
            alerts = self._generate_concept_alerts(
                disappeared, emerging, growing, shrinking
            )
            
            recommendations = self._generate_concept_recommendations(
                disappeared, emerging, growing, shrinking
            )
            
            return ConceptDriftReport(
                report_id=report_id,
                timestamp=timestamp,
                baseline_period=self.baseline_timestamp,
                current_period=current_period,
                total_baseline_clusters=len(self.baseline_clusters),
                total_current_clusters=len(current_snapshots),
                stable_clusters=stable,
                growing_clusters=growing,
                shrinking_clusters=shrinking,
                disappeared_clusters=disappeared,
                emerging_clusters=emerging,
                concept_drift_detected=concept_drift_detected,
                drift_severity=drift_severity,
                business_impact=business_impact,
                alerts=alerts,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Error detecting concept drift: {e}")
            raise
    
    def _create_cluster_snapshots(
        self,
        clusters_df: pd.DataFrame,
        timestamp: str
    ) -> List[ClusterSnapshot]:
        """Create snapshots of all clusters in the dataset"""
        snapshots = []
        
        # Group by cluster
        for cluster_id, group in clusters_df.groupby('cluster_id'):
            snapshot = ClusterSnapshot(
                timestamp=timestamp,
                cluster_id=str(cluster_id),
                cluster_theme=group['theme'].iloc[0] if 'theme' in group.columns else f"cluster_{cluster_id}",
                size=len(group),
                avg_severity=float(group['severity'].mean()) if 'severity' in group.columns else 0.5,
                avg_actionability=float(group['actionability'].mean()) if 'actionability' in group.columns else 0.5,
                avg_sentiment=float(group['score'].mean()) if 'score' in group.columns else 3.0,
                top_keywords=self._extract_top_keywords(group['content'].tolist() if 'content' in group.columns else []),
                representative_reviews=group['content'].head(3).tolist() if 'content' in group.columns else []
            )
            snapshots.append(snapshot)
        
        return snapshots
    
    def _extract_top_keywords(self, texts: List[str], top_n: int = 10) -> List[str]:
        """Extract top keywords from cluster reviews"""
        # Simple frequency-based extraction
        word_freq = Counter()
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 
                    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'this',
                    'that', 'it', 'be', 'have', 'has', 'had', 'do', 'does', 'did'}
        
        for text in texts:
            if isinstance(text, str):
                words = text.lower().split()
                filtered_words = [w for w in words if w not in stopwords and len(w) > 3]
                word_freq.update(filtered_words)
        
        return [word for word, count in word_freq.most_common(top_n)]
    
    def _find_matching_cluster(
        self,
        baseline_snap: ClusterSnapshot,
        current_snapshots: List[ClusterSnapshot]
    ) -> Optional[ClusterSnapshot]:
        """Find matching cluster in current period using theme similarity"""
        best_match = None
        best_similarity = 0.0
        
        for current_snap in current_snapshots:
            similarity = self._calculate_theme_similarity(
                baseline_snap.top_keywords,
                current_snap.top_keywords
            )
            
            if similarity > best_similarity and similarity >= self.THEME_SIMILARITY_THRESHOLD:
                best_similarity = similarity
                best_match = current_snap
        
        return best_match
    
    def _calculate_theme_similarity(
        self,
        keywords1: List[str],
        keywords2: List[str]
    ) -> float:
        """Calculate similarity between two keyword lists using Jaccard similarity"""
        set1 = set(keywords1)
        set2 = set(keywords2)
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _analyze_cluster_evolution(
        self,
        baseline_snap: ClusterSnapshot,
        current_snap: Optional[ClusterSnapshot]
    ) -> ClusterEvolution:
        """Analyze how a cluster has evolved"""
        if current_snap is None:
            return ClusterEvolution(
                cluster_id=baseline_snap.cluster_id,
                baseline_snapshot=baseline_snap,
                current_snapshot=None,
                status='disappeared',
                size_change_pct=-100.0,
                severity_change=0.0,
                actionability_change=0.0,
                sentiment_change=0.0,
                theme_similarity=0.0,
                drift_detected=True
            )
        
        # Calculate changes
        size_change_pct = ((current_snap.size - baseline_snap.size) / baseline_snap.size) * 100
        severity_change = current_snap.avg_severity - baseline_snap.avg_severity
        actionability_change = current_snap.avg_actionability - baseline_snap.avg_actionability
        sentiment_change = current_snap.avg_sentiment - baseline_snap.avg_sentiment
        theme_similarity = self._calculate_theme_similarity(
            baseline_snap.top_keywords,
            current_snap.top_keywords
        )
        
        # Determine status
        if abs(size_change_pct) < self.SIZE_CHANGE_THRESHOLD * 100:
            status = 'stable'
        elif size_change_pct > 0:
            status = 'growing'
        else:
            status = 'shrinking'
        
        # Detect drift
        drift_detected = (
            abs(size_change_pct) > self.SIZE_CHANGE_THRESHOLD * 100 or
            abs(severity_change) > self.SEVERITY_CHANGE_THRESHOLD or
            theme_similarity < self.THEME_SIMILARITY_THRESHOLD
        )
        
        return ClusterEvolution(
            cluster_id=baseline_snap.cluster_id,
            baseline_snapshot=baseline_snap,
            current_snapshot=current_snap,
            status=status,
            size_change_pct=size_change_pct,
            severity_change=severity_change,
            actionability_change=actionability_change,
            sentiment_change=sentiment_change,
            theme_similarity=theme_similarity,
            drift_detected=drift_detected
        )
    
    def _is_similar_to_baseline(
        self,
        current_snap: ClusterSnapshot,
        baseline_snapshots: Any
    ) -> bool:
        """Check if current cluster is similar to any baseline cluster"""
        for baseline_snap in baseline_snapshots:
            similarity = self._calculate_theme_similarity(
                baseline_snap.top_keywords,
                current_snap.top_keywords
            )
            if similarity >= self.THEME_SIMILARITY_THRESHOLD:
                return True
        return False
    
    def _create_emerging_cluster(
        self,
        snapshot: ClusterSnapshot,
        timestamp: str
    ) -> EmergingCluster:
        """Create emerging cluster object with risk assessment"""
        # Calculate urgency based on size, severity, and actionability
        urgency_score = (
            (snapshot.size / self.CRITICAL_CLUSTER_SIZE) * 0.4 +
            snapshot.avg_severity * 0.3 +
            snapshot.avg_actionability * 0.3
        )
        
        # Assess potential risk
        if urgency_score > 0.8:
            potential_risk = 'critical'
        elif urgency_score > 0.6:
            potential_risk = 'high'
        elif urgency_score > 0.4:
            potential_risk = 'medium'
        else:
            potential_risk = 'low'
        
        return EmergingCluster(
            cluster_id=snapshot.cluster_id,
            first_seen=timestamp,
            snapshot=snapshot,
            growth_rate=0.0,  # Would need historical data
            urgency_score=urgency_score,
            potential_risk=potential_risk
        )
    
    def _calculate_drift_severity(
        self,
        disappeared: List[ClusterEvolution],
        emerging: List[EmergingCluster],
        growing: List[ClusterEvolution],
        shrinking: List[ClusterEvolution]
    ) -> str:
        """Calculate overall drift severity"""
        score = 0
        
        # Critical factors
        score += len(disappeared) * 3
        score += len([e for e in emerging if e.potential_risk in ['high', 'critical']]) * 3
        
        # Important factors
        score += len([g for g in growing if abs(g.size_change_pct) > 50]) * 2
        score += len([s for s in shrinking if abs(s.size_change_pct) > 50]) * 2
        
        # Minor factors
        score += len(growing)
        score += len(shrinking)
        
        if score >= 10:
            return 'critical'
        elif score >= 6:
            return 'high'
        elif score >= 3:
            return 'medium'
        elif score > 0:
            return 'low'
        else:
            return 'none'
    
    def _assess_business_impact(
        self,
        disappeared: List[ClusterEvolution],
        emerging: List[EmergingCluster],
        growing: List[ClusterEvolution],
        shrinking: List[ClusterEvolution]
    ) -> str:
        """Assess business impact of concept drift"""
        impacts = []
        
        if disappeared:
            impacts.append(f"{len(disappeared)} complaint categories resolved")
        
        critical_emerging = [e for e in emerging if e.potential_risk in ['high', 'critical']]
        if critical_emerging:
            impacts.append(f"{len(critical_emerging)} new critical issues detected")
        
        severe_growth = [g for g in growing if g.severity_change > 0.2]
        if severe_growth:
            impacts.append(f"{len(severe_growth)} issues becoming more severe")
        
        if not impacts:
            return "Stable - no significant business impact"
        
        return " | ".join(impacts)
    
    def _generate_concept_alerts(
        self,
        disappeared: List[ClusterEvolution],
        emerging: List[EmergingCluster],
        growing: List[ClusterEvolution],
        shrinking: List[ClusterEvolution]
    ) -> List[str]:
        """Generate alerts for concept drift"""
        alerts = []
        
        # Critical emerging issues
        critical_emerging = [e for e in emerging if e.potential_risk == 'critical']
        for cluster in critical_emerging:
            alerts.append(
                f"🚨 CRITICAL: New complaint category '{cluster.snapshot.cluster_theme}' "
                f"detected with {cluster.snapshot.size} reviews (urgency: {cluster.urgency_score:.2f})"
            )
        
        # Large growing clusters
        for cluster in growing:
            if cluster.size_change_pct > 100:
                alerts.append(
                    f"⚠️ WARNING: Complaint '{cluster.baseline_snapshot.cluster_theme}' "
                    f"grew by {cluster.size_change_pct:.0f}% "
                    f"(severity: {cluster.current_snapshot.avg_severity:.2f})"
                )
        
        # Disappeared high-severity clusters
        for cluster in disappeared:
            if cluster.baseline_snapshot.avg_severity > 0.7:
                alerts.append(
                    f"✅ RESOLVED: High-severity issue '{cluster.baseline_snapshot.cluster_theme}' "
                    f"no longer detected"
                )
        
        return alerts
    
    def _generate_concept_recommendations(
        self,
        disappeared: List[ClusterEvolution],
        emerging: List[EmergingCluster],
        growing: List[ClusterEvolution],
        shrinking: List[ClusterEvolution]
    ) -> List[str]:
        """Generate recommendations based on concept drift"""
        recommendations = []
        
        if emerging:
            recommendations.append(
                f"🔍 Investigate {len(emerging)} emerging complaint categories. "
                f"Top themes: {', '.join([e.snapshot.cluster_theme for e in emerging[:3]])}"
            )
        
        if growing:
            top_growing = sorted(growing, key=lambda x: x.size_change_pct, reverse=True)[:3]
            recommendations.append(
                f"📈 Monitor {len(growing)} growing complaint categories. "
                f"Fastest growing: {top_growing[0].baseline_snapshot.cluster_theme} "
                f"(+{top_growing[0].size_change_pct:.0f}%)"
            )
        
        if disappeared:
            recommendations.append(
                f"✅ {len(disappeared)} previous issues resolved. "
                "Validate product improvements worked."
            )
        
        severity_increases = [g for g in growing if g.severity_change > 0.2]
        if severity_increases:
            recommendations.append(
                f"🚨 {len(severity_increases)} issues increasing in severity. "
                "Prioritize for immediate action."
            )
        
        if not recommendations:
            recommendations.append("✅ No significant concept drift. Clusters are stable.")
        
        return recommendations
    
    def save_report(self, report: ConceptDriftReport, output_path: str) -> None:
        """Save concept drift report to JSON"""
        try:
            report_dict = {
                'report_id': report.report_id,
                'timestamp': report.timestamp,
                'baseline_period': report.baseline_period,
                'current_period': report.current_period,
                'total_baseline_clusters': report.total_baseline_clusters,
                'total_current_clusters': report.total_current_clusters,
                'concept_drift_detected': report.concept_drift_detected,
                'drift_severity': report.drift_severity,
                'business_impact': report.business_impact,
                'stable_clusters_count': len(report.stable_clusters),
                'growing_clusters_count': len(report.growing_clusters),
                'shrinking_clusters_count': len(report.shrinking_clusters),
                'disappeared_clusters_count': len(report.disappeared_clusters),
                'emerging_clusters_count': len(report.emerging_clusters),
                'alerts': report.alerts,
                'recommendations': report.recommendations
            }
            
            with open(output_path, 'w') as f:
                json.dump(report_dict, f, indent=2)
            
            logger.info(f"Concept drift report saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error saving report: {e}")
            raise
    
    def generate_markdown_report(
        self,
        report: ConceptDriftReport,
        output_path: str
    ) -> None:
        """Generate human-readable Markdown report"""
        try:
            lines = []
            lines.append("# Concept Drift Detection Report")
            lines.append(f"\n**Report ID:** {report.report_id}")
            lines.append(f"**Generated:** {report.timestamp}")
            lines.append(f"**Baseline Period:** {report.baseline_period}")
            lines.append(f"**Current Period:** {report.current_period}")
            
            lines.append(f"\n## Overall Status")
            severity_emoji = {'none': '✅', 'low': '⚡', 'medium': '⚠️', 'high': '🚨', 'critical': '🔥'}
            lines.append(f"\n{severity_emoji.get(report.drift_severity, '❓')} **Drift Severity: {report.drift_severity.upper()}**")
            lines.append(f"\n**Business Impact:** {report.business_impact}")
            
            lines.append(f"\n## Cluster Evolution Summary")
            lines.append(f"\n- Baseline clusters: {report.total_baseline_clusters}")
            lines.append(f"- Current clusters: {report.total_current_clusters}")
            lines.append(f"- Stable: {len(report.stable_clusters)}")
            lines.append(f"- Growing: {len(report.growing_clusters)}")
            lines.append(f"- Shrinking: {len(report.shrinking_clusters)}")
            lines.append(f"- Disappeared: {len(report.disappeared_clusters)}")
            lines.append(f"- Emerging: {len(report.emerging_clusters)}")
            
            if report.emerging_clusters:
                lines.append(f"\n## 🆕 Emerging Complaint Categories")
                for cluster in report.emerging_clusters:
                    risk_emoji = {'low': '⚡', 'medium': '⚠️', 'high': '🚨', 'critical': '🔥'}
                    lines.append(f"\n### {risk_emoji.get(cluster.potential_risk, '❓')} {cluster.snapshot.cluster_theme}")
                    lines.append(f"- **Size:** {cluster.snapshot.size} reviews")
                    lines.append(f"- **Risk Level:** {cluster.potential_risk}")
                    lines.append(f"- **Urgency Score:** {cluster.urgency_score:.2f}")
                    lines.append(f"- **Avg Severity:** {cluster.snapshot.avg_severity:.2f}")
                    lines.append(f"- **Keywords:** {', '.join(cluster.snapshot.top_keywords[:5])}")
            
            if report.growing_clusters:
                lines.append(f"\n## 📈 Growing Complaint Categories")
                for cluster in sorted(report.growing_clusters, key=lambda x: x.size_change_pct, reverse=True)[:5]:
                    lines.append(f"\n### {cluster.baseline_snapshot.cluster_theme}")
                    lines.append(f"- **Growth:** {cluster.size_change_pct:+.0f}%")
                    lines.append(f"- **Size:** {cluster.baseline_snapshot.size} → {cluster.current_snapshot.size}")
                    lines.append(f"- **Severity change:** {cluster.severity_change:+.2f}")
            
            if report.disappeared_clusters:
                lines.append(f"\n## ✅ Resolved Issues")
                for cluster in report.disappeared_clusters[:5]:
                    lines.append(f"\n- **{cluster.baseline_snapshot.cluster_theme}** ({cluster.baseline_snapshot.size} reviews)")
            
            if report.alerts:
                lines.append(f"\n## Alerts")
                for alert in report.alerts:
                    lines.append(f"\n- {alert}")
            
            if report.recommendations:
                lines.append(f"\n## Recommendations")
                for rec in report.recommendations:
                    lines.append(f"\n- {rec}")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            logger.info(f"Markdown report saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error generating markdown report: {e}")
            raise
