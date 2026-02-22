"""
Train Actionability Model V2 - 3-Label Support
CLI tool for training, evaluation, and comparison with ground truth data.
"""

import argparse
import logging
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.domain.entities import Review
from src.domain.value_objects import ReviewMetadata
from src.infrastructure.ml.hybrid_scorer import HybridActionabilityScorer
from src.infrastructure.ml.training_data_generator_v2 import TrainingDataGeneratorV2, prepare_ground_truth_training

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def train_model_v2(
    train_csv: str,
    val_csv: Optional[str] = None,
    model_dir: str = "./models/actionability",
    enable_online_learning: bool = True,
    calibration_method: str = "platt"
) -> Dict[str, float]:
    """
    Train hybrid actionability model with sample weights and calibration.
    
    Args:
        train_csv: Path to training CSV with sample_weight column
        val_csv: Optional validation CSV for calibration
        model_dir: Directory to save trained models
        enable_online_learning: Enable online learning capability
        calibration_method: 'platt', 'isotonic', or 'none'
        
    Returns:
        Training metrics including calibration metrics if validation set provided
    """
    logger.info(f"Loading training data: {train_csv}")
    df = pd.read_csv(train_csv)
    
    # Validate required columns
    required_cols = ['text', 'rating', 'label', 'sample_weight']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Training CSV missing columns: {missing_cols}")
    
    logger.info(f"Training data loaded: {len(df)} samples")
    logger.info(f"  - Label distribution: {df['label'].value_counts().to_dict()}")
    logger.info(f"  - Sample weight range: [{df['sample_weight'].min():.2f}, {df['sample_weight'].max():.2f}]")
    logger.info(f"  - Weighted samples: {df['sample_weight'].sum():.1f}")
    
    # Convert to Review entities
    reviews = []
    for _, row in df.iterrows():
        metadata = ReviewMetadata(
            rating=int(row.get('rating', 3.0)) if pd.notna(row.get('rating')) else None,
            review_date=None,
            is_verified=row.get('is_verified', False),
            version=row.get('reviewCreatedVersion', None),
            device=row.get('device', None)
        )
        
        review = Review(
            id=str(row.get('reviewId', f"train_{_}")),
            text=str(row['text']),
            metadata=metadata
        )
        reviews.append(review)
    
    # Extract labels and sample weights
    labels = df['label'].tolist()
    sample_weights = df['sample_weight'].values
    
    # Load validation data if provided
    val_reviews = None
    val_labels = None
    if val_csv:
        logger.info(f"Loading validation data: {val_csv}")
        val_df = pd.read_csv(val_csv)
        logger.info(f"Validation data loaded: {len(val_df)} samples")
        
        val_reviews = []
        for _, row in val_df.iterrows():
            metadata = ReviewMetadata(
                rating=int(row.get('rating', 3.0)) if pd.notna(row.get('rating')) else None,
                review_date=None,
                is_verified=row.get('is_verified', False),
                version=row.get('reviewCreatedVersion', None),
                device=row.get('device', None)
            )
            
            review = Review(
                id=str(row.get('reviewId', f"val_{_}")),
                text=str(row['text']),
                metadata=metadata
            )
            val_reviews.append(review)
        
        val_labels = val_df['label'].tolist()
    
    # Initialize and train scorer
    logger.info("Initializing hybrid scorer...")
    scorer = HybridActionabilityScorer(
        threshold=0.5,
        confidence_threshold=0.6,
        model_dir=model_dir,
        enable_online_learning=enable_online_learning,
        calibration_method=calibration_method
    )
    
    logger.info("Training models with sample weights...")
    metrics = scorer.train(
        reviews, 
        labels, 
        sample_weights=sample_weights,
        val_reviews=val_reviews,
        val_labels=val_labels
    )
    
    logger.info("Training complete!")
    logger.info(f"  - Online model accuracy: {metrics['online_accuracy']:.3f}")
    logger.info(f"  - Batch model accuracy: {metrics['batch_accuracy']:.3f}")
    logger.info(f"  - Total samples trained: {metrics['total_samples']}")
    
    # Log calibration metrics if available
    if 'online_brier_score' in metrics:
        logger.info(f"  - Online Brier score: {metrics['online_brier_score']:.4f}")
        logger.info(f"  - Online ECE: {metrics['online_ece']:.4f}")
        logger.info(f"  - Batch Brier score: {metrics['batch_brier_score']:.4f}")
        logger.info(f"  - Batch ECE: {metrics['batch_ece']:.4f}")
    
    logger.info(f"  - Models saved to: {model_dir}")
    
    return metrics


def evaluate_model_v2(
    test_csv: str,
    model_dir: str = "./models/actionability",
    show_samples: int = 5
) -> Dict[str, any]:
    """
    Evaluate trained model with enhanced metrics for v2.
    
    Includes:
    - Standard metrics (accuracy, precision, recall, F1)
    - High-rating actionable performance
    - Mixed sentiment detection
    - Confidence calibration
    
    Args:
        test_csv: Path to test CSV
        model_dir: Directory with trained models
        show_samples: Number of sample predictions to show
        
    Returns:
        Evaluation metrics
    """
    logger.info(f"Loading test data: {test_csv}")
    df = pd.read_csv(test_csv)
    
    logger.info(f"Test data loaded: {len(df)} samples")
    logger.info(f"  - Label distribution: {df['label'].value_counts().to_dict()}")
    if 'manual_label' in df.columns:
        logger.info(f"  - Manual label distribution: {df['manual_label'].value_counts().to_dict()}")
    
    # Convert to Review entities
    reviews = []
    for _, row in df.iterrows():
        metadata = ReviewMetadata(
            rating=int(row.get('rating', 3.0)) if pd.notna(row.get('rating')) else None,
            review_date=None,
            is_verified=row.get('is_verified', False),
            version=row.get('reviewCreatedVersion', None),
            device=row.get('device', None)
        )
        
        review = Review(
            id=str(row.get('reviewId', f"test_{_}")),
            text=str(row['text']),
            metadata=metadata
        )
        reviews.append(review)
    
    # Load trained scorer
    logger.info("Loading trained model...")
    scorer = HybridActionabilityScorer(
        threshold=0.5,
        confidence_threshold=0.6,
        model_dir=model_dir,
        enable_online_learning=False
    )
    
    if not scorer.is_trained:
        raise ValueError("No trained model found. Run 'train' command first.")
    
    # Score reviews
    logger.info("Scoring reviews...")
    scores = scorer.score_batch(reviews)
    
    # Extract predictions
    y_true = df['label'].values
    y_pred = np.array([s.is_actionable for s in scores])
    y_score = np.array([s.score for s in scores])
    y_confidence = np.array([s.confidence for s in scores])
    
    # Calculate metrics
    tp = sum((y_true == 1) & (y_pred == 1))
    fp = sum((y_true == 0) & (y_pred == 1))
    tn = sum((y_true == 0) & (y_pred == 0))
    fn = sum((y_true == 1) & (y_pred == 0))
    
    accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    # High-rating actionable performance
    high_rating_mask = df['rating'] >= 4
    high_rating_actionable_mask = high_rating_mask & (y_true == 1)
    
    if high_rating_actionable_mask.sum() > 0:
        hr_recall = sum(y_pred[high_rating_actionable_mask] == 1) / high_rating_actionable_mask.sum()
        hr_avg_confidence = y_confidence[high_rating_actionable_mask].mean()
    else:
        hr_recall = 0
        hr_avg_confidence = 0
    
    # Mixed sentiment detection (if feature available)
    mixed_sentiment_count = 0
    mixed_sentiment_correct = 0
    if 'feature_positive_words' in df.columns and 'feature_negative_words' in df.columns:
        mixed_mask = (df['feature_positive_words'] > 0) & (df['feature_negative_words'] > 0)
        mixed_sentiment_count = mixed_mask.sum()
        if mixed_sentiment_count > 0:
            mixed_sentiment_correct = (y_pred[mixed_mask] == y_true[mixed_mask]).sum()
    
    # Confidence calibration
    high_conf_mask = y_confidence >= 0.8
    high_conf_accuracy = (y_pred[high_conf_mask] == y_true[high_conf_mask]).mean() if high_conf_mask.sum() > 0 else 0
    
    low_conf_mask = y_confidence < 0.6
    low_conf_accuracy = (y_pred[low_conf_mask] == y_true[low_conf_mask]).mean() if low_conf_mask.sum() > 0 else 0
    
    # Metrics summary
    metrics = {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1_score': f1,
        'tp': int(tp),
        'fp': int(fp),
        'tn': int(tn),
        'fn': int(fn),
        'high_rating_actionable_count': int(high_rating_actionable_mask.sum()),
        'high_rating_actionable_recall': hr_recall,
        'high_rating_actionable_avg_confidence': hr_avg_confidence,
        'mixed_sentiment_count': int(mixed_sentiment_count),
        'mixed_sentiment_accuracy': mixed_sentiment_correct / mixed_sentiment_count if mixed_sentiment_count > 0 else 0,
        'high_confidence_samples': int(high_conf_mask.sum()),
        'high_confidence_accuracy': high_conf_accuracy,
        'low_confidence_samples': int(low_conf_mask.sum()),
        'low_confidence_accuracy': low_conf_accuracy,
        'avg_confidence': float(y_confidence.mean())
    }
    
    # Print results
    print("\n" + "="*80)
    print("📊 Model Evaluation Results")
    print("="*80)
    print(f"\n✅ Overall Performance:")
    print(f"  Accuracy:  {accuracy:.1%}")
    print(f"  Precision: {precision:.1%}")
    print(f"  Recall:    {recall:.1%}")
    print(f"  F1 Score:  {f1:.3f}")
    
    print(f"\n📈 Confusion Matrix:")
    print(f"               Predicted")
    print(f"                0     1")
    print(f"  Actual  0   {tn:4d}  {fp:4d}")
    print(f"          1   {fn:4d}  {tp:4d}")
    
    print(f"\n🎯 High-Rating Actionable (Edge Case):")
    print(f"  Total: {metrics['high_rating_actionable_count']} samples")
    print(f"  Recall: {hr_recall:.1%} (detected {int(hr_recall * metrics['high_rating_actionable_count'])}/{metrics['high_rating_actionable_count']})")
    print(f"  Avg Confidence: {hr_avg_confidence:.3f}")
    
    if mixed_sentiment_count > 0:
        print(f"\n🌓 Mixed Sentiment Detection:")
        print(f"  Total: {mixed_sentiment_count} samples")
        print(f"  Accuracy: {metrics['mixed_sentiment_accuracy']:.1%}")
    
    print(f"\n📊 Confidence Calibration:")
    print(f"  High confidence (≥0.8): {metrics['high_confidence_samples']} samples, {high_conf_accuracy:.1%} accuracy")
    print(f"  Low confidence (<0.6): {metrics['low_confidence_samples']} samples, {low_conf_accuracy:.1%} accuracy")
    print(f"  Average confidence: {metrics['avg_confidence']:.3f}")
    
    # Show sample predictions
    if show_samples > 0:
        print(f"\n📝 Sample Predictions (showing {show_samples}):")
        print("="*80)
        
        # Show diverse samples: correct, incorrect, high-rating actionable, mixed sentiment
        sample_indices = []
        
        # Correct predictions
        correct_mask = y_pred == y_true
        if correct_mask.sum() > 0:
            sample_indices.extend(np.where(correct_mask)[0][:2].tolist())
        
        # Incorrect predictions
        incorrect_mask = y_pred != y_true
        if incorrect_mask.sum() > 0:
            sample_indices.extend(np.where(incorrect_mask)[0][:1].tolist())
        
        # High-rating actionable
        if high_rating_actionable_mask.sum() > 0:
            sample_indices.extend(np.where(high_rating_actionable_mask)[0][:2].tolist())
        
        # Limit to requested samples
        sample_indices = list(set(sample_indices))[:show_samples]
        
        for idx in sample_indices:
            print(f"\n[{idx+1}] {'✓' if y_pred[idx] == y_true[idx] else '✗'} Score: {y_score[idx]:.3f} | Confidence: {y_confidence[idx]:.3f}")
            print(f"    Rating: {df.iloc[idx]['rating']} | True: {y_true[idx]} | Predicted: {y_pred[idx]}")
            if 'manual_label' in df.columns:
                print(f"    Manual Label: {df.iloc[idx]['manual_label']}")
            print(f"    Text: {df.iloc[idx]['text'][:120]}...")
            print(f"    Reason: {scores[idx].features.get('explanation', ['N/A'])[0]}")
    
    print("\n" + "="*80)
    
    return metrics


def compare_models(
    test_csv: str,
    old_model_dir: str,
    new_model_dir: str,
    output_path: Optional[str] = None
) -> Dict:
    """
    Compare two models on the same test set.
    
    Args:
        test_csv: Path to test CSV
        old_model_dir: Directory with old trained model
        new_model_dir: Directory with new trained model
        output_path: Optional path to save comparison report
        
    Returns:
        Comparison metrics
    """
    logger.info("Comparing old vs new model...")
    
    # Evaluate old model
    logger.info("\n=== Old Model ===")
    old_metrics = evaluate_model_v2(test_csv, old_model_dir, show_samples=0)
    
    # Evaluate new model
    logger.info("\n=== New Model ===")
    new_metrics = evaluate_model_v2(test_csv, new_model_dir, show_samples=0)
    
    # Calculate improvements
    comparison = {
        'old_model': old_metrics,
        'new_model': new_metrics,
        'improvements': {
            'accuracy': new_metrics['accuracy'] - old_metrics['accuracy'],
            'precision': new_metrics['precision'] - old_metrics['precision'],
            'recall': new_metrics['recall'] - old_metrics['recall'],
            'f1_score': new_metrics['f1_score'] - old_metrics['f1_score'],
            'high_rating_actionable_recall': new_metrics['high_rating_actionable_recall'] - old_metrics['high_rating_actionable_recall'],
            'confidence_calibration': new_metrics['high_confidence_accuracy'] - old_metrics['high_confidence_accuracy']
        }
    }
    
    # Print comparison
    print("\n" + "="*80)
    print("🔍 Model Comparison Report")
    print("="*80)
    
    print(f"\n📊 Performance Comparison:")
    print(f"{'Metric':<30} {'Old':<12} {'New':<12} {'Change':<12}")
    print("-" * 66)
    
    for metric in ['accuracy', 'precision', 'recall', 'f1_score']:
        old_val = old_metrics[metric]
        new_val = new_metrics[metric]
        change = comparison['improvements'][metric]
        change_str = f"{change:+.1%}" if abs(change) >= 0.01 else "~"
        print(f"{metric.replace('_', ' ').title():<30} {old_val:.1%}       {new_val:.1%}       {change_str}")
    
    print(f"\n🎯 Edge Case Performance:")
    print(f"{'Metric':<30} {'Old':<12} {'New':<12} {'Change':<12}")
    print("-" * 66)
    
    old_hr = old_metrics['high_rating_actionable_recall']
    new_hr = new_metrics['high_rating_actionable_recall']
    hr_change = comparison['improvements']['high_rating_actionable_recall']
    hr_change_str = f"{hr_change:+.1%}" if abs(hr_change) >= 0.01 else "~"
    print(f"{'High-Rating Actionable Recall':<30} {old_hr:.1%}       {new_hr:.1%}       {hr_change_str}")
    
    print(f"\n📊 Confidence Calibration:")
    print(f"{'Metric':<30} {'Old':<12} {'New':<12} {'Change':<12}")
    print("-" * 66)
    
    old_calib = old_metrics['high_confidence_accuracy']
    new_calib = new_metrics['high_confidence_accuracy']
    calib_change = comparison['improvements']['confidence_calibration']
    calib_change_str = f"{calib_change:+.1%}" if abs(calib_change) >= 0.01 else "~"
    print(f"{'High Confidence Accuracy':<30} {old_calib:.1%}       {new_calib:.1%}       {calib_change_str}")
    
    print("\n" + "="*80)
    
    # Save report
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(comparison, f, indent=2, default=str)
        logger.info(f"Comparison report saved to: {output_path}")
    
    return comparison


def main():
    parser = argparse.ArgumentParser(description="Train and evaluate actionability model v2")
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Prepare command
    prepare_parser = subparsers.add_parser('prepare', help='Prepare ground truth training data')
    prepare_parser.add_argument('ground_truth_csv', help='Path to ground truth CSV with manual labels')
    prepare_parser.add_argument('--output-dir', default='./data/training', help='Output directory')
    prepare_parser.add_argument('--test-size', type=float, default=0.2, help='Test set fraction')
    
    # Train command
    train_parser = subparsers.add_parser('train', help='Train model on prepared data')
    train_parser.add_argument('train_csv', help='Path to training CSV')
    train_parser.add_argument('--val-csv', help='Path to validation CSV for calibration')
    train_parser.add_argument('--model-dir', default='./models/actionability', help='Model directory')
    train_parser.add_argument('--no-online-learning', action='store_true', help='Disable online learning')
    train_parser.add_argument('--calibration-method', choices=['platt', 'isotonic', 'none'], default='platt',
                             help='Calibration method (requires --val-csv)')
    
    # Evaluate command
    eval_parser = subparsers.add_parser('evaluate', help='Evaluate trained model')
    eval_parser.add_argument('test_csv', help='Path to test CSV')
    eval_parser.add_argument('--model-dir', default='./models/actionability', help='Model directory')
    eval_parser.add_argument('--samples', type=int, default=5, help='Number of sample predictions')
    
    # Compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two models')
    compare_parser.add_argument('test_csv', help='Path to test CSV')
    compare_parser.add_argument('--old-model', required=True, help='Old model directory')
    compare_parser.add_argument('--new-model', required=True, help='New model directory')
    compare_parser.add_argument('--output', help='Output path for comparison report')
    
    # Active learning commands (V3)
    al_parser = subparsers.add_parser('active-learning', help='Active learning workflow')
    al_subparsers = al_parser.add_subparsers(dest='al_command', help='Active learning command')
    
    # Export uncertain samples
    export_parser = al_subparsers.add_parser('export', help='Export high-uncertainty reviews for labeling')
    export_parser.add_argument('results_csv', help='Path to scoring results CSV')
    export_parser.add_argument('--output', default='uncertain_samples.csv', help='Output CSV path')
    export_parser.add_argument('--threshold', type=float, default=0.3, help='Uncertainty threshold')
    export_parser.add_argument('--max-samples', type=int, default=100, help='Max samples to export')
    
    # Retrain with labeled samples
    retrain_parser = al_subparsers.add_parser('retrain', help='Retrain with manually labeled samples')
    retrain_parser.add_argument('labeled_csv', help='CSV with manual labels')
    retrain_parser.add_argument('--model-dir', default='./models/actionability', help='Model directory')
    retrain_parser.add_argument('--existing-train', help='Existing training CSV to combine with')
    
    args = parser.parse_args()
    
    if args.command == 'prepare':
        train_path, test_path, stats = prepare_ground_truth_training(
            args.ground_truth_csv,
            output_dir=args.output_dir,
            test_size=args.test_size
        )
        print(f"\n✅ Training data prepared!")
        print(f"   Training set: {train_path}")
        print(f"   Test set: {test_path}")
        print(f"   Statistics: {stats}")
    
    elif args.command == 'train':
        metrics = train_model_v2(
            args.train_csv,
            val_csv=args.val_csv,
            model_dir=args.model_dir,
            enable_online_learning=not args.no_online_learning,
            calibration_method=args.calibration_method
        )
        print(f"\n✅ Training complete! Metrics: {metrics}")
    
    elif args.command == 'evaluate':
        metrics = evaluate_model_v2(
            args.test_csv,
            model_dir=args.model_dir,
            show_samples=args.samples
        )
    
    elif args.command == 'compare':
        comparison = compare_models(
            args.test_csv,
            old_model_dir=args.old_model,
            new_model_dir=args.new_model,
            output_path=args.output
        )
    
    elif args.command == 'active-learning':
        from src.infrastructure.ml.active_learning import (
            export_uncertain_reviews, import_labeled_samples, incremental_retrain
        )
        
        if args.al_command == 'export':
            num_exported, output_path = export_uncertain_reviews(
                args.results_csv,
                args.output,
                uncertainty_threshold=args.threshold,
                max_samples=args.max_samples
            )
            print(f"\n✅ Exported {num_exported} uncertain reviews to {output_path}")
            print(f"   Please label the 'manual_label' column (1/0, true/false, actionable/not)")
        
        elif args.al_command == 'retrain':
            # Import labeled samples
            reviews, labels, weights = import_labeled_samples(args.labeled_csv)
            
            if len(reviews) == 0:
                print("❌ No labeled samples found!")
                return
            
            # Load scorer
            scorer = HybridActionabilityScorer(model_dir=args.model_dir)
            
            # Incremental retrain
            metrics = incremental_retrain(
                scorer,
                reviews,
                labels,
                weights,
                existing_train_csv=args.existing_train
            )
            
            print(f"\n✅ Incremental retraining complete!")
            print(f"   Online accuracy: {metrics['online_accuracy']:.3f}")
            print(f"   Batch accuracy: {metrics['batch_accuracy']:.3f}")
        
        else:
            al_parser.print_help()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
