#!/usr/bin/env python3
"""
Drift Monitor - v3 Shadow Monitoring
Detects data drift and adversarial content in review datasets.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np


def detect_drift(baseline_path: str, current_path: str) -> dict:
    """Simple statistical drift detection between two CSV datasets."""
    try:
        baseline_df = pd.read_csv(baseline_path, nrows=5000)
        current_df = pd.read_csv(current_path, nrows=5000)

        drift_signals = []

        # Check score/rating distribution shift
        for col in ['score', 'rating']:
            if col in baseline_df.columns and col in current_df.columns:
                b_mean = baseline_df[col].mean()
                c_mean = current_df[col].mean()
                shift = abs(b_mean - c_mean)
                if shift > 0.5:
                    drift_signals.append({
                        "column": col,
                        "baseline_mean": round(b_mean, 3),
                        "current_mean": round(c_mean, 3),
                        "shift": round(shift, 3)
                    })

        # Check review length distribution
        for col in ['content', 'review', 'text']:
            if col in baseline_df.columns and col in current_df.columns:
                b_len = baseline_df[col].dropna().str.len().mean()
                c_len = current_df[col].dropna().str.len().mean()
                if b_len > 0 and abs(b_len - c_len) / b_len > 0.3:
                    drift_signals.append({
                        "column": f"{col}_length",
                        "baseline_mean": round(b_len, 1),
                        "current_mean": round(c_len, 1),
                        "relative_shift": round(abs(b_len - c_len) / b_len, 3)
                    })

        drift_detected = len(drift_signals) > 0

        return {
            "drift_detected": drift_detected,
            "drift_signals": drift_signals,
            "baseline_rows": len(baseline_df),
            "current_rows": len(current_df),
        }

    except Exception as e:
        return {"drift_detected": False, "error": str(e)}


def detect_adversarial(current_path: str) -> dict:
    """Detect adversarial / spam review patterns."""
    try:
        df = pd.read_csv(current_path, nrows=5000)

        signals = []
        adversarial_detected = False

        text_col = next((c for c in ['content', 'review', 'text'] if c in df.columns), None)
        if text_col:
            texts = df[text_col].dropna().astype(str)

            # Detect coordinated exact duplicates (>5% exact dupes = suspicious)
            dupe_rate = texts.duplicated().mean()
            if dupe_rate > 0.05:
                adversarial_detected = True
                signals.append({
                    "type": "coordinated_duplicates",
                    "duplicate_rate": round(dupe_rate, 3),
                    "threshold": 0.05
                })

            # Detect very short reviews flooding (>50% reviews under 10 chars)
            short_rate = (texts.str.len() < 10).mean()
            if short_rate > 0.5:
                adversarial_detected = True
                signals.append({
                    "type": "spam_short_reviews",
                    "short_review_rate": round(short_rate, 3),
                    "threshold": 0.5
                })

        return {
            "adversarial_detected": adversarial_detected,
            "signals": signals,
            "rows_analyzed": len(df),
        }

    except Exception as e:
        return {"adversarial_detected": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Drift and adversarial monitor for review datasets")
    parser.add_argument("--baseline", required=True, help="Path to baseline CSV")
    parser.add_argument("--current", required=True, help="Path to current CSV")
    parser.add_argument("--output-dir", required=True, help="Output directory for reports")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run drift detection
    drift_result = detect_drift(args.baseline, args.current)
    drift_report_path = output_dir / "data_drift_report.json"
    with open(drift_report_path, "w") as f:
        json.dump(drift_result, f, indent=2)

    # Run adversarial detection
    adv_result = detect_adversarial(args.current)
    adv_report_path = output_dir / "adversarial_report.json"
    with open(adv_report_path, "w") as f:
        json.dump(adv_result, f, indent=2)

    print(f"Drift detected: {drift_result['drift_detected']}")
    print(f"Adversarial detected: {adv_result['adversarial_detected']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
