"""Train and evaluate the importance classification model."""

import argparse
import csv
from typing import Dict, List, Tuple

import numpy as np
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import train_test_split

from pipeline.importance_model import (
    calibrate_threshold,
    predict_probabilities,
    save_model,
    train_classifier,
)


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
            label = _parse_label(row.get(label_col))
            segments.append(segment)
            labels.append(label)

    if not segments:
        raise ValueError("No usable rows found in CSV.")
    if len(set(labels)) < 2:
        raise ValueError("Dataset must contain both positive and negative labels.")
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
    parser = argparse.ArgumentParser(description="Train supervised importance classifier.")
    parser.add_argument("--data", required=True, help="Path to labeled CSV")
    parser.add_argument("--label-col", default="label", help="Label column name (default: label)")
    parser.add_argument("--model-dir", default=None, help="Directory to save model artifacts")
    parser.add_argument("--test-size", type=float, default=0.2, help="Validation split ratio")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--min-precision",
        type=float,
        default=None,
        help="Optional minimum precision constraint for threshold calibration",
    )
    args = parser.parse_args()

    segments, labels = _load_labeled_segments(args.data, args.label_col)
    x_train, x_val, y_train, y_val = train_test_split(
        segments,
        labels,
        test_size=args.test_size,
        random_state=args.random_state,
        stratify=labels,
    )

    model_bundle = train_classifier(x_train, y_train)
    val_probs = predict_probabilities(x_val, model_bundle)

    threshold_metrics = calibrate_threshold(
        labels=y_val,
        probabilities=val_probs,
        min_precision=args.min_precision,
    )
    threshold = threshold_metrics["threshold"]
    eval_metrics = _evaluate(y_val, val_probs, threshold=threshold)
    eval_metrics.update(
        {
            "calibrated_threshold": float(threshold),
            "threshold_precision": float(threshold_metrics["precision"]),
            "threshold_recall": float(threshold_metrics["recall"]),
            "threshold_f1": float(threshold_metrics["f1"]),
            "val_size": int(len(y_val)),
            "train_size": int(len(y_train)),
        }
    )

    paths = save_model(
        model_bundle=model_bundle,
        threshold=threshold,
        model_dir=args.model_dir,
        metrics=eval_metrics,
    )

    print("Training complete.")
    print(f"Train samples: {len(y_train)} | Validation samples: {len(y_val)}")
    print(
        "Validation metrics: "
        f"precision={eval_metrics['precision']:.3f}, "
        f"recall={eval_metrics['recall']:.3f}, "
        f"f1={eval_metrics['f1']:.3f}, "
        f"auc={eval_metrics['auc']:.3f}"
    )
    print(
        f"Calibrated threshold={threshold:.3f} "
        f"(precision={threshold_metrics['precision']:.3f}, "
        f"recall={threshold_metrics['recall']:.3f}, "
        f"f1={threshold_metrics['f1']:.3f})"
    )
    print(f"Saved model: {paths['model_path']}")
    print(f"Saved metadata: {paths['metadata_path']}")


if __name__ == "__main__":
    main()
