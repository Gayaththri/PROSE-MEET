import argparse
import csv
import json
import os
import re
from typing import Dict, List, Tuple

import numpy as np
from sklearn.metrics import precision_recall_curve, precision_recall_fscore_support, roc_auc_score

from pipeline.importance_model import load_model, predict_probabilities


_SEMANTIC_KEYWORDS = [
    "need to",
    "must",
    "should",
    "decide",
    "decision",
    "finalize",
    "finalise",
    "deadline",
    "due date",
    "budget",
    "plan",
    "design",
    "requirement",
    "action item",
    "follow up",
    "deliverable",
]

_LOW_INFORMATION_PHRASES = frozenset(
    s.strip().lower()
    for s in (
        "i don't know",
        "dont know",
        "okay",
        "ok",
        "yeah",
        "yes",
        "no",
        "right",
        "sure",
        "hmm",
        "uh",
        "um",
    )
)


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_label(value: str) -> int:
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "important", "high"}:
        return 1
    return 0


def _safe_norm(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    vmin = float(values.min())
    vmax = float(values.max())
    if vmax <= vmin:
        return np.zeros_like(values, dtype=np.float32)
    return ((values - vmin) / (vmax - vmin)).astype(np.float32)


def _calibrate_threshold(y_true: np.ndarray, probs: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, probs)
    if len(thresholds) == 0:
        return 0.5
    best_f1 = -1.0
    best_t = 0.5
    for i, t in enumerate(thresholds):
        p = float(precision[i])
        r = float(recall[i])
        f1 = 0.0 if (p + r) == 0 else (2.0 * p * r) / (p + r)
        if f1 > best_f1:
            best_f1 = f1
            best_t = float(t)
    return best_t


def _metrics(y_true: np.ndarray, probs: np.ndarray, threshold: float) -> Dict[str, float]:
    preds = (probs >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, preds, average="binary", zero_division=0
    )
    auc = roc_auc_score(y_true, probs) if len(set(y_true.tolist())) > 1 else 0.0
    tp = int(np.sum((preds == 1) & (y_true == 1)))
    fp = int(np.sum((preds == 1) & (y_true == 0)))
    tn = int(np.sum((preds == 0) & (y_true == 0)))
    fn = int(np.sum((preds == 0) & (y_true == 1)))
    return {
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "auc": float(auc),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def _semantic_score(text: str) -> float:
    txt = (text or "").strip().lower()
    words = [w for w in re.split(r"\s+", txt) if w]
    n_words = len(words)

    score = min(0.35, n_words / 20.0)
    kw_hits = sum(1 for kw in _SEMANTIC_KEYWORDS if kw in txt)
    score += min(0.45, 0.15 * kw_hits)
    if re.search(r"\b\d+(?:[\.,]\d+)?\b", txt):
        score += 0.12
    if n_words < 4:
        score -= 0.22
    if n_words <= 2:
        score -= 0.12
    if txt in _LOW_INFORMATION_PHRASES:
        score -= 0.20
    return float(max(0.0, min(1.5, score)))


def _prosody_scores(rows: List[Dict[str, str]]) -> np.ndarray:
    pitch = np.array([_to_float(r.get("pitch_variance"), 0.0) for r in rows], dtype=np.float32)
    energy = np.array([_to_float(r.get("mean_energy"), 0.0) for r in rows], dtype=np.float32)
    pause = np.array([_to_float(r.get("pause_ratio"), 0.0) for r in rows], dtype=np.float32)

    pm, ps = float(np.mean(pitch)), float(np.std(pitch) + 1e-6)
    em, es = float(np.mean(energy)), float(np.std(energy) + 1e-6)
    qm, qs = float(np.mean(pause)), float(np.std(pause) + 1e-6)

    z_pitch = np.abs((pitch - pm) / ps)
    z_energy = np.abs((energy - em) / es)
    z_pause = np.abs((pause - qm) / qs)
    combined = (0.4 * z_pitch) + (0.4 * z_energy) + (0.2 * z_pause)
    return _safe_norm(combined.astype(np.float32))


def _load_rows(csv_path: str, label_col: str) -> List[Dict[str, str]]:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if label_col not in (reader.fieldnames or []):
            raise ValueError(f"Label column '{label_col}' is not present.")
        rows = [r for r in reader if (r.get("text") or "").strip()]
    if not rows:
        raise ValueError("No valid rows with text found in dataset.")
    return rows


def main():
    parser = argparse.ArgumentParser(description="Run Gap 1 ablation study.")
    parser.add_argument("--data", required=True, help="Path to labeled CSV")
    parser.add_argument("--label-col", default="label", help="Label column name")
    parser.add_argument("--model-dir", default=None, help="Model directory for optional supervised row")
    parser.add_argument("--output-json", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    rows = _load_rows(args.data, args.label_col)
    y_true = np.array([_parse_label(r.get(args.label_col)) for r in rows], dtype=int)
    if len(set(y_true.tolist())) < 2:
        raise ValueError("Need both positive and negative labels for ablation.")

    semantic = np.array([_semantic_score(r.get("text") or "") for r in rows], dtype=np.float32)
    semantic = _safe_norm(semantic)
    prosody = _prosody_scores(rows)
    fusion = _safe_norm((0.6 * semantic) + (0.4 * prosody))

    experiments = {}
    for name, probs in (
        ("prosody_only", prosody),
        ("semantics_only", semantic),
        ("fusion_rule_based", fusion),
    ):
        th = _calibrate_threshold(y_true, probs)
        experiments[name] = _metrics(y_true, probs, th)

    bundle = load_model(model_dir=args.model_dir)
    if bundle is not None:
        segments = []
        for idx, r in enumerate(rows):
            start = _to_float(r.get("start"), float(idx))
            end = _to_float(r.get("end"), start + _to_float(r.get("duration"), 1.0))
            segments.append(
                {
                    "text": r.get("text") or "",
                    "pitch_variance": _to_float(r.get("pitch_variance"), 0.0),
                    "mean_energy": _to_float(r.get("mean_energy"), 0.0),
                    "pause_ratio": _to_float(r.get("pause_ratio"), 0.0),
                    "start": start,
                    "end": end,
                }
            )
        sup_probs = predict_probabilities(segments, bundle)
        sup_th = float(bundle.get("threshold", 0.5))
        experiments["supervised_model"] = _metrics(y_true, sup_probs, sup_th)

    output = {
        "samples": int(len(y_true)),
        "experiments": experiments,
    }

    print("=== Gap 1 Ablation ===")
    print(f"Samples: {len(y_true)}")
    for key, m in experiments.items():
        print(
            f"[{key}] "
            f"P={m['precision']:.3f} "
            f"R={m['recall']:.3f} "
            f"F1={m['f1']:.3f} "
            f"AUC={m['auc']:.3f} "
            f"T={m['threshold']:.3f}"
        )

    if args.output_json:
        out_dir = os.path.dirname(args.output_json)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"Saved JSON: {args.output_json}")


if __name__ == "__main__":
    main()
