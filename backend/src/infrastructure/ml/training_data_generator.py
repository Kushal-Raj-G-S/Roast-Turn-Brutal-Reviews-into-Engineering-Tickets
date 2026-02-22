"""
Training Data Generator for Actionability Scorer
Semi-supervised labeling using rule-based heuristics + manual annotations.
"""

import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from datetime import datetime

from src.infrastructure.ml.feature_engineering import FeatureExtractor, calculate_sentiment_polarity, detect_mixed_sentiment

logger = logging.getLogger(__name__)


class TrainingDataGenerator:
    """
    Generate labeled training data for actionability scoring.
    Uses high-confidence rules to auto-label reviews.
    """
    
    def __init__(self):
        self.feature_extractor = FeatureExtractor()
    
    def generate_from_csv(
        self,
        csv_path: str,
        output_path: Optional[str] = None,
        sample_size: Optional[int] = None
    ) -> Tuple[pd.DataFrame, Dict[str, int]]:
        """
        Generate labeled training data from CSV file.
        
        Args:
            csv_path: Path to reviews CSV
            output_path: Optional path to save labeled data
            sample_size: Optional limit on number of samples
            
        Returns:
            DataFrame with labels and statistics dict
        """
        logger.info(f"Generating training data from {csv_path}")
        
        # Load reviews
        df = pd.read_csv(csv_path)
        
        if sample_size and len(df) > sample_size:
            df = df.sample(n=sample_size, random_state=42)
        
        # Ensure required columns
        if 'content' not in df.columns:
            raise ValueError("CSV must have 'content' column")
        
        # Standardize column names
        df = df.rename(columns={'content': 'text'})
        
        # Extract features and auto-label
        labels = []
        confidences = []
        label_reasons = []
        
        for _, row in df.iterrows():
            text = str(row.get('text', ''))
            rating = row.get('score', 3.0)
            
            label, confidence, reasons = self._auto_label(text, rating)
            labels.append(label)
            confidences.append(confidence)
            label_reasons.append(reasons)
        
        df['label'] = labels
        df['confidence'] = confidences
        df['label_reason'] = label_reasons
        
        # Statistics
        stats = {
            'total_samples': len(df),
            'actionable': sum(labels),
            'non_actionable': len(labels) - sum(labels),
            'high_confidence': sum(1 for c in confidences if c >= 0.8),
            'low_confidence': sum(1 for c in confidences if c < 0.6),
            'avg_confidence': float(np.mean(confidences))
        }
        
        logger.info(f"Generated {stats['total_samples']} labeled samples:")
        logger.info(f"  - Actionable: {stats['actionable']} ({stats['actionable']/stats['total_samples']*100:.1f}%)")
        logger.info(f"  - Non-actionable: {stats['non_actionable']} ({stats['non_actionable']/stats['total_samples']*100:.1f}%)")
        logger.info(f"  - High confidence: {stats['high_confidence']} ({stats['high_confidence']/stats['total_samples']*100:.1f}%)")
        logger.info(f"  - Avg confidence: {stats['avg_confidence']:.3f}")
        
        # Save if output path provided
        if output_path:
            df.to_csv(output_path, index=False)
            logger.info(f"Saved labeled data to {output_path}")
        
        return df, stats
    
    def _auto_label(self, text: str, rating: Optional[float] = None) -> Tuple[bool, float, str]:
        """
        Automatically label a review using high-confidence rules.
        
        Returns:
            (is_actionable, confidence, reason)
        """
        if not text or len(text.strip()) == 0:
            return False, 1.0, "empty_review"
        
        # Extract features
        features = self.feature_extractor.extract(text, rating=rating)
        text_lower = text.lower()
        
        # High confidence ACTIONABLE rules
        
        # 1. Low rating + complaints
        if features.rating <= 2.0 and features.complaint_verbs >= 1:
            return True, 0.95, "low_rating_with_complaints"
        
        # 2. Bug reports with details
        if features.has_bug_keywords and features.has_specific_details:
            return True, 0.9, "bug_with_details"
        
        # 3. Multiple complaints
        if features.complaint_verbs >= 2 and features.negative_words >= 3:
            return True, 0.9, "multiple_complaints"
        
        # 4. Specific technical issues
        if features.has_specific_details and features.negative_words >= 2:
            return True, 0.85, "technical_issue_with_details"
        
        # 5. Feature requests with context
        if features.has_feature_request and features.has_specific_details:
            return True, 0.8, "feature_request_with_details"
        
        # 6. Mixed sentiment (often actionable)
        if detect_mixed_sentiment(text):
            return True, 0.75, "mixed_sentiment"
        
        # 7. Critical errors
        critical_keywords = ['crash', 'crashes', 'crashing', 'freeze', 'not working', 'cant open', 'wont load']
        if any(kw in text_lower for kw in critical_keywords):
            return True, 0.85, "critical_error"
        
        # High confidence NON-ACTIONABLE rules
        
        # 1. Very short reviews
        if features.word_count < 3 or features.length < 15:
            return False, 0.9, "too_short"
        
        # 2. High rating without negatives
        if features.rating >= 4.5 and features.negative_words == 0 and features.complaint_verbs == 0:
            return False, 0.85, "high_rating_no_negatives"
        
        # 3. Pure praise
        if features.positive_words >= 3 and features.negative_words == 0 and features.rating >= 4.0:
            return False, 0.8, "pure_praise"
        
        # 4. Generic positive
        generic_positive = ['good', 'nice', 'ok', 'fine', 'thanks', 'thank you']
        if features.word_count <= 5 and any(word in text_lower for word in generic_positive):
            return False, 0.8, "generic_positive"
        
        # 5. Just emoji or symbols
        if len([c for c in text if c.isalpha()]) < 5:
            return False, 0.9, "mostly_symbols"
        
        # Medium confidence rules
        
        # Negative sentiment = likely actionable
        polarity = calculate_sentiment_polarity(text)
        if polarity < -0.3:
            return True, 0.65, "negative_sentiment"
        
        # Positive sentiment = likely not actionable
        if polarity > 0.3 and features.rating >= 4.0:
            return False, 0.65, "positive_sentiment"
        
        # Questions without complaints = uncertain
        if features.question_marks > 0 and features.negative_words < 2:
            return True, 0.5, "question_uncertain"
        
        # Default: weakly actionable (better to include than exclude)
        return True, 0.5, "default_include"
    
    def filter_high_confidence(
        self,
        df: pd.DataFrame,
        min_confidence: float = 0.7
    ) -> pd.DataFrame:
        """
        Filter dataset to only high-confidence labels.
        Useful for initial model training.
        """
        if 'confidence' not in df.columns:
            raise ValueError("DataFrame must have 'confidence' column")
        
        filtered = df[df['confidence'] >= min_confidence].copy()
        
        logger.info(f"Filtered to {len(filtered)} high-confidence samples (>= {min_confidence})")
        logger.info(f"  - Kept {len(filtered)/len(df)*100:.1f}% of original data")
        
        return filtered
    
    def balance_dataset(
        self,
        df: pd.DataFrame,
        method: str = 'undersample'
    ) -> pd.DataFrame:
        """
        Balance actionable vs non-actionable samples.
        
        Args:
            df: DataFrame with 'label' column
            method: 'undersample', 'oversample', or 'smote'
        """
        if 'label' not in df.columns:
            raise ValueError("DataFrame must have 'label' column")
        
        actionable = df[df['label'] == True]
        non_actionable = df[df['label'] == False]
        
        n_actionable = len(actionable)
        n_non_actionable = len(non_actionable)
        
        logger.info(f"Original balance: {n_actionable} actionable, {n_non_actionable} non-actionable")
        
        if method == 'undersample':
            # Undersample majority class
            min_count = min(n_actionable, n_non_actionable)
            actionable_sample = actionable.sample(n=min_count, random_state=42)
            non_actionable_sample = non_actionable.sample(n=min_count, random_state=42)
            balanced = pd.concat([actionable_sample, non_actionable_sample])
            
        elif method == 'oversample':
            # Oversample minority class
            max_count = max(n_actionable, n_non_actionable)
            if n_actionable < n_non_actionable:
                actionable_sample = actionable.sample(n=max_count, replace=True, random_state=42)
                balanced = pd.concat([actionable_sample, non_actionable])
            else:
                non_actionable_sample = non_actionable.sample(n=max_count, replace=True, random_state=42)
                balanced = pd.concat([actionable, non_actionable_sample])
        
        else:
            raise ValueError(f"Unknown balancing method: {method}")
        
        balanced = balanced.sample(frac=1, random_state=42).reset_index(drop=True)
        
        logger.info(f"Balanced dataset: {len(balanced)} samples ({len(balanced)//2} each class)")
        
        return balanced
    
    def create_training_test_split(
        self,
        df: pd.DataFrame,
        test_size: float = 0.2,
        stratify: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split data into training and test sets.
        """
        if stratify and 'label' in df.columns:
            # Stratified split to maintain class balance
            train_list = []
            test_list = []
            
            for label_value in df['label'].unique():
                subset = df[df['label'] == label_value]
                n_test = int(len(subset) * test_size)
                test_subset = subset.sample(n=n_test, random_state=42)
                train_subset = subset.drop(test_subset.index)
                
                train_list.append(train_subset)
                test_list.append(test_subset)
            
            train_df = pd.concat(train_list).sample(frac=1, random_state=42)
            test_df = pd.concat(test_list).sample(frac=1, random_state=42)
        else:
            # Simple random split
            n_test = int(len(df) * test_size)
            test_df = df.sample(n=n_test, random_state=42)
            train_df = df.drop(test_df.index)
        
        logger.info(f"Split: {len(train_df)} training, {len(test_df)} test samples")
        
        return train_df, test_df


def prepare_training_data(
    csv_paths: List[str],
    output_dir: str = "./data/training",
    min_confidence: float = 0.7,
    balance: bool = True,
    max_samples: Optional[int] = None
) -> Tuple[str, str, Dict[str, int]]:
    """
    Convenience function to prepare training data from multiple CSVs.
    
    Args:
        csv_paths: List of paths to review CSV files
        output_dir: Directory to save processed data
        min_confidence: Minimum confidence for filtering
        balance: Whether to balance classes
        max_samples: Maximum total samples to use
        
    Returns:
        (train_path, test_path, statistics)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generator = TrainingDataGenerator()
    
    # Generate labels for each CSV
    all_dfs = []
    for csv_path in csv_paths:
        try:
            df, stats = generator.generate_from_csv(csv_path)
            all_dfs.append(df)
            logger.info(f"Processed {csv_path}: {len(df)} samples")
        except Exception as e:
            logger.error(f"Failed to process {csv_path}: {e}")
    
    if not all_dfs:
        raise ValueError("No data could be loaded")
    
    # Combine all data
    combined_df = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Combined {len(combined_df)} total samples from {len(all_dfs)} files")
    
    # Filter high confidence
    filtered_df = generator.filter_high_confidence(combined_df, min_confidence=min_confidence)
    
    # Balance classes
    if balance:
        filtered_df = generator.balance_dataset(filtered_df, method='undersample')
    
    # Limit samples if requested
    if max_samples and len(filtered_df) > max_samples:
        filtered_df = filtered_df.sample(n=max_samples, random_state=42)
        logger.info(f"Limited to {max_samples} samples")
    
    # Train/test split
    train_df, test_df = generator.create_training_test_split(filtered_df, test_size=0.2)
    
    # Save datasets
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    train_path = output_dir / f"train_{timestamp}.csv"
    test_path = output_dir / f"test_{timestamp}.csv"
    
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)
    
    stats = {
        'total_samples': len(filtered_df),
        'train_samples': len(train_df),
        'test_samples': len(test_df),
        'actionable': sum(filtered_df['label']),
        'non_actionable': len(filtered_df) - sum(filtered_df['label'])
    }
    
    logger.info("Training data prepared successfully:")
    logger.info(f"  - Training set: {train_path}")
    logger.info(f"  - Test set: {test_path}")
    logger.info(f"  - Stats: {stats}")
    
    return str(train_path), str(test_path), stats
