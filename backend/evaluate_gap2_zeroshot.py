"""Evaluate GAP2 using zero-shot domain labeling outputs."""

import argparse
import csv
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import train_test_split

from pipeline.domain import apply_domain_adaptation, detect_domain
from pipeline.importance_model import calibrate_threshold, predict_probabilities, train_classifier


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _parse_binary_label(value: Any) -> Optional[int]:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "important", "high"}:
        return 1
    if text in {"0", "false", "no", "not_important", "low"}:
        return 0
    return None


def _normalise_domain(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    aliases = {
        "corp": "corporate",
        "business": "corporate",
        "education": "academic",
        "healthcare": "medical",
        "health": "medical",
    }
    return aliases.get(text, text)


def _get_column(row: Dict[str, str], names: List[str]) -> Optional[str]:
    for name in names:
        if name in row:
            return row.get(name)
    return None


def _row_to_segment(row: Dict[str, str], fallback_idx: int) -> Dict[str, Any]:
    start = _to_float(row.get("start"), float(fallback_idx))
    end = _to_float(row.get("end"), start + _to_float(row.get("duration"), 1.0))
    if end < start:
        end = start
    return {
        "text": (row.get("text") or "").strip(),
        "pitch_variance": _to_float(row.get("pitch_variance"), 0.0),
        "mean_energy": _to_float(row.get("mean_energy"), 0.0),
        "pause_ratio": _to_float(row.get("pause_ratio"), 0.0),
        "start": start,
        "end": end,
    }


def _load_rows(csv_path: str) -> List[Dict[str, str]]:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Dataset not found: {csv_path}")
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV header missing.")
        required = {"text"}
        missing = [c for c in required if c not in set(reader.fieldnames)]
        if missing:
            raise ValueError(f"CSV missing required column(s): {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError("CSV has no data rows.")
    return rows


def _prepare_labeled(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    prepared = []
    for idx, row in enumerate(rows):
        label = _parse_binary_label(_get_column(row, ["label", "importance_label", "important"]))
        domain = _normalise_domain(_get_column(row, ["true_domain", "domain", "domain_label"]))
        meeting_id = _get_column(row, ["meeting_id", "conversation_id", "session_id"]) or f"row_{idx}"
        seg = _row_to_segment(row, idx)
        if not seg["text"] or label is None or not domain:
            continue
        prepared.append(
            {
                "segment": seg,
                "label": int(label),
                "domain": domain,
                "meeting_id": meeting_id,
            }
        )
    if not prepared:
        raise ValueError(
            "No valid rows found. Ensure text + label + true_domain/domain + meeting_id fields are present."
        )
    return prepared


def _metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    return {"precision": float(precision), "recall": float(recall), "f1": float(f1), "samples": int(len(y_true))}


def _meeting_domain_results(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped = defaultdict(list)
    for item in items:
        grouped[item["meeting_id"]].append(item["segment"])
    out = {}
    for meeting_id, transcript in grouped.items():
        ordered = sorted(transcript, key=lambda s: float(s.get("start", 0.0) or 0.0))
        out[meeting_id] = detect_domain(transcript=ordered)
    return out


def _predict_without_adaptation(probs: np.ndarray, threshold: float) -> List[int]:
    return (probs >= float(threshold)).astype(int).tolist()


def _predict_with_adaptation(
    items: List[Dict[str, Any]],
    probs: np.ndarray,
    meeting_domain: Dict[str, Dict[str, Any]],
    threshold: float,
) -> List[int]:
    preds = []
    for idx, item in enumerate(items):
        base_score = float(probs[idx])
        seg = item["segment"].copy()
        seg["importance_score"] = base_score
        domain_result = meeting_domain.get(item["meeting_id"], {"predicted_domain": "corporate", "confidence": 0.5})
        adapted = apply_domain_adaptation([seg], domain_result=domain_result)
        adapted_score = float(adapted[0].get("importance_score", base_score)) if adapted else base_score
        preds.append(1 if adapted_score >= float(threshold) else 0)
    return preds


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gap 2 zero-shot evaluation: train on corporate only, test cross-domain with/without adaptation."
    )
    parser.add_argument("--data", required=True, help="Path to labeled CSV (must include text, label, true_domain/domain).")
    parser.add_argument("--train-domain", default="corporate", help="Single source domain for training (default: corporate).")
    parser.add_argument("--test-size", type=float, default=0.2, help="Corporate holdout ratio for same-domain baseline.")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed.")
    parser.add_argument("--output-json", default=None, help="Optional path to write JSON results.")
    args = parser.parse_args()

    rows = _load_rows(args.data)
    prepared = _prepare_labeled(rows)

    train_domain = _normalise_domain(args.train_domain) or "corporate"
    train_pool = [r for r in prepared if r["domain"] == train_domain]
    cross_domain = [r for r in prepared if r["domain"] != train_domain]
    if len(train_pool) < 10:
        raise ValueError(f"Not enough training rows for domain '{train_domain}'. Found {len(train_pool)}.")
    if not cross_domain:
        raise ValueError("No non-training-domain rows found for zero-shot test.")

    x = [r["segment"] for r in train_pool]
    y = [r["label"] for r in train_pool]
    if len(set(y)) < 2:
        raise ValueError("Training domain labels must contain both positive and negative examples.")

    x_train, x_test_corp, y_train, y_test_corp = train_test_split(
        x,
        y,
        test_size=float(args.test_size),
        random_state=int(args.random_state),
        stratify=y,
    )
    model = train_classifier(x_train, y_train)

    probs_corp = predict_probabilities(x_test_corp, model)
    threshold_info = calibrate_threshold(y_test_corp, probs_corp)
    threshold = float(threshold_info["threshold"])
    pred_corp = _predict_without_adaptation(probs_corp, threshold)
    same_domain_metrics = _metrics(y_test_corp, pred_corp)

    x_cross = [r["segment"] for r in cross_domain]
    y_cross = [r["label"] for r in cross_domain]
    probs_cross = predict_probabilities(x_cross, model)
    pred_cross_no = _predict_without_adaptation(probs_cross, threshold)
    cross_no_metrics = _metrics(y_cross, pred_cross_no)

    meeting_domain = _meeting_domain_results(cross_domain)
    pred_cross_yes = _predict_with_adaptation(cross_domain, probs_cross, meeting_domain, threshold)
    cross_yes_metrics = _metrics(y_cross, pred_cross_yes)

    domains = sorted({r["domain"] for r in cross_domain})
    results = {
        "setup": {
            "train_domain": train_domain,
            "test_domains": domains,
            "train_samples": len(x_train),
            "same_domain_test_samples": len(y_test_corp),
            "cross_domain_test_samples": len(y_cross),
            "threshold": threshold,
        },
        "scenarios": {
            "same_domain_baseline": same_domain_metrics,
            "cross_domain_no_adaptation": cross_no_metrics,
            "cross_domain_with_adaptation": cross_yes_metrics,
        },
        "improvement": {
            "cross_domain_f1_delta": float(cross_yes_metrics["f1"] - cross_no_metrics["f1"]),
            "cross_domain_precision_delta": float(cross_yes_metrics["precision"] - cross_no_metrics["precision"]),
            "cross_domain_recall_delta": float(cross_yes_metrics["recall"] - cross_no_metrics["recall"]),
        },
    }

    print("=== Gap 2 Zero-Shot Generalisation ===")
    print(f"Train domain only: {train_domain}")
    print(f"Cross-domain test set: {', '.join(domains)}")
    print(
        f"Corporate baseline -> P={same_domain_metrics['precision']:.3f}, "
        f"R={same_domain_metrics['recall']:.3f}, F1={same_domain_metrics['f1']:.3f}"
    )
    print(
        f"Other domain (no adaptation) -> P={cross_no_metrics['precision']:.3f}, "
        f"R={cross_no_metrics['recall']:.3f}, F1={cross_no_metrics['f1']:.3f}"
    )
    print(
        f"Other domain (with adaptation) -> P={cross_yes_metrics['precision']:.3f}, "
        f"R={cross_yes_metrics['recall']:.3f}, F1={cross_yes_metrics['f1']:.3f}"
    )
    print(f"Cross-domain F1 improvement: {results['improvement']['cross_domain_f1_delta']:+.3f}")

    if args.output_json:
        os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Saved JSON: {args.output_json}")


if __name__ == "__main__":
    main()
