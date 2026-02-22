"""
Data Drift Detection Module

Implements statistical monitoring for embedding distribution, vocabulary, and sentiment drift.
Uses Population Stability Index (PSI) and Kolmogorov-Smirnov test to detect data drift over time.

Author: V3 System
Created: 2026-02-22
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import Counter
import logging
import json
from scipy import stats
import warnings

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class DriftMetrics:
    """Data drift metrics for a time period"""
    timestamp: str
    metric_name: str
    psi_score: float
    ks_statistic: float
    ks_pvalue: float
    drift_detected: bool
    severity: str  # 'none', 'low', 'medium', 'high', 'critical'
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VocabularyDrift:
    """Vocabulary shift metrics"""
    timestamp: str
    new_words_count: int
    disappeared_words_count: int
    new_words_ratio: float
    disappeared_words_ratio: float
    top_new_words: List[str]
    top_disappeared_words: List[str]
    jaccard_similarity: float
    drift_detected: bool


@dataclass
class SentimentDrift:
    """Sentiment distribution shift metrics"""
    timestamp: str
    mean_shift: float
    std_shift: float
    distribution_shift: float
    positive_ratio_shift: float
    negative_ratio_shift: float
    neutral_ratio_shift: float
    drift_detected: bool


@dataclass
class DriftReport:
    """Comprehensive drift detection report"""
    report_id: str
    timestamp: str
    baseline_period: str
    current_period: str
    embedding_drift: Optional[DriftMetrics]
    vocabulary_drift: Optional[VocabularyDrift]
    sentiment_drift: Optional[SentimentDrift]
    overall_drift_detected: bool
    overall_severity: str
    recommendations: List[str]
    alerts: List[str]


class DataDriftDetector:
    """
    Detects data drift using statistical methods.
    
    Features:
    - Embedding distribution monitoring (PSI, KS test)
    - Vocabulary shift tracking
    - Sentiment distribution monitoring
    - Configurable thresholds and time windows
    """
    
    # PSI thresholds (industry standard)
    PSI_THRESHOLDS = {
        'low': 0.1,      # <0.1: no significant change
        'medium': 0.25,  # 0.1-0.25: slight change
        'high': 0.25     # >0.25: significant change
    }
    
    # KS test threshold
    KS_PVALUE_THRESHOLD = 0.05  # p-value < 0.05 indicates significant difference
    
    # Vocabulary drift thresholds
    VOCAB_NEW_THRESHOLD = 0.15  # 15% new words is significant
    VOCAB_DISAPPEARED_THRESHOLD = 0.15  # 15% disappeared words is significant
    
    # Sentiment drift thresholds
    SENTIMENT_MEAN_THRESHOLD = 0.3  # 0.3 point shift on 1-5 scale
    SENTIMENT_DISTRIBUTION_THRESHOLD = 0.15  # 15% shift in distribution
    
    def __init__(self, baseline_window_days: int = 30):
        """
        Initialize drift detector.
        
        Args:
            baseline_window_days: Days to use for baseline calculation
        """
        self.baseline_window_days = baseline_window_days
        self.baseline_embeddings = None
        self.baseline_vocabulary = None
        self.baseline_sentiment = None
        self.baseline_timestamp = None
        logger.info(f"Initialized DataDriftDetector with {baseline_window_days}-day baseline window")
    
    def set_baseline(
        self,
        embeddings: np.ndarray,
        texts: List[str],
        scores: List[float],
        timestamp: Optional[str] = None
    ) -> None:
        """
        Set baseline distributions for drift detection.
        
        Args:
            embeddings: Baseline embedding vectors (n_samples, embedding_dim)
            texts: Baseline text reviews
            scores: Baseline sentiment scores (1-5)
            timestamp: Timestamp for baseline (default: now)
        """
        try:
            self.baseline_embeddings = embeddings
            self.baseline_vocabulary = self._extract_vocabulary(texts)
            self.baseline_sentiment = np.array(scores)
            self.baseline_timestamp = timestamp or datetime.now().isoformat()
            
            logger.info(f"Baseline set: {len(embeddings)} samples, "
                       f"{len(self.baseline_vocabulary)} unique words, "
                       f"mean sentiment: {np.mean(scores):.2f}")
        except Exception as e:
            logger.error(f"Error setting baseline: {e}")
            raise
    
    def detect_embedding_drift(
        self,
        current_embeddings: np.ndarray,
        timestamp: Optional[str] = None
    ) -> DriftMetrics:
        """
        Detect drift in embedding distribution using PSI and KS test.
        
        Args:
            current_embeddings: Current embedding vectors
            timestamp: Timestamp for current period
            
        Returns:
            DriftMetrics with PSI and KS statistics
        """
        if self.baseline_embeddings is None:
            raise ValueError("Baseline not set. Call set_baseline() first.")
        
        timestamp = timestamp or datetime.now().isoformat()
        
        try:
            # Flatten embeddings to 1D for distribution comparison
            baseline_flat = self.baseline_embeddings.flatten()
            current_flat = current_embeddings.flatten()
            
            # Calculate PSI
            psi_score = self._calculate_psi(baseline_flat, current_flat)
            
            # Calculate KS test
            ks_stat, ks_pvalue = stats.ks_2samp(baseline_flat, current_flat)
            
            # Determine drift severity
            severity, drift_detected = self._determine_drift_severity(psi_score, ks_pvalue)
            
            # Additional details
            details = {
                'baseline_mean': float(np.mean(baseline_flat)),
                'current_mean': float(np.mean(current_flat)),
                'baseline_std': float(np.std(baseline_flat)),
                'current_std': float(np.std(current_flat)),
                'mean_shift': float(np.abs(np.mean(current_flat) - np.mean(baseline_flat))),
                'std_shift': float(np.abs(np.std(current_flat) - np.std(baseline_flat)))
            }
            
            return DriftMetrics(
                timestamp=timestamp,
                metric_name='embedding_distribution',
                psi_score=psi_score,
                ks_statistic=ks_stat,
                ks_pvalue=ks_pvalue,
                drift_detected=drift_detected,
                severity=severity,
                details=details
            )
            
        except Exception as e:
            logger.error(f"Error detecting embedding drift: {e}")
            raise
    
    def detect_vocabulary_drift(
        self,
        current_texts: List[str],
        timestamp: Optional[str] = None,
        top_n: int = 20
    ) -> VocabularyDrift:
        """
        Detect vocabulary shift between baseline and current period.
        
        Args:
            current_texts: Current text reviews
            timestamp: Timestamp for current period
            top_n: Number of top new/disappeared words to report
            
        Returns:
            VocabularyDrift with vocabulary shift metrics
        """
        if self.baseline_vocabulary is None:
            raise ValueError("Baseline not set. Call set_baseline() first.")
        
        timestamp = timestamp or datetime.now().isoformat()
        
        try:
            current_vocab = self._extract_vocabulary(current_texts)
            
            # Find new and disappeared words
            new_words = current_vocab - self.baseline_vocabulary
            disappeared_words = self.baseline_vocabulary - current_vocab
            
            # Calculate ratios
            new_ratio = len(new_words) / len(self.baseline_vocabulary) if self.baseline_vocabulary else 0
            disappeared_ratio = len(disappeared_words) / len(self.baseline_vocabulary) if self.baseline_vocabulary else 0
            
            # Jaccard similarity
            intersection = len(self.baseline_vocabulary & current_vocab)
            union = len(self.baseline_vocabulary | current_vocab)
            jaccard = intersection / union if union > 0 else 0
            
            # Get top new/disappeared words by frequency
            current_word_freq = self._count_words(current_texts)
            baseline_word_freq = self._count_words([])  # Would need baseline texts, using empty for now
            
            top_new = sorted(new_words, key=lambda w: current_word_freq.get(w, 0), reverse=True)[:top_n]
            top_disappeared = list(disappeared_words)[:top_n]
            
            # Detect drift
            drift_detected = (new_ratio > self.VOCAB_NEW_THRESHOLD or 
                            disappeared_ratio > self.VOCAB_DISAPPEARED_THRESHOLD or
                            jaccard < 0.7)
            
            return VocabularyDrift(
                timestamp=timestamp,
                new_words_count=len(new_words),
                disappeared_words_count=len(disappeared_words),
                new_words_ratio=new_ratio,
                disappeared_words_ratio=disappeared_ratio,
                top_new_words=top_new,
                top_disappeared_words=top_disappeared,
                jaccard_similarity=jaccard,
                drift_detected=drift_detected
            )
            
        except Exception as e:
            logger.error(f"Error detecting vocabulary drift: {e}")
            raise
    
    def detect_sentiment_drift(
        self,
        current_scores: List[float],
        timestamp: Optional[str] = None
    ) -> SentimentDrift:
        """
        Detect sentiment distribution shift.
        
        Args:
            current_scores: Current sentiment scores (1-5)
            timestamp: Timestamp for current period
            
        Returns:
            SentimentDrift with sentiment shift metrics
        """
        if self.baseline_sentiment is None:
            raise ValueError("Baseline not set. Call set_baseline() first.")
        
        timestamp = timestamp or datetime.now().isoformat()
        
        try:
            current_sentiment = np.array(current_scores)
            
            # Calculate shifts
            mean_shift = np.mean(current_sentiment) - np.mean(self.baseline_sentiment)
            std_shift = np.std(current_sentiment) - np.std(self.baseline_sentiment)
            
            # Distribution shift (KS test on scores)
            ks_stat, ks_pvalue = stats.ks_2samp(self.baseline_sentiment, current_sentiment)
            
            # Calculate sentiment category ratios
            baseline_pos = np.sum(self.baseline_sentiment >= 4) / len(self.baseline_sentiment)
            baseline_neg = np.sum(self.baseline_sentiment <= 2) / len(self.baseline_sentiment)
            baseline_neu = 1 - baseline_pos - baseline_neg
            
            current_pos = np.sum(current_sentiment >= 4) / len(current_sentiment)
            current_neg = np.sum(current_sentiment <= 2) / len(current_sentiment)
            current_neu = 1 - current_pos - current_neg
            
            pos_shift = current_pos - baseline_pos
            neg_shift = current_neg - baseline_neg
            neu_shift = current_neu - baseline_neu
            
            # Detect drift
            drift_detected = (
                np.abs(mean_shift) > self.SENTIMENT_MEAN_THRESHOLD or
                np.abs(pos_shift) > self.SENTIMENT_DISTRIBUTION_THRESHOLD or
                np.abs(neg_shift) > self.SENTIMENT_DISTRIBUTION_THRESHOLD or
                ks_pvalue < self.KS_PVALUE_THRESHOLD
            )
            
            return SentimentDrift(
                timestamp=timestamp,
                mean_shift=float(mean_shift),
                std_shift=float(std_shift),
                distribution_shift=float(ks_stat),
                positive_ratio_shift=float(pos_shift),
                negative_ratio_shift=float(neg_shift),
                neutral_ratio_shift=float(neu_shift),
                drift_detected=drift_detected
            )
            
        except Exception as e:
            logger.error(f"Error detecting sentiment drift: {e}")
            raise
    
    def generate_drift_report(
        self,
        current_embeddings: np.ndarray,
        current_texts: List[str],
        current_scores: List[float],
        current_period: str,
        timestamp: Optional[str] = None
    ) -> DriftReport:
        """
        Generate comprehensive drift report for all metrics.
        
        Args:
            current_embeddings: Current embedding vectors
            current_texts: Current text reviews
            current_scores: Current sentiment scores
            current_period: Label for current period (e.g., "2026-02-22 to 2026-03-22")
            timestamp: Timestamp for report
            
        Returns:
            DriftReport with all drift metrics and recommendations
        """
        timestamp = timestamp or datetime.now().isoformat()
        report_id = f"drift_report_{timestamp.replace(':', '-').replace('.', '-')}"
        
        try:
            # Detect all types of drift
            embedding_drift = self.detect_embedding_drift(current_embeddings, timestamp)
            vocabulary_drift = self.detect_vocabulary_drift(current_texts, timestamp)
            sentiment_drift = self.detect_sentiment_drift(current_scores, timestamp)
            
            # Determine overall drift
            drift_flags = [
                embedding_drift.drift_detected,
                vocabulary_drift.drift_detected,
                sentiment_drift.drift_detected
            ]
            overall_drift_detected = any(drift_flags)
            
            # Determine overall severity
            severities = [embedding_drift.severity]
            severity_scores = {'none': 0, 'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
            overall_severity = max(severities, key=lambda s: severity_scores.get(s, 0))
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                embedding_drift, vocabulary_drift, sentiment_drift
            )
            
            # Generate alerts
            alerts = self._generate_alerts(
                embedding_drift, vocabulary_drift, sentiment_drift
            )
            
            return DriftReport(
                report_id=report_id,
                timestamp=timestamp,
                baseline_period=self.baseline_timestamp,
                current_period=current_period,
                embedding_drift=embedding_drift,
                vocabulary_drift=vocabulary_drift,
                sentiment_drift=sentiment_drift,
                overall_drift_detected=overall_drift_detected,
                overall_severity=overall_severity,
                recommendations=recommendations,
                alerts=alerts
            )
            
        except Exception as e:
            logger.error(f"Error generating drift report: {e}")
            raise
    
    def _calculate_psi(
        self,
        baseline: np.ndarray,
        current: np.ndarray,
        bins: int = 10
    ) -> float:
        """
        Calculate Population Stability Index (PSI).
        
        PSI measures distribution shift between two datasets.
        PSI < 0.1: no significant change
        PSI 0.1-0.25: slight change
        PSI > 0.25: significant change
        
        Args:
            baseline: Baseline data
            current: Current data
            bins: Number of bins for histogram
            
        Returns:
            PSI score
        """
        try:
            # Create bins based on baseline
            min_val = min(baseline.min(), current.min())
            max_val = max(baseline.max(), current.max())
            bin_edges = np.linspace(min_val, max_val, bins + 1)
            
            # Calculate distributions
            baseline_hist, _ = np.histogram(baseline, bins=bin_edges)
            current_hist, _ = np.histogram(current, bins=bin_edges)
            
            # Convert to percentages (avoid division by zero)
            baseline_pct = (baseline_hist + 1e-6) / (baseline.shape[0] + bins * 1e-6)
            current_pct = (current_hist + 1e-6) / (current.shape[0] + bins * 1e-6)
            
            # Calculate PSI
            psi = np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct))
            
            return float(psi)
            
        except Exception as e:
            logger.error(f"Error calculating PSI: {e}")
            return 0.0
    
    def _determine_drift_severity(
        self,
        psi_score: float,
        ks_pvalue: float
    ) -> Tuple[str, bool]:
        """
        Determine drift severity based on PSI and KS test.
        
        Args:
            psi_score: PSI score
            ks_pvalue: KS test p-value
            
        Returns:
            (severity_level, drift_detected)
        """
        # KS test indicates significant difference if p-value < threshold
        ks_drift = ks_pvalue < self.KS_PVALUE_THRESHOLD
        
        if psi_score < self.PSI_THRESHOLDS['low']:
            severity = 'none' if not ks_drift else 'low'
            drift_detected = ks_drift
        elif psi_score < self.PSI_THRESHOLDS['medium']:
            severity = 'low' if not ks_drift else 'medium'
            drift_detected = True
        elif psi_score < self.PSI_THRESHOLDS['high']:
            severity = 'medium' if not ks_drift else 'high'
            drift_detected = True
        else:
            severity = 'critical'
            drift_detected = True
        
        return severity, drift_detected
    
    def _extract_vocabulary(self, texts: List[str]) -> set:
        """Extract unique words from texts (simple tokenization)"""
        vocab = set()
        for text in texts:
            if isinstance(text, str):
                words = text.lower().split()
                vocab.update(words)
        return vocab
    
    def _count_words(self, texts: List[str]) -> Counter:
        """Count word frequencies"""
        counter = Counter()
        for text in texts:
            if isinstance(text, str):
                words = text.lower().split()
                counter.update(words)
        return counter
    
    def _generate_recommendations(
        self,
        embedding_drift: DriftMetrics,
        vocabulary_drift: VocabularyDrift,
        sentiment_drift: SentimentDrift
    ) -> List[str]:
        """Generate actionable recommendations based on drift"""
        recommendations = []
        
        if embedding_drift.drift_detected:
            if embedding_drift.severity in ['high', 'critical']:
                recommendations.append(
                    "🚨 High embedding drift detected. Consider retraining models with recent data."
                )
            else:
                recommendations.append(
                    "⚠️ Moderate embedding drift. Monitor closely and prepare for model update."
                )
        
        if vocabulary_drift.drift_detected:
            if vocabulary_drift.new_words_ratio > self.VOCAB_NEW_THRESHOLD:
                recommendations.append(
                    f"📝 {len(vocabulary_drift.top_new_words)} new terms detected. "
                    f"Update feature extraction pipeline. Top terms: {', '.join(vocabulary_drift.top_new_words[:5])}"
                )
        
        if sentiment_drift.drift_detected:
            if sentiment_drift.mean_shift > 0.5:
                recommendations.append(
                    f"📈 Sentiment improved by {sentiment_drift.mean_shift:.2f} points. "
                    "Product quality may have improved."
                )
            elif sentiment_drift.mean_shift < -0.5:
                recommendations.append(
                    f"📉 Sentiment declined by {abs(sentiment_drift.mean_shift):.2f} points. "
                    "Investigate recent product changes."
                )
        
        if not recommendations:
            recommendations.append("✅ No significant drift detected. System is stable.")
        
        return recommendations
    
    def _generate_alerts(
        self,
        embedding_drift: DriftMetrics,
        vocabulary_drift: VocabularyDrift,
        sentiment_drift: SentimentDrift
    ) -> List[str]:
        """Generate alerts for critical drift conditions"""
        alerts = []
        
        if embedding_drift.severity == 'critical':
            alerts.append(
                f"CRITICAL: Embedding drift PSI={embedding_drift.psi_score:.3f} exceeds threshold. "
                "Model predictions may be unreliable."
            )
        
        if vocabulary_drift.new_words_ratio > 0.3:
            alerts.append(
                f"WARNING: {vocabulary_drift.new_words_ratio*100:.1f}% vocabulary change. "
                "Feature space has shifted significantly."
            )
        
        if abs(sentiment_drift.mean_shift) > 1.0:
            direction = "improved" if sentiment_drift.mean_shift > 0 else "degraded"
            alerts.append(
                f"ALERT: Sentiment {direction} by {abs(sentiment_drift.mean_shift):.2f} points. "
                "Significant user perception change detected."
            )
        
        return alerts
    
    def save_report(self, report: DriftReport, output_path: str) -> None:
        """Save drift report to JSON file"""
        try:
            report_dict = {
                'report_id': report.report_id,
                'timestamp': report.timestamp,
                'baseline_period': report.baseline_period,
                'current_period': report.current_period,
                'overall_drift_detected': bool(report.overall_drift_detected),
                'overall_severity': report.overall_severity,
                'embedding_drift': {
                    'psi_score': float(report.embedding_drift.psi_score),
                    'ks_statistic': float(report.embedding_drift.ks_statistic),
                    'ks_pvalue': float(report.embedding_drift.ks_pvalue),
                    'drift_detected': bool(report.embedding_drift.drift_detected),
                    'severity': report.embedding_drift.severity,
                    'details': report.embedding_drift.details
                } if report.embedding_drift else None,
                'vocabulary_drift': {
                    'new_words_count': int(report.vocabulary_drift.new_words_count),
                    'disappeared_words_count': int(report.vocabulary_drift.disappeared_words_count),
                    'new_words_ratio': float(report.vocabulary_drift.new_words_ratio),
                    'disappeared_words_ratio': float(report.vocabulary_drift.disappeared_words_ratio),
                    'top_new_words': report.vocabulary_drift.top_new_words,
                    'top_disappeared_words': report.vocabulary_drift.top_disappeared_words,
                    'jaccard_similarity': float(report.vocabulary_drift.jaccard_similarity),
                    'drift_detected': bool(report.vocabulary_drift.drift_detected)
                } if report.vocabulary_drift else None,
                'sentiment_drift': {
                    'mean_shift': float(report.sentiment_drift.mean_shift),
                    'std_shift': float(report.sentiment_drift.std_shift),
                    'distribution_shift': float(report.sentiment_drift.distribution_shift),
                    'positive_ratio_shift': float(report.sentiment_drift.positive_ratio_shift),
                    'negative_ratio_shift': float(report.sentiment_drift.negative_ratio_shift),
                    'neutral_ratio_shift': float(report.sentiment_drift.neutral_ratio_shift),
                    'drift_detected': bool(report.sentiment_drift.drift_detected)
                } if report.sentiment_drift else None,
                'recommendations': report.recommendations,
                'alerts': report.alerts
            }
            
            with open(output_path, 'w') as f:
                json.dump(report_dict, f, indent=2)
            
            logger.info(f"Drift report saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error saving drift report: {e}")
            raise
    
    def generate_markdown_report(self, report: DriftReport, output_path: str) -> None:
        """Generate human-readable Markdown drift report"""
        try:
            lines = []
            lines.append(f"# Data Drift Detection Report")
            lines.append(f"\n**Report ID:** {report.report_id}")
            lines.append(f"**Generated:** {report.timestamp}")
            lines.append(f"**Baseline Period:** {report.baseline_period}")
            lines.append(f"**Current Period:** {report.current_period}")
            lines.append(f"\n## Overall Status")
            
            if report.overall_drift_detected:
                severity_emoji = {'none': '✅', 'low': '⚡', 'medium': '⚠️', 'high': '🚨', 'critical': '🔥'}
                lines.append(f"\n{severity_emoji.get(report.overall_severity, '❓')} **Drift Detected: {report.overall_severity.upper()}**")
            else:
                lines.append(f"\n✅ **No Significant Drift Detected**")
            
            # Embedding drift
            if report.embedding_drift:
                lines.append(f"\n## Embedding Distribution Drift")
                lines.append(f"\n- **PSI Score:** {report.embedding_drift.psi_score:.4f}")
                lines.append(f"- **KS Statistic:** {report.embedding_drift.ks_statistic:.4f}")
                lines.append(f"- **KS P-value:** {report.embedding_drift.ks_pvalue:.4f}")
                lines.append(f"- **Severity:** {report.embedding_drift.severity}")
                lines.append(f"- **Drift Detected:** {'Yes ⚠️' if report.embedding_drift.drift_detected else 'No ✅'}")
                
                if report.embedding_drift.details:
                    lines.append(f"\n**Details:**")
                    lines.append(f"- Mean shift: {report.embedding_drift.details.get('mean_shift', 0):.4f}")
                    lines.append(f"- Std shift: {report.embedding_drift.details.get('std_shift', 0):.4f}")
            
            # Vocabulary drift
            if report.vocabulary_drift:
                lines.append(f"\n## Vocabulary Drift")
                lines.append(f"\n- **New Words:** {report.vocabulary_drift.new_words_count} ({report.vocabulary_drift.new_words_ratio*100:.1f}%)")
                lines.append(f"- **Disappeared Words:** {report.vocabulary_drift.disappeared_words_count} ({report.vocabulary_drift.disappeared_words_ratio*100:.1f}%)")
                lines.append(f"- **Jaccard Similarity:** {report.vocabulary_drift.jaccard_similarity:.3f}")
                lines.append(f"- **Drift Detected:** {'Yes ⚠️' if report.vocabulary_drift.drift_detected else 'No ✅'}")
                
                if report.vocabulary_drift.top_new_words:
                    lines.append(f"\n**Top New Words:** {', '.join(report.vocabulary_drift.top_new_words[:10])}")
            
            # Sentiment drift
            if report.sentiment_drift:
                lines.append(f"\n## Sentiment Drift")
                lines.append(f"\n- **Mean Shift:** {report.sentiment_drift.mean_shift:+.3f}")
                lines.append(f"- **Distribution Shift (KS):** {report.sentiment_drift.distribution_shift:.4f}")
                lines.append(f"- **Positive Ratio Shift:** {report.sentiment_drift.positive_ratio_shift:+.3f}")
                lines.append(f"- **Negative Ratio Shift:** {report.sentiment_drift.negative_ratio_shift:+.3f}")
                lines.append(f"- **Drift Detected:** {'Yes ⚠️' if report.sentiment_drift.drift_detected else 'No ✅'}")
            
            # Alerts
            if report.alerts:
                lines.append(f"\n## Alerts")
                for alert in report.alerts:
                    lines.append(f"\n- {alert}")
            
            # Recommendations
            if report.recommendations:
                lines.append(f"\n## Recommendations")
                for rec in report.recommendations:
                    lines.append(f"\n- {rec}")
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            logger.info(f"Markdown report saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error generating markdown report: {e}")
            raise
