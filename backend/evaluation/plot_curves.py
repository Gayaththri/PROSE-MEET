"""Plot evaluation curves from benchmark result files."""

import argparse
import csv
import json
import os
import re
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix, precision_recall_curve

try:
    from pipeline.importance_model import load_model, predict_probabilities
except Exception:
    load_model = None
    predict_probabilities = None


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_label(value) -> Optional[int]:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "important", "high"}:
        return 1
    if text in {"0", "false", "no", "not_important", "low"}:
        return 0
    return None


def _semantic_score(text: str) -> float:
    kws = ["need to", "must", "should", "decide", "decision", "deadline", "budget", "plan", "action item"]
    txt = (text or "").strip().lower()
    words = [w for w in re.split(r"\s+", txt) if w]
    s = min(0.35, len(words) / 20.0)
    s += min(0.45, 0.15 * sum(1 for kw in kws if kw in txt))
    if re.search(r"\b\d+(?:[\.,]\d+)?\b", txt):
        s += 0.12
    if len(words) < 4:
        s -= 0.22
    return max(0.0, min(1.5, s))


def _load_eval_rows(path: str, label_col: str):
    rows = []
    labels = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or label_col not in set(reader.fieldnames):
            raise ValueError(f"CSV must include label column: {label_col}")
        for idx, row in enumerate(reader):
            text = (row.get("text") or "").strip()
            lab = _to_label(row.get(label_col))
            if not text or lab is None:
                continue
            start = _to_float(row.get("start"), idx)
            end = _to_float(row.get("end"), start + _to_float(row.get("duration"), 1.0))
            rows.append(
                {
                    "text": text,
                    "pitch_variance": _to_float(row.get("pitch_variance"), 0.0),
                    "mean_energy": _to_float(row.get("mean_energy"), 0.0),
                    "pause_ratio": _to_float(row.get("pause_ratio"), 0.0),
                    "start": start,
                    "end": end,
                }
            )
            labels.append(lab)
    if not rows:
        raise ValueError("No valid rows with labels found.")
    return rows, np.array(labels, dtype=int)


def _norm(arr: np.ndarray) -> np.ndarray:
    if arr.size == 0:
        return arr
    lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)
    return ((arr - lo) / (hi - lo)).astype(np.float32)


def _scores_for_modes(rows: List[Dict], model_dir: Optional[str]):
    sem = np.array([_semantic_score(r["text"]) for r in rows], dtype=np.float32)
    sem = _norm(sem)

    pitch = np.array([r["pitch_variance"] for r in rows], dtype=np.float32)
    energy = np.array([r["mean_energy"] for r in rows], dtype=np.float32)
    pause = np.array([r["pause_ratio"] for r in rows], dtype=np.float32)

    pm, ps = float(np.mean(pitch)), float(np.std(pitch) + 1e-6)
    em, es = float(np.mean(energy)), float(np.std(energy) + 1e-6)
    qm, qs = float(np.mean(pause)), float(np.std(pause) + 1e-6)
    pros = np.abs((pitch - pm) / ps) * 0.4 + np.abs((energy - em) / es) * 0.4 + np.abs((pause - qm) / qs) * 0.2
    pros = _norm(pros.astype(np.float32))

    out = {
        "text_only": sem,
        "prosody_only": pros,
        "full": _norm((0.6 * sem + 0.4 * pros).astype(np.float32)),
    }
    if load_model is not None and predict_probabilities is not None:
        bundle = load_model(model_dir=model_dir)
        if bundle is not None:
            out["supervised"] = predict_probabilities(rows, bundle)
    return out


def main():
    parser = argparse.ArgumentParser(description="Generate PR curves and confusion matrices.")
    parser.add_argument("--data", required=True, help="Labeled CSV path")
    parser.add_argument("--label-col", default="label", help="Label column")
    parser.add_argument("--model-dir", default=None, help="Optional supervised model directory")
    parser.add_argument("--output-dir", default="results/curves", help="Output directory")
    args = parser.parse_args()

    rows, y_true = _load_eval_rows(args.data, args.label_col)
    mode_scores = _scores_for_modes(rows, model_dir=args.model_dir)
    os.makedirs(args.output_dir, exist_ok=True)

    # PR curve
    plt.figure(figsize=(7, 5))
    summary = {}
    for mode, scores in mode_scores.items():
        p, r, th = precision_recall_curve(y_true, scores)
        plt.plot(r, p, label=mode)
        # threshold chosen by max F1 over PR points
        best_t = 0.5
        best_f1 = -1.0
        usable = len(th)
        for i in range(usable):
            pi = float(p[i])
            ri = float(r[i])
            f1 = 0.0 if (pi + ri) == 0 else 2 * pi * ri / (pi + ri)
            if f1 > best_f1:
                best_f1 = f1
                best_t = float(th[i])

        y_pred = (scores >= best_t).astype(int)
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        summary[mode] = {
            "threshold": best_t,
            "best_f1": best_f1,
            "confusion_matrix": cm.tolist(),
        }

        # confusion matrix figure per mode
        fig, ax = plt.subplots(figsize=(4, 4))
        im = ax.imshow(cm, cmap="Blues")
        ax.set_title(f"Confusion Matrix - {mode}")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["0", "1"])
        ax.set_yticklabels(["0", "1"])
        for i in range(2):
            for j in range(2):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        fig.savefig(os.path.join(args.output_dir, f"confusion_{mode}.png"), dpi=160)
        plt.close(fig)

    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Precision-Recall Curves")
    plt.legend()
    plt.tight_layout()
    pr_path = os.path.join(args.output_dir, "pr_curves.png")
    plt.savefig(pr_path, dpi=180)
    plt.close()

    with open(os.path.join(args.output_dir, "curves_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Generated:")
    print(f"- {pr_path}")
    for mode in summary.keys():
        print(f"- {os.path.join(args.output_dir, f'confusion_{mode}.png')}")
    print(f"- {os.path.join(args.output_dir, 'curves_summary.json')}")


if __name__ == "__main__":
    main()
