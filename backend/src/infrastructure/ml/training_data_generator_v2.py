"""
Training Data Generator V2 - 3-Label Support
Handles: actionable, non_actionable, uncertain
Treats uncertain samples as soft labels with reduced weight during training.
"""

import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from datetime import datetime

from src.infrastructure.ml.feature_engineering import FeatureExtractor

logger = logging.getLogger(__name__)


class TrainingDataGeneratorV2:
    """
    Generate labeled training data with 3-label support.
    
    Labels:
        - actionable: Clear actionable feedback (weight=1.0)
        - non_actionable: Clear non-actionable content (weight=1.0)
        - uncertain: Ambiguous cases (weight=0.5 for soft labeling)
    """
    
    def __init__(self):
        self.feature_extractor = FeatureExtractor()
        
        # Confidence mapping for 3-label system
        self.label_confidence_map = {
            'actionable': 0.95,
            'non_actionable': 0.95,
            'uncertain': 0.5  # Low confidence for uncertain
        }
        
        # Sample weight mapping (for training)
        self.label_weight_map = {
            'actionable': 1.0,
            'non_actionable': 1.0,
            'uncertain': 0.5  # Reduced weight for uncertain samples
        }
    
    def load_ground_truth_csv(
        self,
        csv_path: str,
        text_col: str = 'content',
        rating_col: str = 'score',
        label_col: str = 'manual_label'
    ) -> pd.DataFrame:
        """
        Load ground truth CSV with manual labels.
        
        Args:
            csv_path: Path to ground truth CSV
            text_col: Column name for review text
            rating_col: Column name for rating
            label_col: Column name for manual label
            
        Returns:
            DataFrame with standardized columns
        """
        logger.info(f"Loading ground truth from {csv_path}")
        
        df = pd.read_csv(csv_path)
        
        # Validate required columns
        if label_col not in df.columns:
            raise ValueError(f"CSV must have '{label_col}' column")
        if text_col not in df.columns:
            raise ValueError(f"CSV must have '{text_col}' column")
        
        # Standardize column names
        df = df.rename(columns={
            text_col: 'text',
            rating_col: 'rating',
            label_col: 'manual_label'
        })
        
        # Validate label values
        valid_labels = {'actionable', 'non_actionable', 'uncertain'}
        invalid_labels = set(df['manual_label'].unique()) - valid_labels
        if invalid_labels:
            logger.warning(f"Invalid labels found: {invalid_labels}. Will filter them out.")
            df = df[df['manual_label'].isin(valid_labels)]
        
        logger.info(f"Loaded {len(df)} samples")
        logger.info(f"Label distribution:\n{df['manual_label'].value_counts()}")
        
        return df
    
    def prepare_training_data(
        self,
        df: pd.DataFrame,
        extract_features: bool = True
    ) -> pd.DataFrame:
        """
        Prepare training data with features and weights.
        
        Args:
            df: DataFrame with 'text', 'rating', 'manual_label'
            extract_features: Whether to extract ML features
            
        Returns:
            DataFrame with binary labels, confidence, and sample weights
        """
        logger.info("Preparing training data...")
        
        # Convert 3-label to binary (actionable vs non-actionable)
        # uncertain samples get label based on heuristic but with low confidence
        df['label'] = df['manual_label'].apply(self._convert_to_binary_label)
        df['confidence'] = df['manual_label'].map(self.label_confidence_map)
        df['sample_weight'] = df['manual_label'].map(self.label_weight_map)
        
        # Extract features if requested
        if extract_features:
            logger.info("Extracting features...")
            features_list = []
            
            for _, row in df.iterrows():
                features = self.feature_extractor.extract(
                    text=row['text'],
                    rating=row.get('rating', 3.0)
                )
                features_list.append(features.to_array())
            
            # Add feature columns
            from src.infrastructure.ml.feature_engineering import FeatureVector
            feature_names = FeatureVector.feature_names()
            features_array = np.array(features_list)
            
            for i, name in enumerate(feature_names):
                df[f'feature_{name}'] = features_array[:, i]
        
        # Statistics
        stats = {
            'total_samples': len(df),
            'actionable': sum(df['label'] == 1),
            'non_actionable': sum(df['label'] == 0),
            'uncertain_as_actionable': sum((df['manual_label'] == 'uncertain') & (df['label'] == 1)),
            'uncertain_as_non_actionable': sum((df['manual_label'] == 'uncertain') & (df['label'] == 0)),
            'avg_sample_weight': float(df['sample_weight'].mean()),
            'high_confidence_samples': sum(df['confidence'] >= 0.8),
            'low_confidence_samples': sum(df['confidence'] < 0.6)
        }
        
        logger.info(f"Training data prepared:")
        logger.info(f"  - Total: {stats['total_samples']} samples")
        logger.info(f"  - Binary labels: {stats['actionable']} actionable, {stats['non_actionable']} non-actionable")
        logger.info(f"  - Uncertain handling: {stats['uncertain_as_actionable']} → actionable, {stats['uncertain_as_non_actionable']} → non-actionable")
        logger.info(f"  - Avg sample weight: {stats['avg_sample_weight']:.2f}")
        logger.info(f"  - High confidence: {stats['high_confidence_samples']} ({stats['high_confidence_samples']/stats['total_samples']*100:.1f}%)")
        
        return df
    
    def _convert_to_binary_label(self, manual_label: str) -> int:
        """
        Convert 3-label to binary label.
        
        Strategy for 'uncertain':
        - If review has complaint indicators → actionable (1)
        - Otherwise → non-actionable (0)
        """
        if manual_label == 'actionable':
            return 1
        elif manual_label == 'non_actionable':
            return 0
        else:  # uncertain
            # Use heuristic: treat as actionable for now (will have low weight)
            # In production, we could use more sophisticated logic
            return 1
    
    def create_training_test_split(
        self,
        df: pd.DataFrame,
        test_size: float = 0.2,
        stratify_by: str = 'manual_label'
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split data into training and test sets with stratification.
        
        Args:
            df: DataFrame with prepared data
            test_size: Fraction of data for test set
            stratify_by: Column to stratify by (preserves label distribution)
            
        Returns:
            (train_df, test_df)
        """
        logger.info(f"Creating train/test split (test_size={test_size}, stratify={stratify_by})")
        
        train_list = []
        test_list = []
        
        # Stratify by manual_label to preserve 3-label distribution
        for label_value in df[stratify_by].unique():
            subset = df[df[stratify_by] == label_value]
            n_test = max(1, int(len(subset) * test_size))  # At least 1 sample
            
            if len(subset) < 2:
                # Too few samples, put in training
                train_list.append(subset)
                continue
            
            test_subset = subset.sample(n=n_test, random_state=42)
            train_subset = subset.drop(test_subset.index)
            
            train_list.append(train_subset)
            test_list.append(test_subset)
        
        train_df = pd.concat(train_list).sample(frac=1, random_state=42).reset_index(drop=True)
        test_df = pd.concat(test_list).sample(frac=1, random_state=42).reset_index(drop=True)
        
        logger.info(f"Split complete:")
        logger.info(f"  - Training: {len(train_df)} samples")
        logger.info(f"    {train_df['manual_label'].value_counts().to_dict()}")
        logger.info(f"  - Test: {len(test_df)} samples")
        logger.info(f"    {test_df['manual_label'].value_counts().to_dict()}")
        
        return train_df, test_df
    
    def get_high_rating_actionables(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract high-rating actionable reviews (edge cases for evaluation).
        
        These are challenging cases: positive overall but with actionable feedback.
        """
        high_rating_actionable = df[
            (df['manual_label'] == 'actionable') & 
            (df['rating'] >= 4)
        ]
        
        logger.info(f"Found {len(high_rating_actionable)} high-rating actionable reviews")
        
        return high_rating_actionable
    
    def get_mixed_sentiment_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract samples with mixed sentiment (another edge case).
        
        Uses feature extraction to identify reviews with both positive and negative signals.
        """
        mixed_samples = []
        
        for idx, row in df.iterrows():
            features = self.feature_extractor.extract(
                text=row['text'],
                rating=row.get('rating', 3.0)
            )
            
            # Detect mixed sentiment: both positive and negative words
            if features.positive_words > 0 and features.negative_words > 0:
                mixed_samples.append(idx)
        
        mixed_df = df.loc[mixed_samples]
        
        logger.info(f"Found {len(mixed_df)} mixed sentiment samples")
        
        return mixed_df


def prepare_ground_truth_training(
    csv_path: str,
    output_dir: str = "./data/training",
    test_size: float = 0.2
) -> Tuple[str, str, Dict]:
    """
    Convenience function to prepare training data from ground truth CSV.
    
    Args:
        csv_path: Path to ground truth CSV with manual labels
        output_dir: Directory to save processed data
        test_size: Fraction of data for test set
        
    Returns:
        (train_path, test_path, statistics)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generator = TrainingDataGeneratorV2()
    
    # Load ground truth
    df = generator.load_ground_truth_csv(csv_path)
    
    # Prepare training data
    df_prepared = generator.prepare_training_data(df, extract_features=True)
    
    # Train/test split
    train_df, test_df = generator.create_training_test_split(
        df_prepared,
        test_size=test_size,
        stratify_by='manual_label'
    )
    
    # Save datasets
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    train_path = output_dir / f"train_v2_{timestamp}.csv"
    test_path = output_dir / f"test_v2_{timestamp}.csv"
    
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)
    
    # Extract edge cases for evaluation
    high_rating_actionable = generator.get_high_rating_actionables(test_df)
    mixed_sentiment = generator.get_mixed_sentiment_samples(test_df)
    
    # Statistics
    stats = {
        'total_samples': len(df_prepared),
        'train_samples': len(train_df),
        'test_samples': len(test_df),
        'train_distribution': train_df['manual_label'].value_counts().to_dict(),
        'test_distribution': test_df['manual_label'].value_counts().to_dict(),
        'high_rating_actionable_count': len(high_rating_actionable),
        'mixed_sentiment_count': len(mixed_sentiment),
        'avg_sample_weight': float(df_prepared['sample_weight'].mean())
    }
    
    logger.info("Ground truth training data prepared:")
    logger.info(f"  - Training set: {train_path}")
    logger.info(f"  - Test set: {test_path}")
    logger.info(f"  - Edge cases: {stats['high_rating_actionable_count']} high-rating actionable, {stats['mixed_sentiment_count']} mixed sentiment")
    
    return str(train_path), str(test_path), stats
