"""
Data Quality Metrics Module

Computes comprehensive quality metrics for review datasets:
- Noise rate (emoji, meaningless content)
- Duplicate rate
- Language diversity
- Review length distribution
- Validation failure rate
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Comprehensive quality metrics for a dataset."""
    
    # Basic statistics
    total_reviews: int
    valid_reviews: int
    invalid_reviews: int
    validation_failure_rate: float
    
    # Noise metrics
    noise_rate: float  # High emoji/gibberish ratio
    empty_rate: float  # Empty or too short
    too_long_rate: float  # Truncated reviews
    
    # Duplicate metrics
    exact_duplicate_rate: float
    near_duplicate_rate: float
    unique_review_rate: float
    
    # Content quality
    avg_review_length: float
    median_review_length: float
    length_std: float
    length_percentiles: Dict[int, float] = field(default_factory=dict)  # p10, p25, p50, p75, p90
    
    # Language diversity
    language_distribution: Dict[str, int] = field(default_factory=dict)
    mixed_language_rate: float = 0.0
    primary_language: Optional[str] = None
    language_diversity_score: float = 0.0  # Shannon entropy
    
    # Word statistics
    avg_word_count: float = 0.0
    median_word_count: float = 0.0
    vocabulary_size: int = 0
    
    # Rating distribution
    rating_distribution: Dict[int, int] = field(default_factory=dict)
    avg_rating: float = 0.0
    rating_std: float = 0.0


class DataQualityAnalyzer:
    """
    Analyzes data quality for review datasets.
    
    Provides comprehensive metrics for monitoring data quality.
    """
    
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", 
        flags=re.UNICODE
    )
    
    LANGUAGE_PATTERNS = {
        'arabic': re.compile(r'[\u0600-\u06FF]'),
        'chinese': re.compile(r'[\u4e00-\u9fff]'),
        'japanese': re.compile(r'[\u3040-\u309F\u30A0-\u30FF]'),
        'korean': re.compile(r'[\uAC00-\uD7AF]'),
        'cyrillic': re.compile(r'[\u0400-\u04FF]'),
        'hindi': re.compile(r'[\u0900-\u097F]'),
        'bengali': re.compile(r'[\u0980-\u09FF]'),
        'thai': re.compile(r'[\u0E00-\u0E7F]'),
    }
    
    def __init__(
        self, 
        noise_emoji_threshold: float = 0.5,
        min_review_length: int = 10,
        max_review_length: int = 10000
    ):
        self.noise_emoji_threshold = noise_emoji_threshold
        self.min_review_length = min_review_length
        self.max_review_length = max_review_length
    
    def analyze_dataset(
        self, 
        df: pd.DataFrame,
        validation_report: Optional[Any] = None
    ) -> QualityMetrics:
        """
        Compute comprehensive quality metrics for dataset.
        
        Args:
            df: DataFrame with reviews (must have 'content' column)
            validation_report: Optional validation report with error stats
            
        Returns:
            QualityMetrics object
        """
        logger.info(f"Analyzing data quality for {len(df)} reviews...")
        
        total_reviews = len(df)
        if total_reviews == 0:
            logger.warning("Empty dataset - returning zero metrics")
            return self._empty_metrics()
        
        # Ensure content column exists
        if 'content' not in df.columns:
            logger.error("Missing 'content' column - cannot analyze quality")
            return self._empty_metrics()
        
        # Get valid reviews (non-null, non-empty content)
        valid_mask = df['content'].notna() & (df['content'].astype(str).str.strip() != '')
        valid_reviews = valid_mask.sum()
        invalid_reviews = total_reviews - valid_reviews
        
        # Noise analysis
        noise_count = 0
        empty_count = invalid_reviews
        too_long_count = 0
        
        lengths = []
        word_counts = []
        all_words = set()
        language_counts = {}
        mixed_language_count = 0
        
        for idx, row in df.iterrows():
            content = row.get('content', '')
            if pd.isna(content):
                continue
            
            content = str(content).strip()
            if len(content) == 0:
                continue
            
            # Length analysis
            length = len(content)
            lengths.append(length)
            
            if length > self.max_review_length:
                too_long_count += 1
            
            # Word analysis
            words = content.split()
            word_counts.append(len(words))
            all_words.update(w.lower() for w in words if w.isalnum())
            
            # Noise detection
            emoji_count = len(self.EMOJI_PATTERN.findall(content))
            if length > 0:
                emoji_ratio = emoji_count / length
                if emoji_ratio > self.noise_emoji_threshold:
                    noise_count += 1
            
            # Language detection
            detected_langs = self._detect_languages(content)
            for lang in detected_langs:
                language_counts[lang] = language_counts.get(lang, 0) + 1
            if len(detected_langs) > 1:
                mixed_language_count += 1
        
        # Duplicate analysis
        exact_duplicates = 0
        if 'content' in df.columns:
            unique_content = df['content'].nunique()
            exact_duplicates = total_reviews - unique_content
        
        # Length statistics
        lengths_array = np.array(lengths) if lengths else np.array([0])
        word_counts_array = np.array(word_counts) if word_counts else np.array([0])
        
        length_percentiles = {
            10: np.percentile(lengths_array, 10),
            25: np.percentile(lengths_array, 25),
            50: np.percentile(lengths_array, 50),
            75: np.percentile(lengths_array, 75),
            90: np.percentile(lengths_array, 90),
        }
        
        # Language diversity (Shannon entropy)
        total_lang_detections = sum(language_counts.values())
        language_diversity = 0.0
        if total_lang_detections > 0:
            for count in language_counts.values():
                p = count / total_lang_detections
                if p > 0:
                    language_diversity -= p * np.log2(p)
        
        primary_language = max(language_counts.items(), key=lambda x: x[1])[0] if language_counts else None
        
        # Rating statistics
        rating_distribution = {}
        avg_rating = 0.0
        rating_std = 0.0
        if 'score' in df.columns:
            ratings = df['score'].dropna()
            if len(ratings) > 0:
                rating_distribution = ratings.value_counts().to_dict()
                avg_rating = ratings.mean()
                rating_std = ratings.std()
        
        # Validation failure rate
        validation_failure_rate = invalid_reviews / total_reviews if total_reviews > 0 else 0.0
        if validation_report:
            validation_failure_rate = validation_report.invalid_rows / validation_report.total_rows
        
        metrics = QualityMetrics(
            total_reviews=total_reviews,
            valid_reviews=valid_reviews,
            invalid_reviews=invalid_reviews,
            validation_failure_rate=validation_failure_rate,
            noise_rate=noise_count / total_reviews if total_reviews > 0 else 0.0,
            empty_rate=empty_count / total_reviews if total_reviews > 0 else 0.0,
            too_long_rate=too_long_count / total_reviews if total_reviews > 0 else 0.0,
            exact_duplicate_rate=exact_duplicates / total_reviews if total_reviews > 0 else 0.0,
            near_duplicate_rate=0.0,  # Would require fuzzy matching - expensive
            unique_review_rate=(total_reviews - exact_duplicates) / total_reviews if total_reviews > 0 else 0.0,
            avg_review_length=float(np.mean(lengths_array)),
            median_review_length=float(np.median(lengths_array)),
            length_std=float(np.std(lengths_array)),
            length_percentiles=length_percentiles,
            language_distribution=language_counts,
            mixed_language_rate=mixed_language_count / total_reviews if total_reviews > 0 else 0.0,
            primary_language=primary_language,
            language_diversity_score=language_diversity,
            avg_word_count=float(np.mean(word_counts_array)),
            median_word_count=float(np.median(word_counts_array)),
            vocabulary_size=len(all_words),
            rating_distribution=rating_distribution,
            avg_rating=avg_rating,
            rating_std=rating_std
        )
        
        logger.info(f"Quality analysis complete: {metrics.validation_failure_rate:.1%} invalid, "
                   f"{metrics.noise_rate:.1%} noisy, {metrics.exact_duplicate_rate:.1%} duplicates")
        
        return metrics
    
    def compare_quality(
        self, 
        metrics1: QualityMetrics, 
        metrics2: QualityMetrics,
        label1: str = "Dataset 1",
        label2: str = "Dataset 2"
    ) -> Dict[str, Any]:
        """
        Compare quality metrics between two datasets.
        
        Returns:
            Dictionary with comparisons and degradation alerts
        """
        comparison = {
            'datasets': {label1: {}, label2: {}},
            'changes': {},
            'alerts': []
        }
        
        # Key metrics to compare
        metrics_to_compare = [
            ('validation_failure_rate', 'Validation Failure Rate', 0.05),
            ('noise_rate', 'Noise Rate', 0.1),
            ('exact_duplicate_rate', 'Duplicate Rate', 0.1),
            ('avg_review_length', 'Avg Review Length', 50),
            ('language_diversity_score', 'Language Diversity', 0.5),
        ]
        
        for metric_name, display_name, threshold in metrics_to_compare:
            val1 = getattr(metrics1, metric_name)
            val2 = getattr(metrics2, metric_name)
            
            comparison['datasets'][label1][metric_name] = val1
            comparison['datasets'][label2][metric_name] = val2
            
            if val1 > 0:
                change_pct = ((val2 - val1) / val1) * 100
                comparison['changes'][metric_name] = {
                    'absolute': val2 - val1,
                    'percent': change_pct,
                    'display_name': display_name
                }
                
                # Generate alerts for significant changes
                if abs(change_pct) > threshold * 100:
                    direction = "increased" if change_pct > 0 else "decreased"
                    comparison['alerts'].append({
                        'metric': display_name,
                        'severity': 'high' if abs(change_pct) > threshold * 200 else 'medium',
                        'message': f"{display_name} {direction} by {abs(change_pct):.1f}% ({val1:.3f} → {val2:.3f})"
                    })
        
        return comparison
    
    def generate_quality_report(
        self, 
        metrics: QualityMetrics,
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate human-readable quality report.
        
        Args:
            metrics: QualityMetrics object
            output_path: Optional path to save Markdown report
            
        Returns:
            Markdown report string
        """
        report_lines = [
            "# Data Quality Report",
            "",
            "## Overview",
            f"- **Total Reviews**: {metrics.total_reviews:,}",
            f"- **Valid Reviews**: {metrics.valid_reviews:,} ({metrics.valid_reviews/metrics.total_reviews*100:.1f}%)",
            f"- **Invalid Reviews**: {metrics.invalid_reviews:,} ({metrics.validation_failure_rate*100:.1f}%)",
            "",
            "## Quality Metrics",
            "",
            "### Noise and Corruption",
            f"- **Noise Rate**: {metrics.noise_rate*100:.2f}% (emoji/gibberish)",
            f"- **Empty Rate**: {metrics.empty_rate*100:.2f}%",
            f"- **Too Long Rate**: {metrics.too_long_rate*100:.2f}% (truncated)",
            "",
            "### Duplicates",
            f"- **Exact Duplicate Rate**: {metrics.exact_duplicate_rate*100:.2f}%",
            f"- **Unique Reviews**: {metrics.unique_review_rate*100:.1f}%",
            "",
            "## Content Statistics",
            "",
            "### Review Length Distribution",
            f"- **Average**: {metrics.avg_review_length:.0f} characters",
            f"- **Median**: {metrics.median_review_length:.0f} characters",
            f"- **Std Dev**: {metrics.length_std:.0f} characters",
            "- **Percentiles**:",
            f"  - p10: {metrics.length_percentiles.get(10, 0):.0f}",
            f"  - p25: {metrics.length_percentiles.get(25, 0):.0f}",
            f"  - p50: {metrics.length_percentiles.get(50, 0):.0f}",
            f"  - p75: {metrics.length_percentiles.get(75, 0):.0f}",
            f"  - p90: {metrics.length_percentiles.get(90, 0):.0f}",
            "",
            "### Word Statistics",
            f"- **Average Words**: {metrics.avg_word_count:.1f}",
            f"- **Median Words**: {metrics.median_word_count:.0f}",
            f"- **Vocabulary Size**: {metrics.vocabulary_size:,} unique words",
            "",
            "## Language Diversity",
            f"- **Primary Language**: {metrics.primary_language or 'Unknown'}",
            f"- **Mixed Language Rate**: {metrics.mixed_language_rate*100:.2f}%",
            f"- **Diversity Score**: {metrics.language_diversity_score:.3f} (Shannon entropy)",
            "",
            "### Language Distribution",
        ]
        
        for lang, count in sorted(metrics.language_distribution.items(), key=lambda x: x[1], reverse=True):
            pct = count / metrics.total_reviews * 100
            report_lines.append(f"- **{lang}**: {count:,} ({pct:.1f}%)")
        
        report_lines.extend([
            "",
            "## Rating Statistics",
            f"- **Average Rating**: {metrics.avg_rating:.2f}",
            f"- **Rating Std Dev**: {metrics.rating_std:.2f}",
            "",
            "### Rating Distribution",
        ])
        
        for rating in sorted(metrics.rating_distribution.keys()):
            count = metrics.rating_distribution[rating]
            pct = count / metrics.total_reviews * 100
            report_lines.append(f"- **{rating} stars**: {count:,} ({pct:.1f}%)")
        
        # Quality assessment
        report_lines.extend([
            "",
            "## Quality Assessment",
            ""
        ])
        
        if metrics.validation_failure_rate > 0.1:
            report_lines.append("⚠️ **HIGH ALERT**: Validation failure rate exceeds 10%")
        if metrics.noise_rate > 0.2:
            report_lines.append("⚠️ **WARNING**: Noise rate exceeds 20%")
        if metrics.exact_duplicate_rate > 0.1:
            report_lines.append("⚠️ **WARNING**: Duplicate rate exceeds 10%")
        if metrics.language_diversity_score > 1.5:
            report_lines.append("ℹ️ **INFO**: High language diversity detected")
        
        if all([
            metrics.validation_failure_rate < 0.05,
            metrics.noise_rate < 0.1,
            metrics.exact_duplicate_rate < 0.05
        ]):
            report_lines.append("✅ **GOOD**: Dataset quality is high")
        
        report = "\n".join(report_lines)
        
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(report)
                logger.info(f"Quality report saved to {output_path}")
            except Exception as e:
                logger.error(f"Failed to save quality report: {e}")
        
        return report
    
    def _detect_languages(self, text: str) -> List[str]:
        """Detect languages in text."""
        detected = []
        
        if any(ord(char) > 127 for char in text):
            for lang, pattern in self.LANGUAGE_PATTERNS.items():
                if pattern.search(text):
                    detected.append(lang)
        
        if not detected and any(char.isalpha() for char in text):
            detected.append('english')
        
        return detected if detected else ['unknown']
    
    def _empty_metrics(self) -> QualityMetrics:
        """Return empty metrics for error cases."""
        return QualityMetrics(
            total_reviews=0,
            valid_reviews=0,
            invalid_reviews=0,
            validation_failure_rate=0.0,
            noise_rate=0.0,
            empty_rate=0.0,
            too_long_rate=0.0,
            exact_duplicate_rate=0.0,
            near_duplicate_rate=0.0,
            unique_review_rate=0.0,
            avg_review_length=0.0,
            median_review_length=0.0,
            length_std=0.0
        )
