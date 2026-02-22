"""
Probability Calibration for Actionability Scorer
Implements Platt scaling, isotonic regression, and calibration metrics.
"""

import logging
import pickle
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CalibrationMetrics:
    """Calibration quality metrics."""
    brier_score: float  # Lower is better (0-1)
    ece: float  # Expected Calibration Error (0-1)
    mce: float  # Maximum Calibration Error (0-1)
    reliability_bins: List[Tuple[float, float, int]]  # (predicted_prob, actual_freq, count)
    
    def __str__(self):
        return (
            f"Brier Score: {self.brier_score:.4f}\n"
            f"ECE: {self.ece:.4f}\n"
            f"MCE: {self.mce:.4f}"
        )


class ProbabilityCalibrator:
    """
    Calibrate model probabilities using Platt scaling or isotonic regression.
    
    Platt Scaling: Fits a logistic regression on model outputs
    Isotonic Regression: Fits a monotonic function (more flexible, requires more data)
    """
    
    def __init__(self, method: str = "platt", n_bins: int = 10):
        """
        Initialize calibrator.
        
        Args:
            method: Calibration method ("platt", "isotonic", or "none")
            n_bins: Number of bins for ECE calculation
        """
        if method not in ["platt", "isotonic", "none"]:
            raise ValueError(f"Invalid calibration method: {method}")
        
        self.method = method
        self.n_bins = n_bins
        self.calibrator = None
        self.is_fitted = False
    
    def fit(self, probabilities: np.ndarray, labels: np.ndarray) -> None:
        """
        Fit calibration model on validation set.
        
        Args:
            probabilities: Uncalibrated probabilities (0-1)
            labels: True binary labels (0 or 1)
        """
        if len(probabilities) != len(labels):
            raise ValueError("Probabilities and labels must have same length")
        
        if len(probabilities) < 10:
            logger.warning(f"Only {len(probabilities)} samples for calibration. May be unreliable.")
        
        probabilities = np.array(probabilities).reshape(-1, 1)
        labels = np.array(labels).astype(int)
        
        if self.method == "platt":
            # Platt scaling: fit logistic regression on probabilities
            self.calibrator = LogisticRegression(solver='lbfgs', max_iter=100)
            self.calibrator.fit(probabilities, labels)
            logger.info(f"Platt scaling fitted on {len(labels)} samples")
        
        elif self.method == "isotonic":
            # Isotonic regression: fit monotonic function
            self.calibrator = IsotonicRegression(out_of_bounds='clip')
            self.calibrator.fit(probabilities.ravel(), labels)
            logger.info(f"Isotonic regression fitted on {len(labels)} samples")
        
        else:  # none
            self.calibrator = None
            logger.info("No calibration applied (method='none')")
        
        self.is_fitted = True
    
    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        """
        Apply calibration to probabilities.
        
        Args:
            probabilities: Uncalibrated probabilities (0-1)
            
        Returns:
            Calibrated probabilities (0-1)
        """
        if not self.is_fitted:
            logger.warning("Calibrator not fitted. Returning original probabilities.")
            return np.array(probabilities)
        
        if self.method == "none" or self.calibrator is None:
            return np.array(probabilities)
        
        probabilities = np.array(probabilities).reshape(-1, 1)
        
        if self.method == "platt":
            # Logistic regression returns probability via predict_proba
            calibrated = self.calibrator.predict_proba(probabilities)[:, 1]
        
        elif self.method == "isotonic":
            # Isotonic regression directly transforms values
            calibrated = self.calibrator.predict(probabilities.ravel())
        
        else:
            calibrated = probabilities.ravel()
        
        # Ensure values are in [0, 1]
        calibrated = np.clip(calibrated, 0, 1)
        
        return calibrated
    
    def fit_transform(self, probabilities: np.ndarray, labels: np.ndarray) -> np.ndarray:
        """Fit and transform in one step."""
        self.fit(probabilities, labels)
        return self.transform(probabilities)
    
    def save(self, path: Path) -> None:
        """Save calibrator to disk."""
        with open(path, 'wb') as f:
            pickle.dump({
                'method': self.method,
                'n_bins': self.n_bins,
                'calibrator': self.calibrator,
                'is_fitted': self.is_fitted
            }, f)
        logger.info(f"Calibrator saved to {path}")
    
    def load(self, path: Path) -> None:
        """Load calibrator from disk."""
        if not path.exists():
            logger.warning(f"Calibrator file not found: {path}")
            return
        
        with open(path, 'rb') as f:
            data = pickle.load(f)
        
        self.method = data['method']
        self.n_bins = data['n_bins']
        self.calibrator = data['calibrator']
        self.is_fitted = data['is_fitted']
        
        logger.info(f"Calibrator loaded from {path} (method={self.method})")


def compute_brier_score(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """
    Compute Brier score (mean squared error of probabilities).
    
    Lower is better. Range: [0, 1]
    Perfect calibration: 0
    
    Args:
        probabilities: Predicted probabilities (0-1)
        labels: True binary labels (0 or 1)
        
    Returns:
        Brier score
    """
    probabilities = np.array(probabilities)
    labels = np.array(labels).astype(float)
    
    return np.mean((probabilities - labels) ** 2)


def compute_ece(probabilities: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    """
    Compute Expected Calibration Error (ECE).
    
    ECE measures the difference between predicted probabilities and actual frequencies.
    Lower is better. Range: [0, 1]
    
    Args:
        probabilities: Predicted probabilities (0-1)
        labels: True binary labels (0 or 1)
        n_bins: Number of bins for discretization
        
    Returns:
        ECE value
    """
    probabilities = np.array(probabilities)
    labels = np.array(labels).astype(int)
    
    # Create bins
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]
    
    ece = 0.0
    
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        # Find samples in this bin
        in_bin = (probabilities > bin_lower) & (probabilities <= bin_upper)
        prop_in_bin = np.mean(in_bin)
        
        if prop_in_bin > 0:
            # Accuracy in this bin
            accuracy_in_bin = np.mean(labels[in_bin])
            # Average confidence in this bin
            avg_confidence_in_bin = np.mean(probabilities[in_bin])
            # Add weighted difference
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    
    return ece


def compute_mce(probabilities: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    """
    Compute Maximum Calibration Error (MCE).
    
    MCE is the maximum difference between predicted probabilities and actual frequencies
    across all bins.
    
    Args:
        probabilities: Predicted probabilities (0-1)
        labels: True binary labels (0 or 1)
        n_bins: Number of bins for discretization
        
    Returns:
        MCE value
    """
    probabilities = np.array(probabilities)
    labels = np.array(labels).astype(int)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]
    
    max_error = 0.0
    
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        in_bin = (probabilities > bin_lower) & (probabilities <= bin_upper)
        prop_in_bin = np.mean(in_bin)
        
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(labels[in_bin])
            avg_confidence_in_bin = np.mean(probabilities[in_bin])
            error = np.abs(avg_confidence_in_bin - accuracy_in_bin)
            max_error = max(max_error, error)
    
    return max_error


def compute_reliability_diagram_data(
    probabilities: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10
) -> List[Tuple[float, float, int]]:
    """
    Compute data for reliability diagram (calibration plot).
    
    Args:
        probabilities: Predicted probabilities (0-1)
        labels: True binary labels (0 or 1)
        n_bins: Number of bins
        
    Returns:
        List of (predicted_prob, actual_freq, count) tuples for each bin
    """
    probabilities = np.array(probabilities)
    labels = np.array(labels).astype(int)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]
    
    reliability_data = []
    
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        in_bin = (probabilities > bin_lower) & (probabilities <= bin_upper)
        count = np.sum(in_bin)
        
        if count > 0:
            avg_predicted = np.mean(probabilities[in_bin])
            avg_actual = np.mean(labels[in_bin])
            reliability_data.append((float(avg_predicted), float(avg_actual), int(count)))
        else:
            # Empty bin
            bin_center = (bin_lower + bin_upper) / 2
            reliability_data.append((float(bin_center), 0.0, 0))
    
    return reliability_data


def evaluate_calibration(
    probabilities: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10
) -> CalibrationMetrics:
    """
    Compute all calibration metrics.
    
    Args:
        probabilities: Predicted probabilities (0-1)
        labels: True binary labels (0 or 1)
        n_bins: Number of bins for ECE/MCE/reliability
        
    Returns:
        CalibrationMetrics object
    """
    brier = compute_brier_score(probabilities, labels)
    ece = compute_ece(probabilities, labels, n_bins)
    mce = compute_mce(probabilities, labels, n_bins)
    reliability = compute_reliability_diagram_data(probabilities, labels, n_bins)
    
    return CalibrationMetrics(
        brier_score=brier,
        ece=ece,
        mce=mce,
        reliability_bins=reliability
    )


def compare_calibration(
    uncalibrated_probs: np.ndarray,
    calibrated_probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10
) -> Dict[str, CalibrationMetrics]:
    """
    Compare uncalibrated vs calibrated probabilities.
    
    Args:
        uncalibrated_probs: Original model probabilities
        calibrated_probs: Calibrated probabilities
        labels: True binary labels
        n_bins: Number of bins
        
    Returns:
        Dictionary with 'uncalibrated' and 'calibrated' metrics
    """
    uncalibrated_metrics = evaluate_calibration(uncalibrated_probs, labels, n_bins)
    calibrated_metrics = evaluate_calibration(calibrated_probs, labels, n_bins)
    
    logger.info("Calibration Comparison:")
    logger.info(f"\nUncalibrated:\n{uncalibrated_metrics}")
    logger.info(f"\nCalibrated:\n{calibrated_metrics}")
    
    brier_improvement = uncalibrated_metrics.brier_score - calibrated_metrics.brier_score
    ece_improvement = uncalibrated_metrics.ece - calibrated_metrics.ece
    
    logger.info(f"\nImprovements:")
    logger.info(f"  Brier Score: {brier_improvement:+.4f}")
    logger.info(f"  ECE: {ece_improvement:+.4f}")
    
    return {
        'uncalibrated': uncalibrated_metrics,
        'calibrated': calibrated_metrics
    }


def print_reliability_diagram(reliability_bins: List[Tuple[float, float, int]]) -> None:
    """
    Print ASCII reliability diagram.
    
    Args:
        reliability_bins: List of (predicted_prob, actual_freq, count) tuples
    """
    print("\n📊 Reliability Diagram:")
    print("=" * 70)
    print(f"{'Predicted':<12} {'Actual':<12} {'Count':<8} {'Calibration'}")
    print("-" * 70)
    
    for pred, actual, count in reliability_bins:
        if count > 0:
            # Visual bar for calibration
            bar_length = 30
            pred_pos = int(pred * bar_length)
            actual_pos = int(actual * bar_length)
            
            bar = ['.'] * bar_length
            bar[pred_pos] = 'P'  # Predicted
            bar[actual_pos] = 'A'  # Actual
            
            # If very close, show overlap
            if abs(pred_pos - actual_pos) <= 1:
                bar[pred_pos] = '✓'
            
            bar_str = ''.join(bar)
            
            print(f"{pred:.3f}       {actual:.3f}       {count:<8} {bar_str}")
        else:
            print(f"{pred:.3f}       -           {count:<8} (empty bin)")
    
    print("=" * 70)
    print("Legend: P=Predicted, A=Actual, ✓=Well-calibrated")
    print()
