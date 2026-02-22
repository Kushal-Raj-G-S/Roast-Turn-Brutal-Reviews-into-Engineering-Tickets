"""
Advanced Feature Engineering for Actionability Scoring
CPU-efficient feature extraction with sentiment and linguistic analysis.
"""

import re
import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FeatureVector:
    """Structured feature representation."""
    
    # Text statistics
    length: int
    word_count: int
    avg_word_length: float
    sentence_count: int
    
    # Sentiment indicators
    positive_words: int
    negative_words: int
    complaint_verbs: int
    emotion_intensity: float
    
    # Structural patterns
    question_marks: int
    exclamation_marks: int
    caps_ratio: float
    punctuation_ratio: float
    
    # Content signals
    has_bug_keywords: bool
    has_feature_request: bool
    has_comparison: bool
    has_specific_details: bool
    
    # Mixed sentiment and subtle signals (V3)
    has_concession: bool
    concession_count: int
    has_monetization_complaint: bool
    has_retention_signal: bool
    feature_request_count: int
    sentiment_contrast: float
    
    # Metadata
    rating: float
    is_verified: bool
    has_version: bool
    has_device: bool
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array for ML models."""
        return np.array([
            self.length,
            self.word_count,
            self.avg_word_length,
            self.sentence_count,
            self.positive_words,
            self.negative_words,
            self.complaint_verbs,
            self.emotion_intensity,
            self.question_marks,
            self.exclamation_marks,
            self.caps_ratio,
            self.punctuation_ratio,
            int(self.has_bug_keywords),
            int(self.has_feature_request),
            int(self.has_comparison),
            int(self.has_specific_details),
            int(self.has_concession),
            self.concession_count,
            int(self.has_monetization_complaint),
            int(self.has_retention_signal),
            self.feature_request_count,
            self.sentiment_contrast,
            self.rating,
            int(self.is_verified),
            int(self.has_version),
            int(self.has_device)
        ], dtype=np.float32)
    
    @staticmethod
    def feature_names() -> List[str]:
        """Get feature names for model interpretation."""
        return [
            'length', 'word_count', 'avg_word_length', 'sentence_count',
            'positive_words', 'negative_words', 'complaint_verbs', 'emotion_intensity',
            'question_marks', 'exclamation_marks', 'caps_ratio', 'punctuation_ratio',
            'has_bug_keywords', 'has_feature_request', 'has_comparison', 'has_specific_details',
            'has_concession', 'concession_count', 'has_monetization_complaint', 'has_retention_signal',
            'feature_request_count', 'sentiment_contrast',
            'rating', 'is_verified', 'has_version', 'has_device'
        ]


class FeatureExtractor:
    """
    Advanced feature extraction for review actionability.
    Lightweight and CPU-efficient.
    """
    
    # Sentiment lexicons (lightweight)
    POSITIVE_WORDS = {
        'good', 'great', 'excellent', 'amazing', 'awesome', 'love', 'perfect',
        'best', 'fantastic', 'wonderful', 'nice', 'enjoy', 'helpful', 'thanks',
        'thank', 'appreciate', 'easy', 'simple', 'fast', 'smooth', 'works'
    }
    
    NEGATIVE_WORDS = {
        'bad', 'terrible', 'awful', 'horrible', 'worst', 'hate', 'sucks',
        'useless', 'waste', 'disappointed', 'disappointing', 'poor', 'slow',
        'laggy', 'annoying', 'frustrating', 'broken', 'fail', 'failed', 'wrong'
    }
    
    COMPLAINT_VERBS = {
        'crash', 'crashes', 'crashed', 'crashing', 'freeze', 'freezes', 'froze',
        'hang', 'hangs', 'stuck', 'break', 'breaks', 'broke', 'broken',
        'fail', 'fails', 'failed', 'failing', 'stop', 'stops', 'stopped',
        'lose', 'lost', 'delete', 'deleted', 'remove', 'removed',
        'disappear', 'disappeared', 'missing', 'cant', "can't", 'wont', "won't",
        'doesnt', "doesn't", 'not working', 'notworking'
    }
    
    BUG_KEYWORDS = {
        'bug', 'error', 'issue', 'problem', 'glitch', 'defect', 'fault',
        'crash', 'freeze', 'lag', 'slow', 'broken', 'fix', 'update needed'
    }
    
    FEATURE_KEYWORDS = {
        'feature', 'add', 'please add', 'would be nice', 'suggestion',
        'should have', 'needs', 'missing', 'wish', 'hope', 'could', 'should'
    }
    
    # V3: Mixed sentiment and subtle signals
    CONCESSION_PHRASES = {
        'but', 'however', 'although', 'though', 'still', 'yet',
        'even though', 'despite', 'nevertheless', 'nonetheless',
        'on the other hand', 'that said', 'except'
    }
    
    FEATURE_REQUEST_VERBS = {
        'add', 'improve', 'support', 'allow', 'enable', 'include',
        'need', 'want', 'wish', 'hope', 'please', 'would like',
        'should add', 'could add', 'better if'
    }
    
    MONETIZATION_COMPLAINTS = {
        'limit', 'limits', 'limited', 'free', 'subscription', 'price',
        'pay', 'paid', 'paywall', 'expensive', 'cost', 'money',
        'premium', 'trial', 'upgrade', 'unlock', 'purchase'
    }
    
    RETENTION_SIGNALS = {
        'uninstall', 'uninstalling', 'delete', 'deleting', 'removing',
        'switching', 'switch to', 'leaving', 'quit', 'gave up',
        'stopped using', 'no longer', 'used to use', 'abandoning'
    }
    
    COMPARISON_KEYWORDS = {
        'better than', 'worse than', 'compared to', 'like', 'similar to',
        'instead of', 'prefer', 'previous version', 'old version', 'used to'
    }
    
    DETAIL_PATTERNS = [
        r'\b\d+\.\d+\.\d+\b',  # Version numbers (e.g., 2.1.3)
        r'\b(android|ios|iphone|samsung|pixel|galaxy)\b',  # Device names
        r'\b(button|menu|screen|page|tab|icon|feature)\b',  # UI elements
        r'\b(when|after|while|during|before)\b',  # Temporal context
    ]
    
    def __init__(self):
        self.detail_regex = re.compile('|'.join(self.DETAIL_PATTERNS), re.IGNORECASE)
    
    def extract(self, text: str, rating: float = None, is_verified: bool = False,
                version: str = None, device: str = None) -> FeatureVector:
        """
        Extract features from review text and metadata.
        
        Args:
            text: Review content
            rating: Star rating (1-5)
            is_verified: Whether review is verified
            version: App version mentioned
            device: Device model mentioned
            
        Returns:
            FeatureVector with all computed features
        """
        text_lower = text.lower()
        words = text_lower.split()
        
        # Text statistics
        length = len(text)
        word_count = len(words)
        avg_word_length = np.mean([len(w) for w in words]) if words else 0
        sentence_count = len([s for s in text.split('.') if s.strip()])
        
        # Sentiment indicators
        positive_words = sum(1 for w in words if w in self.POSITIVE_WORDS)
        negative_words = sum(1 for w in words if w in self.NEGATIVE_WORDS)
        complaint_verbs = sum(1 for w in words if w in self.COMPLAINT_VERBS)
        
        # Emotion intensity (normalized)
        emotion_intensity = 0.0
        if word_count > 0:
            emotion_intensity = (negative_words + complaint_verbs - positive_words) / word_count
            emotion_intensity = max(-1.0, min(1.0, emotion_intensity))  # Clamp to [-1, 1]
        
        # Structural patterns
        question_marks = text.count('?')
        exclamation_marks = text.count('!')
        caps_ratio = sum(1 for c in text if c.isupper()) / length if length > 0 else 0
        punctuation_count = sum(1 for c in text if c in '.,!?;:')
        punctuation_ratio = punctuation_count / length if length > 0 else 0
        
        # Content signals
        has_bug_keywords = any(kw in text_lower for kw in self.BUG_KEYWORDS)
        has_feature_request = any(kw in text_lower for kw in self.FEATURE_KEYWORDS)
        has_comparison = any(kw in text_lower for kw in self.COMPARISON_KEYWORDS)
        has_specific_details = bool(self.detail_regex.search(text))
        
        # V3: Mixed sentiment and subtle signals
        has_concession = any(phrase in text_lower for phrase in self.CONCESSION_PHRASES)
        concession_count = sum(1 for phrase in self.CONCESSION_PHRASES if phrase in text_lower)
        
        has_monetization_complaint = any(kw in text_lower for kw in self.MONETIZATION_COMPLAINTS)
        has_retention_signal = any(signal in text_lower for signal in self.RETENTION_SIGNALS)
        
        feature_request_count = sum(1 for verb in self.FEATURE_REQUEST_VERBS if verb in text_lower)
        
        # Sentiment contrast: higher when both positive and negative present
        sentiment_contrast = 0.0
        if positive_words > 0 and negative_words > 0:
            sentiment_contrast = min(positive_words, negative_words) / word_count if word_count > 0 else 0
        
        # Metadata
        rating_value = rating if rating is not None else 3.0
        
        return FeatureVector(
            length=length,
            word_count=word_count,
            avg_word_length=avg_word_length,
            sentence_count=sentence_count,
            positive_words=positive_words,
            negative_words=negative_words,
            complaint_verbs=complaint_verbs,
            emotion_intensity=emotion_intensity,
            question_marks=question_marks,
            exclamation_marks=exclamation_marks,
            caps_ratio=caps_ratio,
            punctuation_ratio=punctuation_ratio,
            has_bug_keywords=has_bug_keywords,
            has_feature_request=has_feature_request,
            has_comparison=has_comparison,
            has_specific_details=has_specific_details,
            has_concession=has_concession,
            concession_count=concession_count,
            has_monetization_complaint=has_monetization_complaint,
            has_retention_signal=has_retention_signal,
            feature_request_count=feature_request_count,
            sentiment_contrast=sentiment_contrast,
            rating=rating_value,
            is_verified=is_verified,
            has_version=version is not None,
            has_device=device is not None
        )
    
    def extract_batch(self, reviews: List[Dict]) -> np.ndarray:
        """
        Extract features for multiple reviews efficiently.
        
        Args:
            reviews: List of dicts with keys: text, rating, is_verified, version, device
            
        Returns:
            2D numpy array (n_samples, n_features)
        """
        features = []
        for review in reviews:
            fv = self.extract(
                text=review.get('text', ''),
                rating=review.get('rating'),
                is_verified=review.get('is_verified', False),
                version=review.get('version'),
                device=review.get('device')
            )
            features.append(fv.to_array())
        
        return np.vstack(features) if features else np.array([])


def calculate_sentiment_polarity(text: str) -> float:
    """
    Simple sentiment polarity score [-1, 1].
    -1 = very negative, 0 = neutral, 1 = very positive
    """
    text_lower = text.lower()
    words = text_lower.split()
    
    if not words:
        return 0.0
    
    positive = sum(1 for w in words if w in FeatureExtractor.POSITIVE_WORDS)
    negative = sum(1 for w in words if w in FeatureExtractor.NEGATIVE_WORDS)
    
    # Normalize by word count
    polarity = (positive - negative) / len(words)
    return max(-1.0, min(1.0, polarity))


def detect_mixed_sentiment(text: str) -> bool:
    """
    Detect if review has mixed/conflicting sentiment.
    Example: "I love the app but it crashes constantly"
    """
    text_lower = text.lower()
    words = text_lower.split()
    
    positive = sum(1 for w in words if w in FeatureExtractor.POSITIVE_WORDS)
    negative = sum(1 for w in words if w in FeatureExtractor.NEGATIVE_WORDS)
    
    # Mixed sentiment if both positive and negative words present with reasonable balance
    if positive > 0 and negative > 0:
        ratio = min(positive, negative) / max(positive, negative)
        return ratio > 0.3  # At least 30% balance
    
    return False
