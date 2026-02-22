"""
CLI Tool for Training and Testing Actionability Scorer
Usage:
    python -m src.infrastructure.ml.train_model --help
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.infrastructure.ml.training_data_generator import prepare_training_data, TrainingDataGenerator
from src.infrastructure.ml.hybrid_scorer import HybridActionabilityScorer
from src.domain.entities import Review
from src.domain.value_objects import ReviewMetadata
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def generate_training_data(args):
    """Generate labeled training data from CSV files."""
    logger.info("=" * 80)
    logger.info("GENERATING TRAINING DATA")
    logger.info("=" * 80)
    
    csv_paths = args.csv_files
    output_dir = args.output_dir
    min_confidence = args.min_confidence
    balance = not args.no_balance
    max_samples = args.max_samples
    
    logger.info(f"Input files: {len(csv_paths)} CSV(s)")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Min confidence: {min_confidence}")
    logger.info(f"Balance classes: {balance}")
    logger.info(f"Max samples: {max_samples or 'unlimited'}")
    
    try:
        train_path, test_path, stats = prepare_training_data(
            csv_paths=csv_paths,
            output_dir=output_dir,
            min_confidence=min_confidence,
            balance=balance,
            max_samples=max_samples
        )
        
        logger.info("=" * 80)
        logger.info("SUCCESS!")
        logger.info(f"Training data: {train_path}")
        logger.info(f"Test data: {test_path}")
        logger.info(f"Statistics: {stats}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Failed to generate training data: {e}", exc_info=True)
        sys.exit(1)


def train_model(args):
    """Train the actionability scorer model."""
    logger.info("=" * 80)
    logger.info("TRAINING ACTIONABILITY SCORER")
    logger.info("=" * 80)
    
    train_csv = args.train_csv
    model_dir = args.model_dir
    
    logger.info(f"Training data: {train_csv}")
    logger.info(f"Model directory: {model_dir}")
    
    try:
        # Load training data
        df = pd.read_csv(train_csv)
        logger.info(f"Loaded {len(df)} training samples")
        
        # Convert to Review entities
        reviews = []
        labels = []
        
        for _, row in df.iterrows():
            metadata = ReviewMetadata(
                rating=row.get('score', row.get('rating')),
                version=row.get('version'),
                device=row.get('device'),
                is_verified=row.get('is_verified', False)
            )
            
            review = Review(
                id=None,
                text=str(row.get('text', row.get('content', ''))),
                metadata=metadata,
                tenant_id=None
            )
            
            reviews.append(review)
            labels.append(bool(row['label']))
        
        # Initialize scorer
        scorer = HybridActionabilityScorer(
            model_dir=model_dir,
            enable_online_learning=True
        )
        
        # Train
        logger.info("Training models...")
        metrics = scorer.train(reviews, labels)
        
        logger.info("=" * 80)
        logger.info("TRAINING COMPLETE!")
        logger.info(f"Samples trained: {metrics['training_samples']}")
        logger.info(f"Online model accuracy: {metrics['online_accuracy']:.3f}")
        logger.info(f"Batch model accuracy: {metrics['batch_accuracy']:.3f}")
        logger.info(f"Models saved to: {model_dir}")
        logger.info("=" * 80)
        
        # Show feature importance
        importance = scorer.get_feature_importance()
        if importance:
            logger.info("\nTop 10 Important Features:")
            sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
            for i, (feature, value) in enumerate(sorted_features, 1):
                logger.info(f"  {i}. {feature}: {value:.4f}")
        
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        sys.exit(1)


def evaluate_model(args):
    """Evaluate model on test data."""
    logger.info("=" * 80)
    logger.info("EVALUATING MODEL")
    logger.info("=" * 80)
    
    test_csv = args.test_csv
    model_dir = args.model_dir
    
    logger.info(f"Test data: {test_csv}")
    logger.info(f"Model directory: {model_dir}")
    
    try:
        # Load test data
        df = pd.read_csv(test_csv)
        logger.info(f"Loaded {len(df)} test samples")
        
        # Convert to Review entities
        reviews = []
        true_labels = []
        
        for _, row in df.iterrows():
            metadata = ReviewMetadata(
                rating=row.get('score', row.get('rating')),
                version=row.get('version'),
                device=row.get('device'),
                is_verified=row.get('is_verified', False)
            )
            
            review = Review(
                id=None,
                text=str(row.get('text', row.get('content', ''))),
                metadata=metadata,
                tenant_id=None
            )
            
            reviews.append(review)
            true_labels.append(bool(row['label']))
        
        # Load scorer
        scorer = HybridActionabilityScorer(model_dir=model_dir)
        
        if not scorer.is_trained:
            logger.error("No trained model found! Train model first.")
            sys.exit(1)
        
        # Predict
        logger.info("Scoring reviews...")
        scores = scorer.score_batch(reviews)
        
        predictions = [s.is_actionable for s in scores]
        confidences = [s.confidence for s in scores]
        
        # Calculate metrics
        correct = sum(1 for p, t in zip(predictions, true_labels) if p == t)
        accuracy = correct / len(true_labels)
        
        true_pos = sum(1 for p, t in zip(predictions, true_labels) if p and t)
        false_pos = sum(1 for p, t in zip(predictions, true_labels) if p and not t)
        false_neg = sum(1 for p, t in zip(predictions, true_labels) if not p and t)
        true_neg = sum(1 for p, t in zip(predictions, true_labels) if not p and not t)
        
        precision = true_pos / (true_pos + false_pos) if (true_pos + false_pos) > 0 else 0
        recall = true_pos / (true_pos + false_neg) if (true_pos + false_neg) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        avg_confidence = sum(confidences) / len(confidences)
        
        logger.info("=" * 80)
        logger.info("EVALUATION RESULTS")
        logger.info("=" * 80)
        logger.info(f"Test samples: {len(true_labels)}")
        logger.info(f"Accuracy: {accuracy:.3f}")
        logger.info(f"Precision: {precision:.3f}")
        logger.info(f"Recall: {recall:.3f}")
        logger.info(f"F1 Score: {f1:.3f}")
        logger.info(f"Avg Confidence: {avg_confidence:.3f}")
        logger.info("")
        logger.info("Confusion Matrix:")
        logger.info(f"  True Positives:  {true_pos}")
        logger.info(f"  False Positives: {false_pos}")
        logger.info(f"  True Negatives:  {true_neg}")
        logger.info(f"  False Negatives: {false_neg}")
        logger.info("=" * 80)
        
        # Show some examples
        logger.info("\nSample Predictions:")
        for i in range(min(5, len(reviews))):
            logger.info(f"\n[{i+1}] Text: {reviews[i].text[:100]}...")
            logger.info(f"    True: {'Actionable' if true_labels[i] else 'Not Actionable'}")
            logger.info(f"    Predicted: {'Actionable' if predictions[i] else 'Not Actionable'} (confidence: {confidences[i]:.3f})")
            logger.info(f"    Explanation: {scores[i].features.get('explanation', [])}")
        
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Train and evaluate actionability scorer")
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Generate data command
    gen_parser = subparsers.add_parser('generate', help='Generate training data from CSV')
    gen_parser.add_argument('csv_files', nargs='+', help='Input CSV files')
    gen_parser.add_argument('--output-dir', default='./data/training', help='Output directory')
    gen_parser.add_argument('--min-confidence', type=float, default=0.7, help='Minimum confidence for filtering')
    gen_parser.add_argument('--no-balance', action='store_true', help='Do not balance classes')
    gen_parser.add_argument('--max-samples', type=int, help='Maximum samples to use')
    
    # Train command
    train_parser = subparsers.add_parser('train', help='Train the model')
    train_parser.add_argument('train_csv', help='Training data CSV')
    train_parser.add_argument('--model-dir', default='./models/actionability', help='Model directory')
    
    # Evaluate command
    eval_parser = subparsers.add_parser('evaluate', help='Evaluate the model')
    eval_parser.add_argument('test_csv', help='Test data CSV')
    eval_parser.add_argument('--model-dir', default='./models/actionability', help='Model directory')
    
    args = parser.parse_args()
    
    if args.command == 'generate':
        generate_training_data(args)
    elif args.command == 'train':
        train_model(args)
    elif args.command == 'evaluate':
        evaluate_model(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
