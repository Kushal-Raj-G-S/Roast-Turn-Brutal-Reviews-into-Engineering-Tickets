"""
Actionability Scorer - ML-based review filtering
Uses lightweight models with online learning capability.
"""

import logging
import re
from typing import List, Dict, Optional
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
import pickle
import os

from ...domain.entities import Review
from ...domain.value_objects import ActionabilityScore
from ...domain.services import IActionabilityScorer

logger = logging.getLogger(__name__)


class MLActionabilityScorer(IActionabilityScorer):
    """
    Machine Learning-based actionability scorer.
    
    Features:
    - Text features (TF-IDF, length, keywords)
    - Metadata features (rating, verified)
    - Online learning capability
    - Feature importance tracking
    
    Model: Random Forest (CPU-friendly, interpretable)
    """

    def __init__(
        self,
        threshold: float = 0.5,
        model_path: Optional[str] = None
    ):
        self.threshold = threshold
        self.model_path = model_path
        
        # ML components
        self.vectorizer = TfidfVectorizer(
            max_features=100,
            ngram_range=(1, 2),
            stop_words='english'
        )
        self.classifier = RandomForestClassifier(
            n_estimators=50,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        
        # Training state
        self.is_trained = False
        self.training_samples = 0
        
        # Feature importance cache
        self._feature_importance = {}
        
        # Negative keywords for rule-based features
        self.negative_keywords = [
            'crash', 'crashes', 'bug', 'error', 'issue', 'problem',
            'not working', 'doesnt work', 'broken', 'fix', 'terrible',
            'horrible', 'awful', 'worst', 'hate', 'bad', 'useless',
            'waste', 'refund', 'delete', 'uninstall', 'slow', 'lag',
            'freeze', 'stuck', 'annoying', 'glitch'
        ]
        
        # Load model if path provided
        if model_path and os.path.exists(model_path):
            self._load_model(model_path)

    def _extract_features(self, review: Review) -> Dict[str, float]:
        """Extract numerical features from review."""
        text = review.text.lower()
        
        features = {
            # Text features
            'length': len(text),
            'word_count': len(text.split()),
            'avg_word_length': np.mean([len(w) for w in text.split()]) if text.split() else 0,
            
            # Sentiment indicators
            'has_negative_keywords': any(kw in text for kw in self.negative_keywords),
            'exclamation_count': text.count('!'),
            'question_count': text.count('?'),
            'caps_ratio': sum(1 for c in text if c.isupper()) / len(text) if text else 0,
            
            # Metadata features
            'rating': review.metadata.rating or 3.0,
            'is_verified': 1.0 if review.metadata.is_verified else 0.0,
            'has_version': 1.0 if review.metadata.version else 0.0,
            'has_device': 1.0 if review.metadata.device else 0.0,
        }
        
        return features

    async def score(self, review: Review) -> ActionabilityScore:
        """Score a single review."""
        if not self.is_trained:
            # Fall back to rule-based scoring
            return self._rule_based_score(review)
        
        # Extract features
        features_dict = self._extract_features(review)
        
        # Get TF-IDF features
        try:
            tfidf_features = self.vectorizer.transform([review.text]).toarray()[0]
        except:
            # Vectorizer not fitted
            return self._rule_based_score(review)
        
        # Combine features
        feature_vector = np.hstack([
            list(features_dict.values()),
            tfidf_features
        ]).reshape(1, -1)
        
        # Predict
        proba = self.classifier.predict_proba(feature_vector)[0]
        score = proba[1]  # Probability of being actionable
        
        # Confidence (how certain the model is)
        confidence = max(proba)
        
        is_actionable = score >= self.threshold
        
        return ActionabilityScore(
            score=float(score),
            confidence=float(confidence),
            features=features_dict,
            is_actionable=is_actionable
        )

    async def score_batch(self, reviews: List[Review]) -> List[ActionabilityScore]:
        """Score batch of reviews (optimized)."""
        if not self.is_trained:
            # Fall back to rule-based
            return [self._rule_based_score(r) for r in reviews]
        
        # Extract all features
        feature_dicts = [self._extract_features(r) for r in reviews]
        
        # Get TF-IDF features for all
        texts = [r.text for r in reviews]
        try:
            tfidf_features = self.vectorizer.transform(texts).toarray()
        except:
            return [self._rule_based_score(r) for r in reviews]
        
        # Combine features
        feature_vectors = []
        for features_dict, tfidf_vec in zip(feature_dicts, tfidf_features):
            feature_vector = np.hstack([
                list(features_dict.values()),
                tfidf_vec
            ])
            feature_vectors.append(feature_vector)
        
        feature_matrix = np.array(feature_vectors)
        
        # Batch predict
        probas = self.classifier.predict_proba(feature_matrix)
        
        # Create scores
        scores = []
        for i, (proba, features_dict) in enumerate(zip(probas, feature_dicts)):
            score = proba[1]
            confidence = max(proba)
            is_actionable = score >= self.threshold
            
            scores.append(ActionabilityScore(
                score=float(score),
                confidence=float(confidence),
                features=features_dict,
                is_actionable=is_actionable
            ))
        
        return scores

    def _rule_based_score(self, review: Review) -> ActionabilityScore:
        """Rule-based scoring (fallback when ML model not trained)."""
        text = review.text.lower()
        rating = review.metadata.rating or 3.0
        
        # Calculate score based on rules
        score = 0.0
        
        # Low rating = more likely actionable
        if rating <= 2:
            score += 0.4
        elif rating <= 3:
            score += 0.2
        
        # Negative keywords = actionable
        if any(kw in text for kw in self.negative_keywords):
            score += 0.3
        
        # Length (too short = noise)
        if len(text) >= 25:
            score += 0.2
        
        # Exclamation/caps = emotion = likely actionable
        if text.count('!') > 0 or sum(1 for c in text if c.isupper()) / len(text) > 0.3:
            score += 0.1
        
        score = min(score, 1.0)
        
        is_actionable = score >= self.threshold
        
        return ActionabilityScore(
            score=score,
            confidence=0.7,  # Medium confidence for rules
            features={'rule_based': True},
            is_actionable=is_actionable
        )

    async def train_online(
        self,
        reviews: List[Review],
        labels: List[bool]
    ) -> None:
        """
        Train or update model with new labeled data.
        
        Args:
            reviews: List of reviews
            labels: List of booleans (True = actionable, False = not actionable)
        """
        if len(reviews) != len(labels):
            raise ValueError("Reviews and labels must have same length")
        
        logger.info(f"Online training with {len(reviews)} samples")
        
        # Extract features
        feature_dicts = [self._extract_features(r) for r in reviews]
        texts = [r.text for r in reviews]
        
        # Fit or update TF-IDF vectorizer
        if not self.is_trained:
            # Initial training
            tfidf_features = self.vectorizer.fit_transform(texts).toarray()
        else:
            # Update vocabulary
            tfidf_features = self.vectorizer.transform(texts).toarray()
        
        # Combine features
        feature_vectors = []
        for features_dict, tfidf_vec in zip(feature_dicts, tfidf_features):
            feature_vector = np.hstack([
                list(features_dict.values()),
                tfidf_vec
            ])
            feature_vectors.append(feature_vector)
        
        X = np.array(feature_vectors)
        y = np.array(labels, dtype=int)
        
        # Train model
        if not self.is_trained:
            # Initial fit
            self.classifier.fit(X, y)
            self.is_trained = True
        else:
            # Incremental update using partial_fit simulation
            # Random Forest doesn't support partial_fit, so we'd need to:
            # 1. Retrain with all data (requires storing data)
            # 2. Use online learning algorithm (SGDClassifier)
            # For now, retrain
            self.classifier.fit(X, y)
        
        self.training_samples += len(reviews)
        
        # Update feature importance
        if hasattr(self.classifier, 'feature_importances_'):
            importances = self.classifier.feature_importances_
            feature_names = list(feature_dicts[0].keys()) + [
                f"tfidf_{i}" for i in range(len(tfidf_features[0]))
            ]
            self._feature_importance = dict(zip(feature_names, importances))
        
        logger.info(
            f"Model trained. Total samples: {self.training_samples}, "
            f"Accuracy on training: {self.classifier.score(X, y):.3f}"
        )

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores."""
        return self._feature_importance

    def save_model(self, path: str) -> None:
        """Save model to disk."""
        model_data = {
            'vectorizer': self.vectorizer,
            'classifier': self.classifier,
            'is_trained': self.is_trained,
            'training_samples': self.training_samples,
            'feature_importance': self._feature_importance
        }
        
        with open(path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Model saved to {path}")

    def _load_model(self, path: str) -> None:
        """Load model from disk."""
        with open(path, 'rb') as f:
            model_data = pickle.load(f)
        
        self.vectorizer = model_data['vectorizer']
        self.classifier = model_data['classifier']
        self.is_trained = model_data['is_trained']
        self.training_samples = model_data['training_samples']
        self._feature_importance = model_data['feature_importance']
        
        logger.info(f"Model loaded from {path} ({self.training_samples} samples)")


class RuleBasedActionabilityScorer(IActionabilityScorer):
    """
    Simple rule-based scorer (no ML).
    Good for cold start before collecting labeled data.
    """

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        
        self.negative_keywords = [
            'crash', 'crashes', 'bug', 'error', 'issue', 'problem',
            'not working', 'doesnt work', 'broken', 'fix', 'terrible',
            'horrible', 'awful', 'worst', 'hate', 'bad', 'useless',
            'waste', 'refund', 'delete', 'uninstall', 'slow', 'lag',
            'freeze', 'stuck', 'annoying', 'glitch'
        ]

    async def score(self, review: Review) -> ActionabilityScore:
        """Score using rules."""
        text = review.text.lower()
        rating = review.metadata.rating or 3.0
        
        score = 0.0
        
        # Rating
        if rating <= 2:
            score += 0.4
        elif rating <= 3:
            score += 0.2
        
        # Keywords
        if any(kw in text for kw in self.negative_keywords):
            score += 0.3
        
        # Length
        if len(text) >= 25:
            score += 0.2
        else:
            score -= 0.1
        
        # Emotion indicators
        if text.count('!') > 0:
            score += 0.1
        
        score = max(0.0, min(score, 1.0))
        
        return ActionabilityScore(
            score=score,
            confidence=0.7,
            features={
                'rating': rating,
                'length': len(text),
                'has_keywords': any(kw in text for kw in self.negative_keywords)
            },
            is_actionable=score >= self.threshold
        )

    async def score_batch(self, reviews: List[Review]) -> List[ActionabilityScore]:
        """Score batch."""
        return [await self.score(r) for r in reviews]

    async def train_online(
        self,
        reviews: List[Review],
        labels: List[bool]
    ) -> None:
        """No-op for rule-based."""
        pass

    def get_feature_importance(self) -> Dict[str, float]:
        """Return rule weights."""
        return {
            'rating': 0.4,
            'keywords': 0.3,
            'length': 0.2,
            'emotion': 0.1
        }
