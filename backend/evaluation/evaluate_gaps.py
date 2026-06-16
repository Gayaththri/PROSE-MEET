"""Run and summarize GAP evaluation metrics."""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from pipeline.domain import detect_domain
from pipeline.importance_model import load_model, predict_probabilities


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


def _parse_binary_label(value: str) -> Optional[int]:
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "important", "high"}:
        return 1
    if text in {"0", "false", "no", "not_important", "low"}:
        return 0
    return None


def _normalise_domain(value: str) -> Optional[str]:
    text = (value or "").strip().lower()
    if not text:
        return None
    aliases = {
        "corp": "corporate",
        "business": "corporate",
        "academic": "academic",
        "education": "academic",
        "medical": "medical",
        "healthcare": "medical",
        "health": "medical",
    }
    return aliases.get(text, text)


def _get_column(row: Dict[str, str], names: List[str]) -> Optional[str]:
    for name in names:
        if name in row:
            return row.get(name)
    return None


def _load_rows(csv_path: str) -> List[Dict[str, str]]:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(
            f"Evaluation dataset not found: {csv_path}. "
            "Expected a CSV such as data/eval_dataset.csv with labeled rows."
        )
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV header is missing.")
        required = {"text"}
        missing_required = [c for c in required if c not in set(reader.fieldnames)]
        if missing_required:
            raise ValueError(
                "CSV is missing required columns: "
                + ", ".join(missing_required)
                + ". Required at minimum: text."
            )
        rows = list(reader)
        if not rows:
            raise ValueError("CSV has no data rows.")
        return rows


def _build_segments(rows: List[Dict[str, str]]) -> Tuple[List[Dict], List[int]]:
    segments = []
    labels = []
    for i, row in enumerate(rows):
        text = (row.get("text") or "").strip()
        if not text:
            continue

        label_raw = _get_column(row, ["label", "importance_label", "important"])
        label = _parse_binary_label(label_raw)
        if label is None:
            continue

        start = _to_float(row.get("start"), float(i))
        end = _to_float(row.get("end"), start + _to_float(row.get("duration"), 1.0))
        if end < start:
            end = start

        seg = {
            "text": text,
            "pitch_variance": _to_float(row.get("pitch_variance"), 0.0),
            "mean_energy": _to_float(row.get("mean_energy"), 0.0),
            "pause_ratio": _to_float(row.get("pause_ratio"), 0.0),
            "start": start,
            "end": end,
        }
        segments.append(seg)
        labels.append(label)

    if not segments:
        label_cols = {"label", "importance_label", "important"}
        present = sorted(label_cols & set(rows[0].keys())) if rows else []
        if not present:
            raise ValueError(
                "No label column found. Add one of: label, importance_label, important."
            )
        raise ValueError(
            "No valid importance rows found. Ensure rows include non-empty text and valid binary labels."
        )
    if len(set(labels)) < 2:
        raise ValueError("Importance labels must contain both positive and negative examples.")
    return segments, labels


def evaluate_gap1_importance(rows: List[Dict[str, str]], model_dir: Optional[str]) -> Dict[str, float]:
    segments, y_true = _build_segments(rows)
    bundle = load_model(model_dir=model_dir)
    if bundle is None:
        raise FileNotFoundError(
            "No trained model found for Gap 1 evaluation. Train the model first."
        )

    probs = predict_probabilities(segments, bundle)
    threshold = float(bundle.get("threshold", 0.5))
    preds = (probs >= threshold).astype(int)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, preds, average="binary", zero_division=0
    )
    auc = roc_auc_score(y_true, probs) if len(set(y_true)) > 1 else 0.0
    return {
        "samples": float(len(y_true)),
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "auc": float(auc),
    }


def evaluate_gap2_domain(rows: List[Dict[str, str]]) -> Dict[str, float]:
    grouped = defaultdict(list)
    truth = {}

    for i, row in enumerate(rows):
        meeting_id = _get_column(row, ["meeting_id", "conversation_id", "session_id"]) or f"row_{i}"
        text = (row.get("text") or "").strip()
        if not text:
            continue

        start = _to_float(row.get("start"), float(i))
        end = _to_float(row.get("end"), start + _to_float(row.get("duration"), 1.0))
        if end < start:
            end = start

        grouped[meeting_id].append({"text": text, "start": start, "end": end})

        domain_raw = _get_column(row, ["true_domain", "domain", "domain_label"])
        domain = _normalise_domain(domain_raw or "")
        if domain:
            truth[meeting_id] = domain

    eval_ids = [mid for mid in grouped.keys() if mid in truth]
    if not eval_ids:
        raise ValueError(
            "No domain labels found. Add true_domain/domain column and meeting_id for Gap 2 evaluation."
        )

    correct = 0
    per_domain_total = defaultdict(int)
    per_domain_correct = defaultdict(int)

    for meeting_id in eval_ids:
        transcript = sorted(grouped[meeting_id], key=lambda x: x["start"])
        predicted = detect_domain(transcript=transcript).get("predicted_domain", "")
        actual = truth[meeting_id]
        per_domain_total[actual] += 1
        if predicted == actual:
            correct += 1
            per_domain_correct[actual] += 1

    accuracy = correct / max(len(eval_ids), 1)
    results = {
        "meetings": float(len(eval_ids)),
        "accuracy": float(accuracy),
    }
    for domain, total in sorted(per_domain_total.items()):
        dom_acc = per_domain_correct.get(domain, 0) / max(total, 1)
        results[f"accuracy_{domain}"] = float(dom_acc)
    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate Gap 1 (importance) and Gap 2 (domain).")
    parser.add_argument("--data", required=True, help="Path to labeled CSV")
    parser.add_argument("--model-dir", default=None, help="Model directory for Gap 1 classifier")
    parser.add_argument("--output-json", default=None, help="Optional path to write full metrics JSON")
    args = parser.parse_args()

    rows = _load_rows(args.data)
    output = {"dataset_rows": len(rows), "gap1": None, "gap2": None, "gap1_error": None, "gap2_error": None}

    print("=== PROSE-MEET Gap Evaluation ===")
    print(f"Dataset rows: {len(rows)}")

    try:
        gap1 = evaluate_gap1_importance(rows, model_dir=args.model_dir)
        output["gap1"] = gap1
        print("\n[Gap 1] Importance Detection")
        print(f"Samples: {int(gap1['samples'])}")
        print(f"Threshold: {gap1['threshold']:.3f}")
        print(
            f"Precision: {gap1['precision']:.3f} | "
            f"Recall: {gap1['recall']:.3f} | "
            f"F1: {gap1['f1']:.3f} | "
            f"AUC: {gap1['auc']:.3f}"
        )
    except Exception as exc:
        output["gap1_error"] = str(exc)
        print("\n[Gap 1] Importance Detection")
        print(f"Skipped: {exc}")

    try:
        gap2 = evaluate_gap2_domain(rows)
        output["gap2"] = gap2
        print("\n[Gap 2] Domain Adaptation")
        print(f"Meetings: {int(gap2['meetings'])}")
        print(f"Accuracy: {gap2['accuracy']:.3f}")
        domain_keys = sorted(k for k in gap2.keys() if k.startswith("accuracy_"))
        for key in domain_keys:
            print(f"{key}: {gap2[key]:.3f}")
    except Exception as exc:
        output["gap2_error"] = str(exc)
        print("\n[Gap 2] Domain Adaptation")
        print(f"Skipped: {exc}")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)


if __name__ == "__main__":
    main()
