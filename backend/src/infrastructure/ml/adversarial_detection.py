"""
Adversarial and Spam Detection Module

Detects fake reviews, sarcasm, coordinated review bursts, and abnormal patterns.
Uses lightweight heuristics and embedding similarity for CPU-efficient detection.

Author: V3 System
Created: 2026-02-22
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import logging
import re
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AdversarialFlags:
    """Flags for different types of adversarial content"""
    review_id: str
    is_fake_positive: bool
    is_sarcastic: bool
    is_coordinated: bool
    is_repetitive: bool
    is_spam: bool
    suspicion_score: float
    flags: List[str]
    details: Dict[str, any] = field(default_factory=dict)


@dataclass
class CoordinatedBurst:
    """Detected coordinated review burst"""
    burst_id: str
    timestamp_start: str
    timestamp_end: str
    review_count: int
    avg_similarity: float
    suspicion_score: float
    review_ids: List[str]
    common_patterns: List[str]
    potential_coordinated: bool


@dataclass
class AdversarialReport:
    """Comprehensive adversarial detection report"""
    report_id: str
    timestamp: str
    total_reviews: int
    fake_positive_count: int
    sarcasm_count: int
    coordinated_count: int
    repetitive_count: int
    spam_count: int
    coordinated_bursts: List[CoordinatedBurst]
    high_risk_reviews: List[AdversarialFlags]
    detection_summary: Dict[str, int]
    alerts: List[str]
    recommendations: List[str]


class AdversarialDetector:
    """
    Detects adversarial and spam content using lightweight heuristics.
    
    Features:
    - Fake positive review detection (high rating + negative language)
    - Sarcasm detection (sentiment-word mismatch)
    - Coordinated burst detection (similar reviews in short time)
    - Repetition pattern detection (copy-paste, template reviews)
    - Lightweight embedding similarity for duplicate detection
    """
    
    # Sarcasm indicators
    SARCASM_MARKERS = [
        'yeah right', 'sure', 'great job', 'well done', 'fantastic',
        'awesome', 'perfect', 'love it', 'best ever', 'amazing',
        'wonderful', 'brilliant', 'excellent'
    ]
    
    # Negative sentiment words (for fake positive detection)
    NEGATIVE_WORDS = [
        'crash', 'bug', 'broken', 'waste', 'terrible', 'awful', 'horrible',
        'useless', 'worst', 'fail', 'problem', 'issue', 'error', 'annoying',
        'disappointed', 'frustrat', 'angry', 'hate', 'regret', 'refund'
    ]
    
    # Spam indicators
    SPAM_PATTERNS = [
        r'\b(?:https?://|www\.)\S+',  # URLs
        r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',  # Emails
        r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone numbers
        r'\b(?:click here|buy now|limited offer|act now)\b',  # Spam phrases
        r'\b(?:promo code|discount code|coupon)\b'
    ]
    
    # Thresholds
    FAKE_POSITIVE_THRESHOLD = 0.6  # Suspicion score for fake positive
    SARCASM_THRESHOLD = 0.5
    SIMILARITY_THRESHOLD = 0.85  # For detecting coordinated reviews
    BURST_TIME_WINDOW_HOURS = 24
    BURST_MIN_REVIEWS = 5
    REPETITION_THRESHOLD = 0.9  # Very high similarity = copy-paste
    HIGH_RISK_THRESHOLD = 0.7
    
    def __init__(self):
        """Initialize adversarial detector"""
        self.review_history: List[Dict] = []
        logger.info("Initialized AdversarialDetector")
    
    def detect_fake_positive(
        self,
        review_text: str,
        score: float,
        review_id: str
    ) -> AdversarialFlags:
        """
        Detect fake positive reviews (high rating but negative content).
        
        Args:
            review_text: Review text
            score: Review score (1-5)
            review_id: Review identifier
            
        Returns:
            AdversarialFlags with detection results
        """
        flags = []
        details = {}
        
        # Check if high rating
        if score >= 4:
            text_lower = review_text.lower()
            
            # Count negative words
            negative_count = sum(1 for word in self.NEGATIVE_WORDS if word in text_lower)
            
            # Check for sarcasm markers with negative context
            sarcasm_with_negative = any(
                marker in text_lower and any(neg in text_lower for neg in self.NEGATIVE_WORDS)
                for marker in self.SARCASM_MARKERS
            )
            
            # Calculate suspicion score
            suspicion = 0.0
            
            if negative_count >= 3:
                suspicion += 0.4
                flags.append('high_negative_word_count')
                details['negative_word_count'] = negative_count
            
            if sarcasm_with_negative:
                suspicion += 0.3
                flags.append('sarcasm_with_negative_context')
            
            # Check for contradiction patterns (but, however, although with negative)
            contradiction_patterns = [
                r'\b(?:but|however|although|yet)\b.*?(?:' + '|'.join(self.NEGATIVE_WORDS[:10]) + r')\b'
            ]
            if any(re.search(pattern, text_lower) for pattern in contradiction_patterns):
                suspicion += 0.2
                flags.append('contradiction_pattern')
            
            is_fake = suspicion >= self.FAKE_POSITIVE_THRESHOLD
            
            return AdversarialFlags(
                review_id=review_id,
                is_fake_positive=is_fake,
                is_sarcastic=False,
                is_coordinated=False,
                is_repetitive=False,
                is_spam=False,
                suspicion_score=suspicion,
                flags=flags,
                details=details
            )
        
        return AdversarialFlags(
            review_id=review_id,
            is_fake_positive=False,
            is_sarcastic=False,
            is_coordinated=False,
            is_repetitive=False,
            is_spam=False,
            suspicion_score=0.0,
            flags=[],
            details={}
        )
    
    def detect_sarcasm(
        self,
        review_text: str,
        score: float,
        review_id: str
    ) -> AdversarialFlags:
        """
        Detect sarcasm (positive words with negative sentiment score).
        
        Args:
            review_text: Review text
            score: Review score (1-5)
            review_id: Review identifier
            
        Returns:
            AdversarialFlags with detection results
        """
        flags = []
        details = {}
        suspicion = 0.0
        
        text_lower = review_text.lower()
        
        # Low score with sarcasm markers
        if score <= 2:
            sarcasm_count = sum(1 for marker in self.SARCASM_MARKERS if marker in text_lower)
            
            if sarcasm_count > 0:
                suspicion = min(1.0, 0.3 + (sarcasm_count * 0.2))
                flags.append('sarcasm_markers_in_negative_review')
                details['sarcasm_marker_count'] = sarcasm_count
                
                # Check for exclamation marks (common in sarcasm)
                exclamation_count = text_lower.count('!')
                if exclamation_count >= 2:
                    suspicion += 0.1
                    flags.append('excessive_exclamations')
                    details['exclamation_count'] = exclamation_count
                
                # Check for ALL CAPS (sarcasm indicator)
                caps_ratio = sum(1 for c in review_text if c.isupper()) / len(review_text) if review_text else 0
                if caps_ratio > 0.3:
                    suspicion += 0.1
                    flags.append('excessive_caps')
                    details['caps_ratio'] = caps_ratio
        
        is_sarcastic = suspicion >= self.SARCASM_THRESHOLD
        
        return AdversarialFlags(
            review_id=review_id,
            is_fake_positive=False,
            is_sarcastic=is_sarcastic,
            is_coordinated=False,
            is_repetitive=False,
            is_spam=False,
            suspicion_score=suspicion,
            flags=flags,
            details=details
        )
    
    def detect_spam(
        self,
        review_text: str,
        review_id: str
    ) -> AdversarialFlags:
        """
        Detect spam reviews (URLs, emails, promotional content).
        
        Args:
            review_text: Review text
            review_id: Review identifier
            
        Returns:
            AdversarialFlags with detection results
        """
        flags = []
        details = {}
        suspicion = 0.0
        
        # Check spam patterns
        for i, pattern in enumerate(self.SPAM_PATTERNS):
            matches = re.findall(pattern, review_text, re.IGNORECASE)
            if matches:
                suspicion += 0.3
                flags.append(f'spam_pattern_{i}')
                details[f'spam_matches_{i}'] = len(matches)
        
        # Very short reviews (likely spam)
        if len(review_text.split()) < 5:
            suspicion += 0.2
            flags.append('very_short_review')
        
        # Excessive repetition of same word
        words = review_text.lower().split()
        if words:
            word_freq = Counter(words)
            most_common_freq = word_freq.most_common(1)[0][1] if word_freq else 0
            if most_common_freq > len(words) * 0.3:
                suspicion += 0.2
                flags.append('excessive_word_repetition')
                details['repeated_word_ratio'] = most_common_freq / len(words)
        
        is_spam = suspicion >= 0.5
        
        return AdversarialFlags(
            review_id=review_id,
            is_fake_positive=False,
            is_sarcastic=False,
            is_coordinated=False,
            is_repetitive=False,
            is_spam=is_spam,
            suspicion_score=suspicion,
            flags=flags,
            details=details
        )
    
    def detect_repetition(
        self,
        review_text: str,
        review_id: str,
        all_reviews: List[str]
    ) -> AdversarialFlags:
        """
        Detect repetitive/template reviews using text similarity.
        
        Args:
            review_text: Review text
            review_id: Review identifier
            all_reviews: All reviews for comparison
            
        Returns:
            AdversarialFlags with detection results
        """
        flags = []
        details = {}
        suspicion = 0.0
        
        # Calculate similarity with other reviews using simple word overlap
        high_similarity_count = 0
        max_similarity = 0.0
        
        for other_review in all_reviews[:100]:  # Limit to 100 for performance
            if other_review != review_text:
                similarity = self._calculate_text_similarity(review_text, other_review)
                max_similarity = max(max_similarity, similarity)
                
                if similarity >= self.REPETITION_THRESHOLD:
                    high_similarity_count += 1
        
        if high_similarity_count > 0:
            suspicion = min(1.0, 0.5 + (high_similarity_count * 0.1))
            flags.append('high_similarity_to_other_reviews')
            details['similar_review_count'] = high_similarity_count
            details['max_similarity'] = max_similarity
        
        is_repetitive = suspicion >= 0.6
        
        return AdversarialFlags(
            review_id=review_id,
            is_fake_positive=False,
            is_sarcastic=False,
            is_coordinated=False,
            is_repetitive=is_repetitive,
            is_spam=False,
            suspicion_score=suspicion,
            flags=flags,
            details=details
        )
    
    def detect_coordinated_bursts(
        self,
        reviews_df: pd.DataFrame
    ) -> List[CoordinatedBurst]:
        """
        Detect coordinated review bursts (similar reviews in short time).
        
        Args:
            reviews_df: DataFrame with columns: reviewId, content, at (timestamp), score
            
        Returns:
            List of detected coordinated bursts
        """
        bursts = []
        
        if 'at' not in reviews_df.columns:
            logger.warning("No timestamp column 'at' found, skipping burst detection")
            return bursts
        
        try:
            # Convert timestamps
            reviews_df = reviews_df.copy()
            reviews_df['timestamp'] = pd.to_datetime(reviews_df['at'], errors='coerce')
            reviews_df = reviews_df.dropna(subset=['timestamp'])
            reviews_df = reviews_df.sort_values('timestamp')
            
            # Sliding window approach
            window_hours = self.BURST_TIME_WINDOW_HOURS
            
            for i, row in reviews_df.iterrows():
                window_start = row['timestamp']
                window_end = window_start + timedelta(hours=window_hours)
                
                # Get reviews in window
                window_reviews = reviews_df[
                    (reviews_df['timestamp'] >= window_start) &
                    (reviews_df['timestamp'] < window_end)
                ]
                
                if len(window_reviews) >= self.BURST_MIN_REVIEWS:
                    # Calculate pairwise similarity
                    texts = window_reviews['content'].tolist()
                    similarities = []
                    
                    for j in range(len(texts)):
                        for k in range(j + 1, min(j + 10, len(texts))):  # Limit comparisons
                            sim = self._calculate_text_similarity(texts[j], texts[k])
                            similarities.append(sim)
                    
                    if similarities:
                        avg_similarity = np.mean(similarities)
                        
                        if avg_similarity >= self.SIMILARITY_THRESHOLD:
                            # Calculate suspicion score
                            suspicion = min(1.0, avg_similarity * (len(window_reviews) / self.BURST_MIN_REVIEWS) * 0.5)
                            
                            # Extract common patterns
                            common_patterns = self._extract_common_phrases(texts)
                            
                            burst = CoordinatedBurst(
                                burst_id=f"burst_{window_start.isoformat()}",
                                timestamp_start=window_start.isoformat(),
                                timestamp_end=window_end.isoformat(),
                                review_count=len(window_reviews),
                                avg_similarity=avg_similarity,
                                suspicion_score=suspicion,
                                review_ids=window_reviews['reviewId'].tolist(),
                                common_patterns=common_patterns,
                                potential_coordinated=suspicion >= 0.6
                            )
                            
                            bursts.append(burst)
                            
                            # Skip ahead to avoid overlapping bursts
                            break
            
            # Deduplicate bursts
            bursts = self._deduplicate_bursts(bursts)
            
            return bursts
            
        except Exception as e:
            logger.error(f"Error detecting coordinated bursts: {e}")
            return []
    
    def analyze_reviews(
        self,
        reviews_df: pd.DataFrame
    ) -> AdversarialReport:
        """
        Comprehensive adversarial analysis of all reviews.
        
        Args:
            reviews_df: DataFrame with columns: reviewId, content, score, at (optional)
            
        Returns:
            AdversarialReport with all detection results
        """
        timestamp = datetime.now().isoformat()
        report_id = f"adversarial_report_{timestamp.replace(':', '-').replace('.', '-')}"
        
        try:
            all_flags = []
            all_reviews = reviews_df['content'].tolist()
            
            # Analyze each review
            for idx, row in reviews_df.iterrows():
                review_id = str(row['reviewId'])
                content = str(row['content'])
                score = float(row['score'])
                
                # Run all detectors
                fake_flags = self.detect_fake_positive(content, score, review_id)
                sarcasm_flags = self.detect_sarcasm(content, score, review_id)
                spam_flags = self.detect_spam(content, review_id)
                repetition_flags = self.detect_repetition(content, review_id, all_reviews)
                
                # Combine flags
                combined_flags = AdversarialFlags(
                    review_id=review_id,
                    is_fake_positive=fake_flags.is_fake_positive,
                    is_sarcastic=sarcasm_flags.is_sarcastic,
                    is_coordinated=False,  # Detected separately
                    is_repetitive=repetition_flags.is_repetitive,
                    is_spam=spam_flags.is_spam,
                    suspicion_score=max(
                        fake_flags.suspicion_score,
                        sarcasm_flags.suspicion_score,
                        spam_flags.suspicion_score,
                        repetition_flags.suspicion_score
                    ),
                    flags=(fake_flags.flags + sarcasm_flags.flags + 
                          spam_flags.flags + repetition_flags.flags),
                    details={
                        **fake_flags.details,
                        **sarcasm_flags.details,
                        **spam_flags.details,
                        **repetition_flags.details
                    }
                )
                
                all_flags.append(combined_flags)
            
            # Detect coordinated bursts
            coordinated_bursts = self.detect_coordinated_bursts(reviews_df)
            
            # Mark coordinated reviews
            coordinated_review_ids = set()
            for burst in coordinated_bursts:
                coordinated_review_ids.update(burst.review_ids)
            
            for flags in all_flags:
                if flags.review_id in coordinated_review_ids:
                    flags.is_coordinated = True
            
            # Count detections
            fake_count = sum(1 for f in all_flags if f.is_fake_positive)
            sarcasm_count = sum(1 for f in all_flags if f.is_sarcastic)
            coordinated_count = len(coordinated_review_ids)
            repetitive_count = sum(1 for f in all_flags if f.is_repetitive)
            spam_count = sum(1 for f in all_flags if f.is_spam)
            
            # High risk reviews
            high_risk = [f for f in all_flags if f.suspicion_score >= self.HIGH_RISK_THRESHOLD]
            high_risk = sorted(high_risk, key=lambda x: x.suspicion_score, reverse=True)
            
            # Detection summary
            detection_summary = {
                'total_reviews': len(reviews_df),
                'fake_positive': fake_count,
                'sarcasm': sarcasm_count,
                'coordinated': coordinated_count,
                'repetitive': repetitive_count,
                'spam': spam_count,
                'high_risk': len(high_risk),
                'clean_reviews': len(all_flags) - len(high_risk)
            }
            
            # Generate alerts and recommendations
            alerts = self._generate_adversarial_alerts(
                fake_count, sarcasm_count, coordinated_bursts, repetitive_count, spam_count, len(reviews_df)
            )
            
            recommendations = self._generate_adversarial_recommendations(
                fake_count, sarcasm_count, coordinated_bursts, repetitive_count, spam_count
            )
            
            return AdversarialReport(
                report_id=report_id,
                timestamp=timestamp,
                total_reviews=len(reviews_df),
                fake_positive_count=fake_count,
                sarcasm_count=sarcasm_count,
                coordinated_count=coordinated_count,
                repetitive_count=repetitive_count,
                spam_count=spam_count,
                coordinated_bursts=coordinated_bursts,
                high_risk_reviews=high_risk[:20],  # Top 20
                detection_summary=detection_summary,
                alerts=alerts,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Error analyzing reviews: {e}")
            raise
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _extract_common_phrases(self, texts: List[str], top_n: int = 5) -> List[str]:
        """Extract common phrases from multiple texts"""
        # Simple n-gram approach
        bigrams = Counter()
        
        for text in texts:
            words = text.lower().split()
            for i in range(len(words) - 1):
                bigram = f"{words[i]} {words[i+1]}"
                bigrams[bigram] += 1
        
        # Filter common phrases (appear in multiple reviews)
        min_frequency = max(2, len(texts) // 3)
        common = [phrase for phrase, count in bigrams.items() if count >= min_frequency]
        
        return common[:top_n]
    
    def _deduplicate_bursts(self, bursts: List[CoordinatedBurst]) -> List[CoordinatedBurst]:
        """Remove overlapping bursts, keep highest suspicion"""
        if not bursts:
            return []
        
        # Sort by suspicion score
        sorted_bursts = sorted(bursts, key=lambda x: x.suspicion_score, reverse=True)
        
        unique_bursts = []
        used_reviews = set()
        
        for burst in sorted_bursts:
            # Check if reviews already covered
            overlap = len(set(burst.review_ids) & used_reviews)
            if overlap < len(burst.review_ids) * 0.5:  # Less than 50% overlap
                unique_bursts.append(burst)
                used_reviews.update(burst.review_ids)
        
        return unique_bursts
    
    def _generate_adversarial_alerts(
        self,
        fake_count: int,
        sarcasm_count: int,
        bursts: List[CoordinatedBurst],
        repetitive_count: int,
        spam_count: int,
        total_reviews: int
    ) -> List[str]:
        """Generate alerts for adversarial content"""
        alerts = []
        
        # Fake positive rate
        fake_rate = fake_count / total_reviews if total_reviews > 0 else 0
        if fake_rate > 0.1:
            alerts.append(
                f"🚨 HIGH: {fake_count} fake positive reviews detected ({fake_rate*100:.1f}%). "
                "High ratings hiding complaints."
            )
        
        # Coordinated bursts
        critical_bursts = [b for b in bursts if b.potential_coordinated]
        if critical_bursts:
            alerts.append(
                f"⚠️ COORDINATED: {len(critical_bursts)} suspicious review bursts detected. "
                f"Potential manipulation or bot activity."
            )
        
        # Spam rate
        spam_rate = spam_count / total_reviews if total_reviews > 0 else 0
        if spam_rate > 0.05:
            alerts.append(
                f"🚨 SPAM: {spam_count} spam reviews detected ({spam_rate*100:.1f}%). "
                "Contains promotional content or contact info."
            )
        
        # Repetitive reviews
        repetitive_rate = repetitive_count / total_reviews if total_reviews > 0 else 0
        if repetitive_rate > 0.15:
            alerts.append(
                f"⚠️ REPETITION: {repetitive_count} repetitive/template reviews ({repetitive_rate*100:.1f}%). "
                "Possible copy-paste or bot-generated content."
            )
        
        return alerts
    
    def _generate_adversarial_recommendations(
        self,
        fake_count: int,
        sarcasm_count: int,
        bursts: List[CoordinatedBurst],
        repetitive_count: int,
        spam_count: int
    ) -> List[str]:
        """Generate recommendations for handling adversarial content"""
        recommendations = []
        
        if fake_count > 0:
            recommendations.append(
                f"🔍 Review {fake_count} fake positive reviews manually. "
                "Apply sentiment correction or flag as misleading."
            )
        
        if sarcasm_count > 0:
            recommendations.append(
                f"📝 Adjust sentiment scoring for {sarcasm_count} sarcastic reviews. "
                "Consider inverting sentiment polarity."
            )
        
        if bursts:
            recommendations.append(
                f"🚨 Investigate {len(bursts)} coordinated review bursts. "
                "Check for bot activity or manipulation campaigns."
            )
        
        if spam_count > 0:
            recommendations.append(
                f"🗑️ Filter out {spam_count} spam reviews from analysis. "
                "Exclude from business intelligence reports."
            )
        
        if repetitive_count > 0:
            recommendations.append(
                f"🔄 Deduplicate {repetitive_count} repetitive reviews. "
                "Keep only unique complaints for clustering."
            )
        
        if not recommendations:
            recommendations.append("✅ No significant adversarial content detected. Reviews appear genuine.")
        
        return recommendations
    
    def save_report(self, report: AdversarialReport, output_path: str) -> None:
        """Save adversarial report to JSON"""
        try:
            report_dict = {
                'report_id': report.report_id,
                'timestamp': report.timestamp,
                'detection_summary': report.detection_summary,
                'alerts': report.alerts,
                'recommendations': report.recommendations,
                'coordinated_bursts_count': len(report.coordinated_bursts),
                'high_risk_reviews_count': len(report.high_risk_reviews)
            }
            
            with open(output_path, 'w') as f:
                json.dump(report_dict, f, indent=2)
            
            logger.info(f"Adversarial report saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error saving report: {e}")
            raise
    
    def generate_markdown_report(
        self,
        report: AdversarialReport,
        output_path: str
    ) -> None:
        """Generate human-readable Markdown report"""
        try:
            lines = []
            lines.append("# Adversarial Content Detection Report")
            lines.append(f"\n**Report ID:** {report.report_id}")
            lines.append(f"**Generated:** {report.timestamp}")
            lines.append(f"**Total Reviews Analyzed:** {report.total_reviews}")
            
            lines.append(f"\n## Detection Summary")
            lines.append(f"\n| Type | Count | Percentage |")
            lines.append(f"|------|-------|------------|")
            
            total = report.total_reviews
            lines.append(f"| Fake Positive | {report.fake_positive_count} | {report.fake_positive_count/total*100:.1f}% |")
            lines.append(f"| Sarcasm | {report.sarcasm_count} | {report.sarcasm_count/total*100:.1f}% |")
            lines.append(f"| Coordinated | {report.coordinated_count} | {report.coordinated_count/total*100:.1f}% |")
            lines.append(f"| Repetitive | {report.repetitive_count} | {report.repetitive_count/total*100:.1f}% |")
            lines.append(f"| Spam | {report.spam_count} | {report.spam_count/total*100:.1f}% |")
            lines.append(f"| **High Risk** | **{len(report.high_risk_reviews)}** | **{len(report.high_risk_reviews)/total*100:.1f}%** |")
            lines.append(f"| **Clean** | **{report.detection_summary['clean_reviews']}** | **{report.detection_summary['clean_reviews']/total*100:.1f}%** |")
            
            if report.coordinated_bursts:
                lines.append(f"\n## 🚨 Coordinated Review Bursts")
                for burst in report.coordinated_bursts[:5]:
                    lines.append(f"\n### Burst: {burst.burst_id}")
                    lines.append(f"- **Time Window:** {burst.timestamp_start} to {burst.timestamp_end}")
                    lines.append(f"- **Review Count:** {burst.review_count}")
                    lines.append(f"- **Avg Similarity:** {burst.avg_similarity:.2f}")
                    lines.append(f"- **Suspicion Score:** {burst.suspicion_score:.2f}")
                    if burst.common_patterns:
                        lines.append(f"- **Common Phrases:** {', '.join(burst.common_patterns[:3])}")
            
            if report.high_risk_reviews:
                lines.append(f"\n## ⚠️ High Risk Reviews")
                for flags in report.high_risk_reviews[:10]:
                    lines.append(f"\n### Review {flags.review_id}")
                    lines.append(f"- **Suspicion Score:** {flags.suspicion_score:.2f}")
                    lines.append(f"- **Flags:** {', '.join(flags.flags)}")
            
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
