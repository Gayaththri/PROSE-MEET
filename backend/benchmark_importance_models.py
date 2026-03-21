import argparse
import csv
import json
from contextlib import contextmanager
from typing import Dict, List, Tuple

import numpy as np
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

from pipeline import importance
from pipeline.importance_model import load_model, predict_probabilities


def _parse_label(value: str) -> int:
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "important", "high"}:
        return 1
    return 0


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_dataset(csv_path: str, label_col: str) -> Tuple[List[Dict], List[int]]:
    segments = []
    labels = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if label_col not in (reader.fieldnames or []):
            raise ValueError(f"Label column '{label_col}' not in CSV.")
        for idx, row in enumerate(reader):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            seg = {
                "segment_id": row.get("segment_id") or str(idx),
                "start": _to_float(row.get("start"), float(idx)),
                "end": _to_float(row.get("end"), float(idx + 1)),
                "text": text,
                "pitch_variance": _to_float(row.get("pitch_variance"), 0.0),
                "mean_energy": _to_float(row.get("mean_energy"), 0.0),
                "pause_ratio": _to_float(row.get("pause_ratio"), 0.0),
            }
            segments.append(seg)
            labels.append(_parse_label(row.get(label_col)))

    if len(set(labels)) < 2:
        raise ValueError("Need both positive and negative labels for benchmarking.")
    return segments, labels


def _metrics(y_true: List[int], probs: np.ndarray, threshold: float) -> Dict[str, float]:
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


@contextmanager
def _force_rule_based_importance():
    original_get_bundle = importance._get_model_bundle
    original_attempted = importance._MODEL_LOAD_ATTEMPTED
    original_bundle = importance._MODEL_BUNDLE
    try:
        importance._get_model_bundle = lambda: None
        importance._MODEL_LOAD_ATTEMPTED = True
        importance._MODEL_BUNDLE = None
        yield
    finally:
        importance._get_model_bundle = original_get_bundle
        importance._MODEL_LOAD_ATTEMPTED = original_attempted
        importance._MODEL_BUNDLE = original_bundle


def _rule_based_probabilities(segments: List[Dict]) -> np.ndarray:
    with _force_rule_based_importance():
        ranked = importance.compute_importance(segments)
    by_id = {s["segment_id"]: s for s in ranked}
    ordered_scores = [float(by_id[s["segment_id"]]["importance_score"]) for s in segments]
    scores = np.array(ordered_scores, dtype=np.float32)
    max_score = float(scores.max()) if len(scores) else 1.0
    if max_score <= 0:
        return scores
    return scores / max_score


def main():
    parser = argparse.ArgumentParser(description="Benchmark rule-based vs supervised importance scoring.")
    parser.add_argument("--data", required=True, help="Path to labeled CSV")
    parser.add_argument("--label-col", default="label", help="Label column name")
    parser.add_argument("--model-dir", default=None, help="Model artifacts directory")
    parser.add_argument("--rule-threshold", type=float, default=0.5, help="Threshold for normalized rule score")
    parser.add_argument("--output-json", default=None, help="Optional path to write benchmark metrics as JSON")
    args = parser.parse_args()

    segments, labels = _load_dataset(args.data, args.label_col)
    y_true = labels

    rule_probs = _rule_based_probabilities(segments)
    rule_metrics = _metrics(y_true, rule_probs, threshold=args.rule_threshold)
    output = {
        "samples": len(y_true),
        "rule_threshold": float(args.rule_threshold),
        "rule_based": rule_metrics,
        "supervised": None,
    }

    print("=== Importance Benchmark ===")
    print(f"Samples: {len(y_true)}")
    print(
        "[Rule-based] "
        f"P={rule_metrics['precision']:.3f} "
        f"R={rule_metrics['recall']:.3f} "
        f"F1={rule_metrics['f1']:.3f} "
        f"AUC={rule_metrics['auc']:.3f}"
    )

    bundle = load_model(model_dir=args.model_dir)
    if bundle is None:
        print("[Supervised] Skipped: model not found.")
        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2)
        return

    model_probs = predict_probabilities(segments, bundle)
    model_threshold = float(bundle.get("threshold", 0.5))
    model_metrics = _metrics(y_true, model_probs, threshold=model_threshold)
    output["supervised"] = {
        "threshold": model_threshold,
        **model_metrics,
    }
    print(
        "[Supervised] "
        f"threshold={model_threshold:.3f} "
        f"P={model_metrics['precision']:.3f} "
        f"R={model_metrics['recall']:.3f} "
        f"F1={model_metrics['f1']:.3f} "
        f"AUC={model_metrics['auc']:.3f}"
    )
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)


if __name__ == "__main__":
    main()
