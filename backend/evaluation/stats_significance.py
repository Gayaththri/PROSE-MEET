"""Run statistical significance tests on experiment results."""

import argparse
import csv
import json
import random
from typing import Dict, List, Tuple

from scipy.stats import ttest_rel, wilcoxon


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_metric_map(path: str, id_col: str, metric_col: str) -> Dict[str, float]:
    out = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Missing CSV header: {path}")
        needed = {id_col, metric_col}
        if not needed.issubset(set(reader.fieldnames)):
            raise ValueError(f"{path} must include columns: {id_col},{metric_col}")
        for row in reader:
            key = str(row.get(id_col, "")).strip()
            val = _to_float(row.get(metric_col))
            if key and val is not None:
                out[key] = val
    return out


def _paired_samples(
    csv_a: str,
    csv_b: str,
    id_col: str,
    metric_a: str,
    metric_b: str,
) -> Tuple[List[float], List[float], List[str]]:
    a_map = _load_metric_map(csv_a, id_col=id_col, metric_col=metric_a)
    b_map = _load_metric_map(csv_b, id_col=id_col, metric_col=metric_b)
    keys = sorted(set(a_map.keys()) & set(b_map.keys()))
    x = [a_map[k] for k in keys]
    y = [b_map[k] for k in keys]
    return x, y, keys


def _bootstrap_ci(diffs: List[float], iters: int = 5000, alpha: float = 0.05, seed: int = 42):
    if not diffs:
        return None, None
    rng = random.Random(seed)
    n = len(diffs)
    means = []
    for _ in range(iters):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    low_idx = int((alpha / 2) * len(means))
    high_idx = int((1 - alpha / 2) * len(means)) - 1
    return means[low_idx], means[high_idx]


def main():
    parser = argparse.ArgumentParser(description="Paired significance test between two result CSVs.")
    parser.add_argument("--csv-a", required=True, help="Baseline CSV")
    parser.add_argument("--csv-b", required=True, help="Improved CSV")
    parser.add_argument("--id-col", default="id", help="Meeting identifier column")
    parser.add_argument("--metric-a", required=True, help="Metric column in csv-a")
    parser.add_argument("--metric-b", required=True, help="Metric column in csv-b")
    parser.add_argument("--output-json", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    x, y, keys = _paired_samples(
        args.csv_a, args.csv_b, id_col=args.id_col, metric_a=args.metric_a, metric_b=args.metric_b
    )
    if not x:
        raise ValueError("No overlapping IDs with valid metric values.")

    diffs = [yb - xa for xa, yb in zip(x, y)]
    mean_diff = sum(diffs) / len(diffs)
    t_res = ttest_rel(y, x, nan_policy="omit")
    try:
        w_res = wilcoxon(y, x, zero_method="wilcox", correction=False)
        wilcoxon_stat = float(w_res.statistic)
        wilcoxon_p = float(w_res.pvalue)
    except Exception:
        wilcoxon_stat = None
        wilcoxon_p = None
    ci_low, ci_high = _bootstrap_ci(diffs)

    out = {
        "n_pairs": len(x),
        "mean_a": sum(x) / len(x),
        "mean_b": sum(y) / len(y),
        "mean_diff_b_minus_a": mean_diff,
        "ttest_rel_statistic": float(t_res.statistic),
        "ttest_rel_pvalue": float(t_res.pvalue),
        "wilcoxon_statistic": wilcoxon_stat,
        "wilcoxon_pvalue": wilcoxon_p,
        "bootstrap_95ci_diff": [ci_low, ci_high],
    }

    print("=== Significance Test (Paired) ===")
    print(f"pairs={out['n_pairs']}")
    print(f"mean_a={out['mean_a']:.4f} | mean_b={out['mean_b']:.4f} | mean_diff={out['mean_diff_b_minus_a']:.4f}")
    print(f"ttest p={out['ttest_rel_pvalue']:.6f}")
    if out["wilcoxon_pvalue"] is not None:
        print(f"wilcoxon p={out['wilcoxon_pvalue']:.6f}")
    print(f"bootstrap_95ci=[{out['bootstrap_95ci_diff'][0]:.4f}, {out['bootstrap_95ci_diff'][1]:.4f}]")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"saved={args.output_json}")


if __name__ == "__main__":
    main()
