"""
Data Validation and Robustness Module

Provides graceful handling for corrupted/malformed review data:
- Missing columns
- Invalid schema
- Null/empty reviews
- Duplicate records
- Extremely long text
- Emoji/noise-heavy reviews
- Mixed-language inputs

NEVER crashes - always logs warnings and continues processing.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation with warnings and corrections."""
    is_valid: bool
    warnings: List[str] = field(default_factory=list)
    corrections_applied: List[str] = field(default_factory=list)
    cleaned_data: Optional[Dict[str, Any]] = None


@dataclass
class DatasetValidationReport:
    """Report for entire dataset validation."""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    warnings_by_type: Dict[str, int] = field(default_factory=dict)
    corrections_by_type: Dict[str, int] = field(default_factory=dict)
    error_samples: List[Dict[str, Any]] = field(default_factory=list)


class ReviewValidator:
    """
    Validates and cleans review data with graceful error handling.
    
    Never throws exceptions - returns ValidationResult with warnings.
    """
    
    # Required columns for review processing
    REQUIRED_COLUMNS = ['reviewId', 'content', 'score']
    OPTIONAL_COLUMNS = ['userName', 'thumbsUpCount', 'reviewCreatedVersion', 'at', 'appVersion']
    
    # Validation thresholds
    MAX_REVIEW_LENGTH = 10000  # Characters
    MIN_REVIEW_LENGTH = 1
    MAX_EMOJI_RATIO = 0.5  # 50% emojis = noise
    MIN_WORD_COUNT = 1
    MAX_DUPLICATE_SIMILARITY = 0.95  # 95% similar = duplicate
    
    # Emoji and noise patterns
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", 
        flags=re.UNICODE
    )
    
    # Language detection patterns (basic)
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
    
    def __init__(self):
        self.validation_stats = {
            'total_validated': 0,
            'schema_errors': 0,
            'null_content': 0,
            'empty_content': 0,
            'too_long': 0,
            'too_short': 0,
            'noise_heavy': 0,
            'mixed_language': 0,
            'invalid_score': 0,
            'missing_required': 0,
        }
    
    def validate_review(self, review_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate and clean a single review.
        
        Args:
            review_data: Dictionary with review fields
            
        Returns:
            ValidationResult with is_valid, warnings, corrections, cleaned_data
        """
        self.validation_stats['total_validated'] += 1
        
        warnings = []
        corrections = []
        cleaned = review_data.copy()
        is_valid = True
        
        # 1. Check required columns
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in review_data]
        if missing_cols:
            warnings.append(f"Missing required columns: {missing_cols}")
            self.validation_stats['missing_required'] += 1
            
            # Try to provide defaults
            if 'reviewId' not in review_data:
                cleaned['reviewId'] = f"generated_{self.validation_stats['total_validated']}"
                corrections.append("Generated missing reviewId")
            if 'content' not in review_data:
                cleaned['content'] = ""
                warnings.append("Missing content - will skip processing")
                is_valid = False
            if 'score' not in review_data:
                cleaned['score'] = 3  # Neutral default
                corrections.append("Set missing score to neutral (3)")
        
        # 2. Validate content field
        content = cleaned.get('content', '')
        
        # Handle None/NaN
        if content is None or (isinstance(content, float) and pd.isna(content)):
            warnings.append("Content is null/NaN")
            cleaned['content'] = ""
            self.validation_stats['null_content'] += 1
            is_valid = False
        else:
            content = str(content).strip()
            cleaned['content'] = content
            
            # Check if empty
            if len(content) == 0:
                warnings.append("Content is empty after cleaning")
                self.validation_stats['empty_content'] += 1
                is_valid = False
            else:
                # Check length
                if len(content) > self.MAX_REVIEW_LENGTH:
                    warnings.append(f"Review too long ({len(content)} chars, max {self.MAX_REVIEW_LENGTH})")
                    cleaned['content'] = content[:self.MAX_REVIEW_LENGTH]
                    corrections.append(f"Truncated review to {self.MAX_REVIEW_LENGTH} chars")
                    self.validation_stats['too_long'] += 1
                
                if len(content) < self.MIN_REVIEW_LENGTH:
                    warnings.append(f"Review too short ({len(content)} chars)")
                    self.validation_stats['too_short'] += 1
                    is_valid = False
                
                # Check emoji/noise ratio
                emoji_count = len(self.EMOJI_PATTERN.findall(content))
                if len(content) > 0:
                    emoji_ratio = emoji_count / len(content)
                    if emoji_ratio > self.MAX_EMOJI_RATIO:
                        warnings.append(f"High emoji/noise ratio ({emoji_ratio:.1%})")
                        self.validation_stats['noise_heavy'] += 1
                        # Don't invalidate - might still have useful text
                
                # Check word count
                words = content.split()
                if len(words) < self.MIN_WORD_COUNT:
                    warnings.append(f"Too few words ({len(words)})")
                    is_valid = False
                
                # Detect mixed languages
                detected_langs = self._detect_languages(content)
                if len(detected_langs) > 1:
                    warnings.append(f"Mixed languages detected: {detected_langs}")
                    self.validation_stats['mixed_language'] += 1
                    # Don't invalidate - can still process
        
        # 3. Validate score
        score = cleaned.get('score')
        try:
            score = int(score) if score is not None else None
            if score is not None:
                if not (1 <= score <= 5):
                    warnings.append(f"Score out of range: {score} (expected 1-5)")
                    cleaned['score'] = max(1, min(5, score))  # Clamp to valid range
                    corrections.append(f"Clamped score to valid range")
                    self.validation_stats['invalid_score'] += 1
            else:
                cleaned['score'] = 3  # Neutral default
                corrections.append("Set null score to neutral (3)")
        except (ValueError, TypeError):
            warnings.append(f"Invalid score value: {score}")
            cleaned['score'] = 3
            corrections.append("Set invalid score to neutral (3)")
            self.validation_stats['invalid_score'] += 1
        
        # 4. Add optional columns with defaults
        for col in self.OPTIONAL_COLUMNS:
            if col not in cleaned:
                cleaned[col] = None
        
        return ValidationResult(
            is_valid=is_valid,
            warnings=warnings,
            corrections_applied=corrections,
            cleaned_data=cleaned
        )
    
    def validate_dataset(
        self, 
        df: pd.DataFrame, 
        max_error_samples: int = 10
    ) -> Tuple[pd.DataFrame, DatasetValidationReport]:
        """
        Validate entire dataset and return cleaned version.
        
        Args:
            df: Input DataFrame
            max_error_samples: Max number of error examples to include in report
            
        Returns:
            (cleaned_df, validation_report)
        """
        logger.info(f"Validating dataset with {len(df)} rows...")
        
        cleaned_rows = []
        valid_count = 0
        invalid_count = 0
        warnings_by_type: Dict[str, int] = {}
        corrections_by_type: Dict[str, int] = {}
        error_samples = []
        
        for idx, row in df.iterrows():
            try:
                review_data = row.to_dict()
                result = self.validate_review(review_data)
                
                # Track statistics
                for warning in result.warnings:
                    warning_type = warning.split(':')[0] if ':' in warning else warning
                    warnings_by_type[warning_type] = warnings_by_type.get(warning_type, 0) + 1
                
                for correction in result.corrections_applied:
                    correction_type = correction.split(' ')[0]
                    corrections_by_type[correction_type] = corrections_by_type.get(correction_type, 0) + 1
                
                if result.is_valid:
                    valid_count += 1
                    cleaned_rows.append(result.cleaned_data)
                else:
                    invalid_count += 1
                    # Store sample errors
                    if len(error_samples) < max_error_samples:
                        error_samples.append({
                            'row_index': idx,
                            'original': review_data,
                            'warnings': result.warnings,
                            'is_recoverable': result.cleaned_data is not None
                        })
                    # Still include if cleaned data exists
                    if result.cleaned_data is not None:
                        cleaned_rows.append(result.cleaned_data)
            
            except Exception as e:
                # NEVER crash - log and continue
                logger.error(f"Unexpected error validating row {idx}: {e}")
                invalid_count += 1
                if len(error_samples) < max_error_samples:
                    error_samples.append({
                        'row_index': idx,
                        'original': row.to_dict(),
                        'warnings': [f"Unexpected error: {str(e)}"],
                        'is_recoverable': False
                    })
        
        cleaned_df = pd.DataFrame(cleaned_rows)
        
        report = DatasetValidationReport(
            total_rows=len(df),
            valid_rows=valid_count,
            invalid_rows=invalid_count,
            warnings_by_type=warnings_by_type,
            corrections_by_type=corrections_by_type,
            error_samples=error_samples
        )
        
        logger.info(f"Validation complete: {valid_count} valid, {invalid_count} invalid")
        logger.info(f"Cleaned dataset has {len(cleaned_df)} rows")
        
        return cleaned_df, report
    
    def detect_duplicates(
        self, 
        df: pd.DataFrame, 
        content_column: str = 'content'
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Detect and remove duplicate reviews.
        
        Args:
            df: DataFrame with reviews
            content_column: Column name for review text
            
        Returns:
            (deduplicated_df, duplicate_report)
        """
        original_count = len(df)
        
        # Exact duplicates
        df_deduped = df.drop_duplicates(subset=[content_column], keep='first')
        exact_duplicates = original_count - len(df_deduped)
        
        report = {
            'original_count': original_count,
            'deduplicated_count': len(df_deduped),
            'exact_duplicates_removed': exact_duplicates,
            'duplicate_rate': exact_duplicates / original_count if original_count > 0 else 0.0
        }
        
        logger.info(f"Removed {exact_duplicates} duplicate reviews ({report['duplicate_rate']:.1%})")
        
        return df_deduped, report
    
    def _detect_languages(self, text: str) -> List[str]:
        """Detect languages present in text (basic pattern matching)."""
        detected = []
        
        # Check for non-ASCII (likely non-English)
        if any(ord(char) > 127 for char in text):
            for lang, pattern in self.LANGUAGE_PATTERNS.items():
                if pattern.search(text):
                    detected.append(lang)
        
        # If no specific language detected but has ASCII, assume English
        if not detected and any(char.isalpha() for char in text):
            detected.append('english')
        
        return detected
    
    def get_statistics(self) -> Dict[str, int]:
        """Get validation statistics."""
        return self.validation_stats.copy()
    
    def reset_statistics(self):
        """Reset validation counters."""
        for key in self.validation_stats:
            self.validation_stats[key] = 0


def validate_csv_file(
    csv_path: str, 
    output_path: Optional[str] = None
) -> Tuple[pd.DataFrame, DatasetValidationReport]:
    """
    Validate and clean a CSV file with reviews.
    
    Args:
        csv_path: Path to input CSV
        output_path: Optional path to save cleaned CSV
        
    Returns:
        (cleaned_df, validation_report)
    """
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        logger.error(f"Failed to read CSV {csv_path}: {e}")
        # Return empty dataframe and error report
        return pd.DataFrame(), DatasetValidationReport(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            warnings_by_type={'file_read_error': 1},
            error_samples=[{'error': str(e)}]
        )
    
    validator = ReviewValidator()
    cleaned_df, report = validator.validate_dataset(df)
    
    # Remove duplicates
    cleaned_df, dup_report = validator.detect_duplicates(cleaned_df)
    report.warnings_by_type['duplicates'] = dup_report['exact_duplicates_removed']
    
    if output_path:
        try:
            cleaned_df.to_csv(output_path, index=False)
            logger.info(f"Saved cleaned dataset to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save cleaned CSV: {e}")
    
    return cleaned_df, report
