"""
Active Learning Module for V3
Minimal implementation for uncertainty-based sample selection and incremental retraining.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


def export_uncertain_reviews(
    results_csv: str,
    output_path: str,
    uncertainty_threshold: float = 0.3,
    max_samples: int = 100,
    include_signals: bool = True
) -> Tuple[int, str]:
    """
    Export high-uncertainty reviews for manual labeling.
    
    Args:
        results_csv: Path to scoring results CSV (must have 'uncertainty' column)
        output_path: Output path for export CSV
        uncertainty_threshold: Minimum uncertainty to export
        max_samples: Maximum number of samples to export
        include_signals: Include V3 signal columns
        
    Returns:
        (num_exported, output_path)
    """
    logger.info(f"Loading results from {results_csv}")
    df = pd.read_csv(results_csv)
    
    if 'uncertainty' not in df.columns:
        raise ValueError("Results CSV must have 'uncertainty' column")
    
    # Filter high-uncertainty samples
    uncertain = df[df['uncertainty'] >= uncertainty_threshold].copy()
    logger.info(f"Found {len(uncertain)} reviews with uncertainty >= {uncertainty_threshold}")
    
    if len(uncertain) == 0:
        logger.warning("No uncertain reviews found!")
        return 0, output_path
    
    # Sort by uncertainty (highest first) and take top N
    uncertain = uncertain.nlargest(max_samples, 'uncertainty')
    
    # Prepare export columns
    export_cols = ['review_id', 'text', 'rating', 'score', 'confidence', 'uncertainty', 'is_actionable']
    
    if include_signals:
        # Add V3 signal columns if available
        signal_cols = [
            'has_concession', 'has_monetization_complaint', 
            'has_retention_signal', 'feature_request_count', 'sentiment_contrast'
        ]
        export_cols.extend([col for col in signal_cols if col in df.columns])
    
    # Add manual_label column (empty for labeling)
    uncertain['manual_label'] = ''
    uncertain['notes'] = ''
    export_cols.extend(['manual_label', 'notes'])
    
    # Export
    export_df = uncertain[[col for col in export_cols if col in uncertain.columns]]
    export_df.to_csv(output_path, index=False)
    
    logger.info(f"✅ Exported {len(export_df)} uncertain reviews to {output_path}")
    logger.info(f"   Uncertainty range: [{export_df['uncertainty'].min():.3f}, {export_df['uncertainty'].max():.3f}]")
    
    return len(export_df), output_path


def import_labeled_samples(labeled_csv: str) -> Tuple[List[Dict], List[bool], List[float]]:
    """
    Import manually labeled samples for retraining.
    
    Args:
        labeled_csv: CSV with 'text', 'rating', 'manual_label' columns
        
    Returns:
        (reviews, labels, sample_weights)
    """
    logger.info(f"Loading labeled samples from {labeled_csv}")
    df = pd.read_csv(labeled_csv)
    
    required_cols = ['text', 'manual_label']
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Filter rows with manual labels
    labeled = df[df['manual_label'].notna() & (df['manual_label'] != '')].copy()
    logger.info(f"Found {len(labeled)} labeled reviews")
    
    if len(labeled) == 0:
        logger.warning("No labeled reviews found!")
        return [], [], []
    
    # Convert to format for training
    reviews = []
    labels = []
    weights = []
    
    for _, row in labeled.iterrows():
        # Parse label (flexible: 1/0, true/false, yes/no, actionable/not)
        label_str = str(row['manual_label']).lower().strip()
        if label_str in ['1', 'true', 'yes', 'actionable']:
            label = True
        elif label_str in ['0', 'false', 'no', 'not actionable', 'not']:
            label = False
        else:
            logger.warning(f"Unknown label '{label_str}', skipping row")
            continue
        
        reviews.append({
            'text': str(row['text']),
            'rating': row.get('rating', 3.0),
            'is_verified': row.get('is_verified', False),
            'version': row.get('reviewCreatedVersion'),
            'device': row.get('device')
        })
        labels.append(label)
        
        # Higher weight for manually labeled data (confident labels)
        weights.append(1.0)
    
    logger.info(f"✅ Loaded {len(reviews)} labeled samples")
    logger.info(f"   Actionable: {sum(labels)} ({sum(labels)/len(labels)*100:.1f}%)")
    logger.info(f"   Non-actionable: {len(labels) - sum(labels)} ({(1 - sum(labels)/len(labels))*100:.1f}%)")
    
    return reviews, labels, weights


def incremental_retrain(
    scorer,
    new_reviews: List[Dict],
    new_labels: List[bool],
    new_weights: List[float],
    existing_train_csv: str = None
) -> Dict[str, float]:
    """
    Incrementally update models with new labeled data.
    
    Args:
        scorer: HybridActionabilityScorer instance
        new_reviews: New review dicts
        new_labels: Labels for new reviews
        new_weights: Sample weights for new reviews
        existing_train_csv: Optional path to existing training data to combine
        
    Returns:
        Training metrics
    """
    from src.domain.entities import Review
    from src.domain.value_objects import ReviewMetadata
    
    logger.info("Starting incremental retraining...")
    
    # Convert to Review entities
    review_entities = []
    for rev_dict in new_reviews:
        metadata = ReviewMetadata(
            rating=int(rev_dict.get('rating', 3.0)),
            review_date=None,
            is_verified=rev_dict.get('is_verified', False),
            version=rev_dict.get('version'),
            device=rev_dict.get('device')
        )
        review = Review(
            id=str(len(review_entities)),
            text=rev_dict['text'],
            metadata=metadata
        )
        review_entities.append(review)
    
    # Combine with existing data if provided
    all_reviews = review_entities
    all_labels = new_labels
    all_weights = np.array(new_weights)
    
    if existing_train_csv and Path(existing_train_csv).exists():
        logger.info(f"Loading existing training data from {existing_train_csv}")
        df_existing = pd.read_csv(existing_train_csv)
        
        for _, row in df_existing.iterrows():
            metadata = ReviewMetadata(
                rating=int(row.get('rating', 3.0)),
                review_date=None,
                is_verified=row.get('is_verified', False),
                version=row.get('reviewCreatedVersion'),
                device=row.get('device')
            )
            review = Review(
                id=str(row.get('reviewId', len(all_reviews))),
                text=str(row['text']),
                metadata=metadata
            )
            all_reviews.append(review)
            all_labels.append(bool(row['label']))
        
        # Existing data gets lower weight (already seen)
        existing_weights = np.full(len(df_existing), 0.5)
        all_weights = np.concatenate([all_weights, existing_weights])
        
        logger.info(f"Combined: {len(new_reviews)} new + {len(df_existing)} existing = {len(all_reviews)} total")
    
    # Train
    logger.info(f"Training on {len(all_reviews)} samples...")
    metrics = scorer.train(all_reviews, all_labels, sample_weights=all_weights)
    
    logger.info("✅ Incremental retraining complete")
    return metrics


def analyze_active_learning_impact(
    old_results_csv: str,
    new_results_csv: str,
    labeled_csv: str
) -> Dict[str, any]:
    """
    Analyze impact of active learning iteration.
    
    Args:
        old_results_csv: Results before retraining
        new_results_csv: Results after retraining
        labeled_csv: Manually labeled samples used for retraining
        
    Returns:
        Impact analysis dict
    """
    df_old = pd.read_csv(old_results_csv)
    df_new = pd.read_csv(new_results_csv)
    df_labeled = pd.read_csv(labeled_csv)
    
    # Extract labeled sample IDs
    labeled_ids = set(df_labeled['review_id'].values)
    
    # Compare predictions on labeled samples
    old_labeled = df_old[df_old['review_id'].isin(labeled_ids)]
    new_labeled = df_new[df_new['review_id'].isin(labeled_ids)]
    
    # Count agreement changes
    old_preds = old_labeled['is_actionable'].values
    new_preds = new_labeled['is_actionable'].values
    
    changes = (old_preds != new_preds).sum()
    
    # Confidence changes
    old_conf = df_old['confidence'].mean()
    new_conf = df_new['confidence'].mean()
    
    # Uncertainty changes
    old_unc = df_old['uncertainty'].mean()
    new_unc = df_new['uncertainty'].mean()
    
    analysis = {
        'labeled_samples': len(labeled_ids),
        'predictions_changed': int(changes),
        'change_rate': float(changes / len(labeled_ids)) if len(labeled_ids) > 0 else 0,
        'old_mean_confidence': float(old_conf),
        'new_mean_confidence': float(new_conf),
        'confidence_change': float(new_conf - old_conf),
        'old_mean_uncertainty': float(old_unc),
        'new_mean_uncertainty': float(new_unc),
        'uncertainty_change': float(new_unc - old_unc)
    }
    
    logger.info("Active Learning Impact Analysis:")
    logger.info(f"  Labeled samples: {analysis['labeled_samples']}")
    logger.info(f"  Predictions changed: {analysis['predictions_changed']} ({analysis['change_rate']*100:.1f}%)")
    logger.info(f"  Mean confidence: {old_conf:.3f} → {new_conf:.3f} ({new_conf-old_conf:+.3f})")
    logger.info(f"  Mean uncertainty: {old_unc:.3f} → {new_unc:.3f} ({new_unc-old_unc:+.3f})")
    
    return analysis
