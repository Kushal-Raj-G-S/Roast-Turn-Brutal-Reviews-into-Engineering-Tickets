"""
Production ML Actionability Scorer
Lightweight, CPU-efficient model with online learning capability.
Uses ensemble of Logistic Regression + Gradient Boosting.
"""

import logging
import pickle
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from datetime import datetime

from src.domain.entities import Review
from src.domain.value_objects import ActionabilityScore
from src.domain.services import IActionabilityScorer
from .feature_engineering import FeatureExtractor, calculate_sentiment_polarity, detect_mixed_sentiment
from .calibration import ProbabilityCalibrator, evaluate_calibration, CalibrationMetrics
from .observability import ObservabilityTracker

logger = logging.getLogger(__name__)


class HybridActionabilityScorer(IActionabilityScorer):
    """
    Production-ready actionability scorer combining:
    1. Rule-based filtering (fast, interpretable)
    2. ML-based scoring (adaptive, nuanced)
    
    Architecture:
    - SGDClassifier for online learning (incremental updates)
    - GradientBoostingClassifier for high accuracy (batch updates)
    - Ensemble voting for final decision
    - Confidence scoring based on agreement
    
    CPU-Efficient Design:
    - Lightweight feature extraction
    - Small model footprint (~1MB)
    - No GPU dependencies
    - Batch inference optimization
    """
    
    def __init__(
        self,
        threshold: float = 0.5,
        confidence_threshold: float = 0.6,
        model_dir: Optional[str] = None,
        enable_online_learning: bool = True,
        calibration_method: str = "platt",
        uncertainty_threshold: float = 0.3
    ):
        """
        Initialize hybrid scorer.
        
        Args:
            threshold: Minimum score to classify as actionable (0-1)
            confidence_threshold: Minimum confidence to trust ML prediction
            model_dir: Directory to save/load trained models
            enable_online_learning: Enable incremental model updates
            calibration_method: Probability calibration ("platt", "isotonic", or "none")
            uncertainty_threshold: Threshold for flagging high uncertainty (0-1)
        """
        self.threshold = threshold
        self.confidence_threshold = confidence_threshold
        self.enable_online_learning = enable_online_learning
        self.calibration_method = calibration_method
        self.uncertainty_threshold = uncertainty_threshold
        
        # Feature extraction
        self.feature_extractor = FeatureExtractor()
        self.scaler = StandardScaler()
        
        # Online learning model (SGD Logistic Regression)
        self.online_model = SGDClassifier(
            loss='log_loss',  # Logistic regression
            penalty='l2',
            alpha=0.0001,
            max_iter=1000,
            tol=1e-3,
            random_state=42,
            warm_start=True,  # Enable incremental learning
            n_jobs=1  # Single-threaded for consistency
        )
        
        # Batch learning model (Gradient Boosting)
        self.batch_model = GradientBoostingClassifier(
            n_estimators=50,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42
        )
        
        # Probability calibration
        self.online_calibrator = ProbabilityCalibrator(method=calibration_method)
        self.batch_calibrator = ProbabilityCalibrator(method=calibration_method)
        self.calibrators_fitted = False
        
        # Model state
        self.is_trained = False
        self.online_model_trained = False
        self.batch_model_trained = False
        self.scaler_fitted = False
        
        # Training statistics
        self.training_samples = 0
        self.online_updates = 0
        self.last_trained = None
        
        # Model directory setup
        self.model_dir = Path(model_dir) if model_dir else Path("./models/actionability")
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        # V3: Observability tracker
        self.tracker = ObservabilityTracker()
        
        # Load pre-trained models if available
        self._load_models()
    
    def score(self, review: Review) -> ActionabilityScore:
        """
        Score a single review for actionability with calibrated confidence and uncertainty.
        Combines rule-based and ML-based approaches.
        """
        import time
        
        start_time = time.time()
        
        # Extract features
        feature_start = time.time()
        features = self.feature_extractor.extract(
            text=review.text,
            rating=review.metadata.rating,
            is_verified=review.metadata.is_verified,
            version=review.metadata.version,
            device=review.metadata.device
        )
        feature_time = (time.time() - feature_start) * 1000  # ms
        self.tracker.latency_metrics.add('feature_extraction', feature_time)
        
        # Rule-based filtering (fast path)
        rule_start = time.time()
        rule_based_actionable, rule_confidence = self._rule_based_score(features, review.text)
        rule_time = (time.time() - rule_start) * 1000  # ms
        self.tracker.latency_metrics.add('rule_scoring', rule_time)
        
        # If rules are very confident, use them
        if rule_confidence > 0.9:
            score = 1.0 if rule_based_actionable else 0.0
            uncertainty = 1.0 - rule_confidence
            
            # Track prediction
            self.tracker.record_prediction(
                score=score,
                confidence=rule_confidence,
                uncertainty=uncertainty,
                is_actionable=rule_based_actionable,
                has_concession=features.has_concession,
                has_monetization_complaint=features.has_monetization_complaint,
                has_retention_signal=features.has_retention_signal,
                feature_request_count=features.feature_request_count
            )
            
            total_time = (time.time() - start_time) * 1000
            self.tracker.latency_metrics.add('total', total_time)
            
            return ActionabilityScore(
                score=score,
                confidence=rule_confidence,
                is_actionable=rule_based_actionable,
                features={
                    'explanation': self._explain_score(features, rule_based_actionable),
                    'uncertainty': uncertainty,
                    'source': 'rule_based'
                }
            )
        
        # ML-based scoring (if model trained)
        if self.is_trained:
            ml_start = time.time()
            ml_score, ml_confidence, ml_uncertainty = self._ml_score(features)
            ml_time = (time.time() - ml_start) * 1000  # ms
            self.tracker.latency_metrics.add('ml_scoring', ml_time)
            
            # Ensemble: combine rule-based and ML
            if self.online_model_trained and self.batch_model_trained:
                # Weighted average (ML gets more weight if confident)
                weight_ml = ml_confidence
                weight_rule = 1 - ml_confidence
                final_score = (ml_score * weight_ml + (1.0 if rule_based_actionable else 0.0) * weight_rule) / (weight_ml + weight_rule)
                final_confidence = (ml_confidence + rule_confidence) / 2
                final_uncertainty = (ml_uncertainty + (1.0 - rule_confidence)) / 2
            else:
                final_score = ml_score
                final_confidence = ml_confidence
                final_uncertainty = ml_uncertainty
            
            is_actionable = final_score >= self.threshold
            
            # Track prediction
            self.tracker.record_prediction(
                score=final_score,
                confidence=final_confidence,
                uncertainty=final_uncertainty,
                is_actionable=is_actionable,
                has_concession=features.has_concession,
                has_monetization_complaint=features.has_monetization_complaint,
                has_retention_signal=features.has_retention_signal,
                feature_request_count=features.feature_request_count
            )
            
            total_time = (time.time() - start_time) * 1000
            self.tracker.latency_metrics.add('total', total_time)
            
            # Log summary periodically (every 5 minutes)
            self.tracker.log_summary(interval_seconds=300)
            
            return ActionabilityScore(
                score=float(final_score),
                confidence=float(final_confidence),
                is_actionable=is_actionable,
                features={
                    'explanation': self._explain_score(features, is_actionable),
                    'uncertainty': float(final_uncertainty),
                    'high_uncertainty': final_uncertainty >= self.uncertainty_threshold,
                    'source': 'ensemble'
                }
            )
            
            return ActionabilityScore(
                score=final_score,
                confidence=final_confidence,
                is_actionable=is_actionable,
                features={'explanation': self._explain_score(features, is_actionable)}
            )
        
        # Fallback to rule-based only
        score = 1.0 if rule_based_actionable else 0.0
        return ActionabilityScore(
            score=score,
            confidence=rule_confidence,
            is_actionable=rule_based_actionable,
            features={'explanation': self._explain_score(features, rule_based_actionable)}
        )
    
    def score_batch(self, reviews: List[Review]) -> List[ActionabilityScore]:
        """
        Score multiple reviews efficiently.
        Optimized for batch processing.
        """
        if not reviews:
            return []
        
        # Extract features in batch
        feature_dicts = [
            {
                'text': r.text,
                'rating': r.metadata.rating,
                'is_verified': r.metadata.is_verified,
                'version': r.metadata.version,
                'device': r.metadata.device
            }
            for r in reviews
        ]
        
        features_array = self.feature_extractor.extract_batch(feature_dicts)
        
        # Get rule-based scores
        rule_scores = np.array([
            self._rule_based_score_fast(reviews[i].text, features_array[i])
            for i in range(len(reviews))
        ])
        
        # Get ML scores if model trained
        if self.is_trained and len(features_array) > 0:
            features_scaled = self.scaler.transform(features_array)
            
            ml_scores = np.zeros(len(reviews))
            ml_confidences = np.zeros(len(reviews))
            
            # Online model predictions
            if self.online_model_trained:
                online_probs = self.online_model.predict_proba(features_scaled)[:, 1]
                ml_scores += online_probs * 0.4
                ml_confidences += 0.4
            
            # Batch model predictions
            if self.batch_model_trained:
                batch_probs = self.batch_model.predict_proba(features_scaled)[:, 1]
                ml_scores += batch_probs * 0.6
                ml_confidences += 0.6
            
            # Normalize
            if ml_confidences[0] > 0:
                ml_scores /= ml_confidences
                ml_confidences = np.clip(ml_confidences, 0, 1)
            
            # Ensemble with rule-based
            final_scores = (ml_scores + rule_scores) / 2
            final_confidences = ml_confidences * 0.7 + 0.3  # Boost confidence
        else:
            final_scores = rule_scores
            final_confidences = np.full(len(reviews), 0.7)
        
        # Create ActionabilityScore objects
        results = []
        for i, review in enumerate(reviews):
            is_actionable = final_scores[i] >= self.threshold
            features = self.feature_extractor.extract(
                text=review.text,
                rating=review.metadata.rating
            )
            
            results.append(ActionabilityScore(
                score=float(final_scores[i]),
                confidence=float(final_confidences[i]),
                is_actionable=is_actionable,
                features={'explanation': self._explain_score(features, is_actionable)}
            ))
        
        return results
    
    def _rule_based_score(self, features, text: str) -> Tuple[bool, float]:
        """
        Rule-based actionability scoring.
        Returns (is_actionable, confidence)
        """
        confidence = 0.7  # Default confidence for rules
        
        # Strong negative signals (high confidence actionable)
        if features.rating <= 2.0 and features.complaint_verbs > 0:
            return True, 0.95
        
        if features.has_bug_keywords and features.has_specific_details:
            return True, 0.9
        
        if features.complaint_verbs >= 2 and features.negative_words >= 3:
            return True, 0.85
        
        # Mixed sentiment (usually actionable)
        if detect_mixed_sentiment(text):
            return True, 0.75
        
        # Strong feature request
        if features.has_feature_request and features.has_specific_details:
            return True, 0.8
        
        # Weak signals (low confidence non-actionable)
        if features.rating >= 4.0 and features.negative_words == 0 and features.word_count < 10:
            return False, 0.85
        
        if features.word_count < 5 or features.length < 20:
            return False, 0.8
        
        # Default: uncertain
        polarity = calculate_sentiment_polarity(text)
        if polarity < -0.3:
            return True, 0.6
        elif polarity > 0.3:
            return False, 0.6
        
        return True, 0.5  # Neutral = keep for analysis
    
    def _rule_based_score_fast(self, text: str, features_array: np.ndarray) -> float:
        """Fast rule-based scoring for batch processing."""
        rating = features_array[16]
        complaint_verbs = features_array[6]
        negative_words = features_array[5]
        word_count = features_array[1]
        
        if rating <= 2.0 and complaint_verbs > 0:
            return 1.0
        if word_count < 5:
            return 0.0
        if negative_words >= 3:
            return 0.9
        if rating >= 4.0 and negative_words == 0:
            return 0.2
        
        return 0.5
    
    def _ml_score(self, features) -> Tuple[float, float, float]:
        """
        ML-based scoring with calibrated probabilities and ensemble uncertainty.
        Returns (score, confidence, uncertainty)
        """
        features_array = features.to_array().reshape(1, -1)
        features_scaled = self.scaler.transform(features_array)
        
        scores = []
        uncalibrated_probs = []
        
        # Online model
        if self.online_model_trained:
            online_prob = self.online_model.predict_proba(features_scaled)[0, 1]
            uncalibrated_probs.append(online_prob)
            
            # Apply calibration if fitted
            if self.calibrators_fitted and self.calibration_method != "none":
                online_prob = self.online_calibrator.transform(np.array([online_prob]))[0]
            
            scores.append(online_prob)
        
        # Batch model
        if self.batch_model_trained:
            batch_prob = self.batch_model.predict_proba(features_scaled)[0, 1]
            uncalibrated_probs.append(batch_prob)
            
            # Apply calibration if fitted
            if self.calibrators_fitted and self.calibration_method != "none":
                batch_prob = self.batch_calibrator.transform(np.array([batch_prob]))[0]
            
            scores.append(batch_prob)
        
        if not scores:
            return 0.5, 0.3, 0.7  # No model trained
        
        # Ensemble scoring: weighted average
        if len(scores) == 2:
            final_score = 0.4 * scores[0] + 0.6 * scores[1]  # Favor batch model
        else:
            final_score = scores[0]
        
        # Compute uncertainty based on ensemble disagreement
        if len(scores) >= 2:
            # Variance-based uncertainty
            disagreement = np.var(scores)
            # Normalize to [0, 1] (max variance for binary is 0.25)
            uncertainty = min(1.0, disagreement * 4.0)
        else:
            # Single model: use distance from decision boundary as proxy
            uncertainty = 1.0 - abs(2 * final_score - 1)
        
        # V3: Boost uncertainty for mixed sentiment and subtle signals
        mixed_sentiment_boost = 0.0
        if features.has_concession or features.sentiment_contrast > 0.05:
            # Concessions and sentiment contrast suggest ambiguity
            mixed_sentiment_boost += 0.15
        if features.has_monetization_complaint or features.has_retention_signal:
            # High-impact signals increase importance of correct classification
            mixed_sentiment_boost += 0.1
        
        # Apply boost but cap uncertainty at 1.0
        uncertainty = min(1.0, uncertainty + mixed_sentiment_boost)
        
        # Confidence is inverse of uncertainty, adjusted
        base_confidence = 1.0 - uncertainty
        
        # Boost confidence if models agree strongly
        if len(scores) >= 2:
            agreement = 1.0 - abs(scores[0] - scores[1])
            confidence = base_confidence * 0.6 + agreement * 0.4
        else:
            confidence = base_confidence
        
        # Ensure confidence is in reasonable range
        confidence = np.clip(confidence, 0.3, 0.99)
        
        return float(final_score), float(confidence), float(uncertainty)
    
    def _explain_score(self, features, is_actionable: bool) -> List[str]:
        """Generate human-readable explanation."""
        reasons = []
        
        if is_actionable:
            if features.rating <= 2.0:
                reasons.append("Low rating indicates dissatisfaction")
            if features.complaint_verbs > 0:
                reasons.append("Contains complaint language")
            if features.has_bug_keywords:
                reasons.append("Mentions bugs or errors")
            if features.has_specific_details:
                reasons.append("Provides specific technical details")
            if features.negative_words >= 3:
                reasons.append("Strong negative sentiment")
            # V3: New signals
            if features.has_retention_signal:
                reasons.append("⚠️ Contains retention risk signal (uninstall/leaving)")
            if features.has_monetization_complaint:
                reasons.append("💰 Contains monetization complaint")
            if features.feature_request_count > 0:
                reasons.append(f"📝 Contains {features.feature_request_count} feature request(s)")
            if features.has_concession and features.sentiment_contrast > 0:
                reasons.append("⚖️ Mixed sentiment detected (positive + negative)")
        else:
            if features.rating >= 4.0:
                reasons.append("High rating indicates satisfaction")
            if features.word_count < 5:
                reasons.append("Too short for meaningful analysis")
            if features.positive_words > features.negative_words:
                reasons.append("Predominantly positive sentiment")
        
        return reasons if reasons else ["Default classification"]
    
    def train(
        self,
        reviews: List[Review],
        labels: List[bool],
        sample_weights: Optional[np.ndarray] = None,
        val_reviews: Optional[List[Review]] = None,
        val_labels: Optional[List[bool]] = None
    ) -> Dict[str, float]:
        """
        Train models on labeled data with optional sample weights and calibration.
        
        Args:
            reviews: List of Review entities for training
            labels: List of boolean labels (True = actionable)
            sample_weights: Optional weights for each sample (for uncertain labels)
            val_reviews: Optional validation set for calibration
            val_labels: Optional validation labels
            
        Returns:
            Training metrics including calibration metrics
        """
        if len(reviews) != len(labels):
            raise ValueError("Reviews and labels must have same length")
        
        if sample_weights is not None and len(sample_weights) != len(labels):
            raise ValueError("Sample weights must match labels length")
        
        logger.info(f"Training actionability scorer on {len(reviews)} samples")
        if sample_weights is not None:
            logger.info(f"Using sample weights: min={sample_weights.min():.2f}, max={sample_weights.max():.2f}, mean={sample_weights.mean():.2f}")
        
        # Extract features
        feature_dicts = [
            {
                'text': r.text,
                'rating': r.metadata.rating,
                'is_verified': r.metadata.is_verified,
                'version': r.metadata.version,
                'device': r.metadata.device
            }
            for r in reviews
        ]
        
        X = self.feature_extractor.extract_batch(feature_dicts)
        y = np.array(labels, dtype=int)
        
        # Fit scaler
        if not self.scaler_fitted:
            self.scaler.fit(X)
            self.scaler_fitted = True
        
        X_scaled = self.scaler.transform(X)
        
        # Train online model (SGD) - supports sample weights
        if self.enable_online_learning:
            if sample_weights is not None:
                self.online_model.partial_fit(X_scaled, y, classes=[0, 1], sample_weight=sample_weights)
            else:
                self.online_model.partial_fit(X_scaled, y, classes=[0, 1])
            self.online_model_trained = True
            self.online_updates += 1
        
        # Train batch model (GradientBoosting) - supports sample weights
        if sample_weights is not None:
            self.batch_model.fit(X_scaled, y, sample_weight=sample_weights)
        else:
            self.batch_model.fit(X_scaled, y)
        self.batch_model_trained = True
        
        self.is_trained = True
        self.training_samples += len(reviews)
        self.last_trained = datetime.now()
        
        # Calculate training accuracy
        online_acc = self.online_model.score(X_scaled, y) if self.online_model_trained else 0
        batch_acc = self.batch_model.score(X_scaled, y) if self.batch_model_trained else 0
        
        metrics = {
            'training_samples': len(reviews),
            'total_samples': self.training_samples,
            'online_accuracy': float(online_acc),
            'batch_accuracy': float(batch_acc),
            'online_updates': self.online_updates
        }
        
        # Calibration on validation set
        if val_reviews and val_labels and self.calibration_method != "none":
            logger.info(f"Calibrating probabilities on {len(val_reviews)} validation samples...")
            
            # Extract validation features
            val_feature_dicts = [
                {
                    'text': r.text,
                    'rating': r.metadata.rating,
                    'is_verified': r.metadata.is_verified,
                    'version': r.metadata.version,
                    'device': r.metadata.device
                }
                for r in val_reviews
            ]
            
            X_val = self.feature_extractor.extract_batch(val_feature_dicts)
            X_val_scaled = self.scaler.transform(X_val)
            y_val = np.array(val_labels, dtype=int)
            
            # Get uncalibrated probabilities
            if self.online_model_trained:
                online_probs = self.online_model.predict_proba(X_val_scaled)[:, 1]
                self.online_calibrator.fit(online_probs, y_val)
                
                # Evaluate online calibration
                calib_online_probs = self.online_calibrator.transform(online_probs)
                online_calib_metrics = evaluate_calibration(calib_online_probs, y_val)
                logger.info(f"Online model calibration:\n{online_calib_metrics}")
                
                metrics['online_brier_score'] = online_calib_metrics.brier_score
                metrics['online_ece'] = online_calib_metrics.ece
            
            if self.batch_model_trained:
                batch_probs = self.batch_model.predict_proba(X_val_scaled)[:, 1]
                self.batch_calibrator.fit(batch_probs, y_val)
                
                # Evaluate batch calibration
                calib_batch_probs = self.batch_calibrator.transform(batch_probs)
                batch_calib_metrics = evaluate_calibration(calib_batch_probs, y_val)
                logger.info(f"Batch model calibration:\n{batch_calib_metrics}")
                
                metrics['batch_brier_score'] = batch_calib_metrics.brier_score
                metrics['batch_ece'] = batch_calib_metrics.ece
            
            self.calibrators_fitted = True
            logger.info("✅ Calibration complete")
        else:
            if self.calibration_method != "none":
                logger.warning("No validation set provided. Skipping calibration.")
        
        logger.info(f"Training complete: Online={online_acc:.3f}, Batch={batch_acc:.3f}")
        
        # Save models
        self._save_models()
        
        return metrics
    
    async def train_online(self, reviews: List[Review], labels: List[bool]) -> None:
        """
        Incremental online learning with multiple samples.
        Async wrapper for batch online updates.
        """
        for review, label in zip(reviews, labels):
            self.update_online(review, label)
        
        logger.info(f"Online training updated with {len(reviews)} samples")
    
    def update_online(self, review: Review, label: bool) -> None:
        """
        Incremental online learning update (single sample).
        """
        if not self.enable_online_learning:
            return
        
        features = self.feature_extractor.extract(
            text=review.text,
            rating=review.metadata.rating,
            is_verified=review.metadata.is_verified,
            version=review.metadata.version,
            device=review.metadata.device
        )
        
        X = features.to_array().reshape(1, -1)
        
        if not self.scaler_fitted:
            # Need at least some data to fit scaler
            logger.warning("Scaler not fitted. Need initial training batch first.")
            return
        
        X_scaled = self.scaler.transform(X)
        y = np.array([int(label)])
        
        self.online_model.partial_fit(X_scaled, y, classes=[0, 1])
        self.online_model_trained = True
        self.online_updates += 1
        self.training_samples += 1
        
        # Periodic model save
        if self.online_updates % 100 == 0:
            self._save_models()
            logger.info(f"Online model updated ({self.online_updates} updates)")
    
    def _save_models(self) -> None:
        """Save trained models and calibrators to disk."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save online model
            if self.online_model_trained:
                online_path = self.model_dir / f"online_model_{timestamp}.pkl"
                with open(online_path, 'wb') as f:
                    pickle.dump(self.online_model, f)
                
                # Keep latest symlink
                latest_online = self.model_dir / "online_model_latest.pkl"
                if latest_online.exists():
                    latest_online.unlink()
                with open(latest_online, 'wb') as f:
                    pickle.dump(self.online_model, f)
            
            # Save batch model
            if self.batch_model_trained:
                batch_path = self.model_dir / f"batch_model_{timestamp}.pkl"
                with open(batch_path, 'wb') as f:
                    pickle.dump(self.batch_model, f)
                
                latest_batch = self.model_dir / "batch_model_latest.pkl"
                if latest_batch.exists():
                    latest_batch.unlink()
                with open(latest_batch, 'wb') as f:
                    pickle.dump(self.batch_model, f)
            
            # Save scaler
            if self.scaler_fitted:
                scaler_path = self.model_dir / "scaler_latest.pkl"
                with open(scaler_path, 'wb') as f:
                    pickle.dump(self.scaler, f)
            
            # Save calibrators
            if self.calibrators_fitted:
                online_calib_path = self.model_dir / "online_calibrator_latest.pkl"
                self.online_calibrator.save(online_calib_path)
                
                batch_calib_path = self.model_dir / "batch_calibrator_latest.pkl"
                self.batch_calibrator.save(batch_calib_path)
            
            logger.info(f"Models saved to {self.model_dir}")
            
        except Exception as e:
            logger.error(f"Failed to save models: {e}")
    
    def _load_models(self) -> None:
        """Load pre-trained models and calibrators from disk."""
        try:
            # Load scaler
            scaler_path = self.model_dir / "scaler_latest.pkl"
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                    self.scaler_fitted = True
                logger.info("Loaded scaler")
            
            # Load online model
            online_path = self.model_dir / "online_model_latest.pkl"
            if online_path.exists():
                with open(online_path, 'rb') as f:
                    self.online_model = pickle.load(f)
                    self.online_model_trained = True
                logger.info("Loaded online model")
            
            # Load batch model
            batch_path = self.model_dir / "batch_model_latest.pkl"
            if batch_path.exists():
                with open(batch_path, 'rb') as f:
                    self.batch_model = pickle.load(f)
                    self.batch_model_trained = True
                logger.info("Loaded batch model")
            
            # Load calibrators
            online_calib_path = self.model_dir / "online_calibrator_latest.pkl"
            batch_calib_path = self.model_dir / "batch_calibrator_latest.pkl"
            if online_calib_path.exists() and batch_calib_path.exists():
                self.online_calibrator.load(online_calib_path)
                self.batch_calibrator.load(batch_calib_path)
                self.calibrators_fitted = True
                logger.info("Loaded calibrators")
            
            if self.online_model_trained or self.batch_model_trained:
                self.is_trained = True
                logger.info("✅ Pre-trained models loaded successfully")
            
        except Exception as e:
            logger.warning(f"Could not load pre-trained models: {e}")
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from batch model."""
        if not self.batch_model_trained:
            return {}
        
        from .feature_engineering import FeatureVector
        feature_names = FeatureVector.feature_names()
        importances = self.batch_model.feature_importances_
        
        return dict(zip(feature_names, importances.tolist()))
