import argparse
import csv
from typing import Dict, List, Tuple

import numpy as np
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

from pipeline.importance_model import calibrate_threshold, load_model, predict_probabilities, save_model


def _parse_label(value: str) -> int:
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "important", "high"}:
        return 1
    return 0


def _to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _load_labeled_segments(csv_path: str, label_col: str) -> Tuple[List[Dict], List[int]]:
    segments = []
    labels = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"text"}
        missing = [col for col in required if col not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing required columns in CSV: {', '.join(missing)}")
        if label_col not in (reader.fieldnames or []):
            raise ValueError(f"Label column '{label_col}' not found in CSV.")

        for row in reader:
            text = (row.get("text") or "").strip()
            if not text:
                continue
            start = _to_float(row.get("start"), 0.0)
            end = _to_float(row.get("end"), start + _to_float(row.get("duration"), 0.0))
            if end < start:
                end = start

            segment = {
                "text": text,
                "pitch_variance": _to_float(row.get("pitch_variance"), 0.0),
                "mean_energy": _to_float(row.get("mean_energy"), 0.0),
                "pause_ratio": _to_float(row.get("pause_ratio"), 0.0),
                "start": start,
                "end": end,
            }
            labels.append(_parse_label(row.get(label_col)))
            segments.append(segment)

    if not segments:
        raise ValueError("No usable rows found in CSV.")
    if len(set(labels)) < 2:
        raise ValueError("Calibration set must contain both positive and negative labels.")
    return segments, labels


def _evaluate(y_true: List[int], probs: np.ndarray, threshold: float) -> Dict[str, float]:
    preds = (probs >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, preds, average="binary", zero_division=0
    )
    auc = roc_auc_score(y_true, probs) if len(set(y_true)) > 1 else 0.0
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "auc": float(auc),
    }


def main():
    parser = argparse.ArgumentParser(description="Recalibrate threshold for trained importance model.")
    parser.add_argument("--data", required=True, help="Path to labeled CSV")
    parser.add_argument("--label-col", default="label", help="Label column name (default: label)")
    parser.add_argument("--model-dir", default=None, help="Directory containing saved model artifacts")
    parser.add_argument(
        "--min-precision",
        type=float,
        default=None,
        help="Optional minimum precision constraint for threshold calibration",
    )
    args = parser.parse_args()

    bundle = load_model(model_dir=args.model_dir)
    if bundle is None:
        raise FileNotFoundError(
            "No trained model found. Run train_importance_model.py first."
        )

    segments, labels = _load_labeled_segments(args.data, args.label_col)
    probs = predict_probabilities(segments, bundle)
    threshold_metrics = calibrate_threshold(labels, probs, min_precision=args.min_precision)
    threshold = threshold_metrics["threshold"]
    eval_metrics = _evaluate(labels, probs, threshold=threshold)
    eval_metrics.update(
        {
            "calibrated_threshold": float(threshold),
            "threshold_precision": float(threshold_metrics["precision"]),
            "threshold_recall": float(threshold_metrics["recall"]),
            "threshold_f1": float(threshold_metrics["f1"]),
            "calibration_size": int(len(labels)),
        }
    )

    # Save the existing trained components with updated threshold/metrics.
    base_bundle = {
        "vectorizer": bundle["vectorizer"],
        "scaler": bundle["scaler"],
        "classifier": bundle["classifier"],
    }
    paths = save_model(
        model_bundle=base_bundle,
        threshold=threshold,
        model_dir=args.model_dir,
        metrics=eval_metrics,
    )

    print("Threshold recalibration complete.")
    print(
        "Calibration metrics: "
        f"precision={eval_metrics['precision']:.3f}, "
        f"recall={eval_metrics['recall']:.3f}, "
        f"f1={eval_metrics['f1']:.3f}, "
        f"auc={eval_metrics['auc']:.3f}"
    )
    print(
        f"New threshold={threshold:.3f} "
        f"(precision={threshold_metrics['precision']:.3f}, "
        f"recall={threshold_metrics['recall']:.3f}, "
        f"f1={threshold_metrics['f1']:.3f})"
    )
    print(f"Saved model: {paths['model_path']}")
    print(f"Saved metadata: {paths['metadata_path']}")


if __name__ == "__main__":
    main()
