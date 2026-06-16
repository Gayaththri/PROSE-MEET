"""Train and evaluate the importance classification model."""

import argparse
import csv
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

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


def _load_labeled_segments(
    csv_path: str,
    label_col: str,
    group_col: Optional[str] = None,
) -> Tuple[List[Dict], List[int], bool]:
    """Load segments; if group_col is present in the CSV, store it on each segment for splitting."""
    segments = []
    labels = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        required = {"text"}
        missing = [col for col in required if col not in fieldnames]
        if missing:
            raise ValueError(f"Missing required columns in CSV: {', '.join(missing)}")
        if label_col not in fieldnames:
            raise ValueError(f"Label column '{label_col}' not found in CSV.")

        use_group = bool(group_col and group_col in fieldnames)
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
            if use_group:
                raw_g = (row.get(group_col) or "").strip()
                segment[group_col] = raw_g if raw_g else "__missing_group__"
            label = _parse_label(row.get(label_col))
            segments.append(segment)
            labels.append(label)

    if not segments:
        raise ValueError("No usable rows found in CSV.")
    if len(set(labels)) < 2:
        raise ValueError("Dataset must contain both positive and negative labels.")
    return segments, labels, use_group


def _split_train_val(
    segments: List[Dict],
    labels: List[int],
    group_col: str,
    use_group: bool,
    test_size: float,
    random_state: int,
) -> Tuple[List[Dict], List[Dict], List[int], List[int]]:
    """Split so entire meetings (groups) stay in train or val when use_group is True."""
    labels_arr = np.array(labels)
    if not use_group:
        return train_test_split(
            segments,
            labels,
            test_size=test_size,
            random_state=random_state,
            stratify=labels,
        )

    group_to_indices: Dict[str, List[int]] = defaultdict(list)
    for i, seg in enumerate(segments):
        group_to_indices[str(seg[group_col])].append(i)

    unique_groups = list(group_to_indices.keys())
    # Majority label per group for stratifying meetings (avoids all-positive val by chance)
    strat_labels = []
    for g in unique_groups:
        ys = labels_arr[group_to_indices[g]]
        strat_labels.append(1 if ys.mean() >= 0.5 else 0)

    try:
        g_train, g_val = train_test_split(
            unique_groups,
            test_size=test_size,
            random_state=random_state,
            stratify=strat_labels,
        )
    except ValueError:
        # Too few groups per class for stratification — random group holdout
        gss = GroupShuffleSplit(
            n_splits=1,
            test_size=test_size,
            random_state=random_state,
        )
        flat_groups = np.array([seg[group_col] for seg in segments])
        idx_train, idx_val = next(
            gss.split(np.zeros(len(segments)), labels_arr, flat_groups)
        )
        train_idx, val_idx = idx_train.tolist(), idx_val.tolist()
    else:
        train_idx = [i for g in g_train for i in group_to_indices[g]]
        val_idx = [i for g in g_val for i in group_to_indices[g]]

    x_train = [segments[i] for i in train_idx]
    x_val = [segments[i] for i in val_idx]
    y_train = [labels[i] for i in train_idx]
    y_val = [labels[i] for i in val_idx]

    if len(set(y_val)) < 2:
        print(
            "Warning: validation set has a single class after group split; "
            "metrics/AUC/threshold may be unreliable. Consider more meetings or --test-size."
        )
    return x_train, x_val, y_train, y_val


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


def _overfit_gaps(train_m: Dict[str, float], val_m: Dict[str, float]) -> Dict[str, float]:
    """Train minus validation; large positive gaps suggest memorization."""
    return {
        "overfit_f1_gap": float(train_m["f1"] - val_m["f1"]),
        "overfit_auc_gap": float(train_m["auc"] - val_m["auc"]),
    }


def _overfit_note(gaps: Dict[str, float]) -> str:
    f1g, aucg = gaps["overfit_f1_gap"], gaps["overfit_auc_gap"]
    parts = []
    if f1g > 0.12:
        parts.append(f"large F1 gap ({f1g:+.3f})")
    if aucg > 0.08:
        parts.append(f"large AUC gap ({aucg:+.3f})")
    if parts:
        return "Possible overfitting: " + "; ".join(parts) + "."
    if f1g > 0.06 or aucg > 0.05:
        return "Moderate train/val gap; review split size or regularization."
    return "Train and validation metrics are reasonably aligned at this threshold."


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
    parser.add_argument(
        "--group-col",
        default="meeting_id",
        help=(
            "Column name for group-wise train/val split (default: meeting_id). "
            "If the column is missing from the CSV, falls back to stratified row split."
        ),
    )
    args = parser.parse_args()

    segments, labels, use_group = _load_labeled_segments(
        args.data,
        args.label_col,
        group_col=args.group_col,
    )
    if use_group:
        print(
            f"Using group-wise split on '{args.group_col}' "
            f"({len({str(s[args.group_col]) for s in segments})} groups)."
        )
    else:
        print(
            f"No column '{args.group_col}' in CSV; using stratified row split "
            "(segments from the same meeting may appear in train and validation)."
        )

    x_train, x_val, y_train, y_val = _split_train_val(
        segments,
        labels,
        args.group_col,
        use_group,
        test_size=args.test_size,
        random_state=args.random_state,
    )

    model_bundle = train_classifier(x_train, y_train)
    train_probs = predict_probabilities(x_train, model_bundle)
    val_probs = predict_probabilities(x_val, model_bundle)

    threshold_metrics = calibrate_threshold(
        labels=y_val,
        probabilities=val_probs,
        min_precision=args.min_precision,
    )
    threshold = threshold_metrics["threshold"]
    val_metrics = _evaluate(y_val, val_probs, threshold=threshold)
    train_metrics = _evaluate(y_train, train_probs, threshold=threshold)
    gaps = _overfit_gaps(train_metrics, val_metrics)

    eval_metrics = {
        **val_metrics,
        "train_precision": train_metrics["precision"],
        "train_recall": train_metrics["recall"],
        "train_f1": train_metrics["f1"],
        "train_auc": train_metrics["auc"],
        **gaps,
        "calibrated_threshold": float(threshold),
        "threshold_precision": float(threshold_metrics["precision"]),
        "threshold_recall": float(threshold_metrics["recall"]),
        "threshold_f1": float(threshold_metrics["f1"]),
        "val_size": int(len(y_val)),
        "train_size": int(len(y_train)),
    }

    paths = save_model(
        model_bundle=model_bundle,
        threshold=threshold,
        model_dir=args.model_dir,
        metrics=eval_metrics,
    )

    print("Training complete.")
    print(f"Train samples: {len(y_train)} | Validation samples: {len(y_val)}")
    print(
        "Validation metrics (threshold calibrated on validation): "
        f"P={eval_metrics['precision']:.3f}, "
        f"R={eval_metrics['recall']:.3f}, "
        f"F1={eval_metrics['f1']:.3f}, "
        f"AUC={eval_metrics['auc']:.3f}"
    )
    print(
        "Train metrics (same threshold, overfitting check): "
        f"P={eval_metrics['train_precision']:.3f}, "
        f"R={eval_metrics['train_recall']:.3f}, "
        f"F1={eval_metrics['train_f1']:.3f}, "
        f"AUC={eval_metrics['train_auc']:.3f}"
    )
    print(
        f"Gaps (train minus val): dF1={gaps['overfit_f1_gap']:+.3f}, "
        f"dAUC={gaps['overfit_auc_gap']:+.3f}"
    )
    print(f"Overfitting note: {_overfit_note(gaps)}")
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
