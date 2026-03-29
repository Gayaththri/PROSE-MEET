"""Build consolidated tables from experiment outputs."""

import argparse
import json
import os
from datetime import datetime, timezone


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fmt(x):
    if x is None:
        return "-"
    if isinstance(x, (int, float)):
        return f"{x:.3f}" if isinstance(x, float) else str(x)
    return str(x)


def build_markdown(gap_eval: dict, benchmark: dict, ablation: dict = None, runtime: dict = None) -> str:
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    gap2 = gap_eval.get("gap2") or {}
    rule = benchmark.get("rule_based") or {}
    sup = benchmark.get("supervised") or {}

    lines = []
    lines.append("# Chapter 8 Results Tables")
    lines.append("")
    lines.append(f"_Generated at: {ts}_")
    gap1 = gap_eval.get("gap1") or {}
    if not gap1 or gap1.get("samples") is None:
        lines.append("")
        lines.append("> **Note:** Gap 1 importance metrics show \"-\" until a labeled eval dataset is available and (for full comparison) a trained supervised model exists. See `backend/data/templates/README.md` and backend README.")
        lines.append("")
    lines.append("## Gap 1 Evaluation")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Samples | {_fmt(gap1.get('samples'))} |")
    lines.append(f"| Threshold | {_fmt(gap1.get('threshold'))} |")
    lines.append(f"| Precision | {_fmt(gap1.get('precision'))} |")
    lines.append(f"| Recall | {_fmt(gap1.get('recall'))} |")
    lines.append(f"| F1 | {_fmt(gap1.get('f1'))} |")
    lines.append(f"| AUC | {_fmt(gap1.get('auc'))} |")
    lines.append("")
    lines.append("## Gap 2 Evaluation")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Meetings | {_fmt(gap2.get('meetings'))} |")
    lines.append(f"| Accuracy | {_fmt(gap2.get('accuracy'))} |")
    for k in sorted(gap2.keys()):
        if k.startswith("accuracy_") and k != "accuracy":
            lines.append(f"| {k} | {_fmt(gap2.get(k))} |")
    lines.append("")
    lines.append("## Benchmark: Rule-based vs Supervised")
    lines.append("")
    lines.append("| Method | Precision | Recall | F1 | AUC | Threshold |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(
        f"| Rule-based | {_fmt(rule.get('precision'))} | {_fmt(rule.get('recall'))} | "
        f"{_fmt(rule.get('f1'))} | {_fmt(rule.get('auc'))} | {_fmt(benchmark.get('rule_threshold'))} |"
    )
    if sup:
        lines.append(
            f"| Supervised | {_fmt(sup.get('precision'))} | {_fmt(sup.get('recall'))} | "
            f"{_fmt(sup.get('f1'))} | {_fmt(sup.get('auc'))} | {_fmt(sup.get('threshold'))} |"
        )
    else:
        lines.append("| Supervised | - | - | - | - | - |")
    lines.append("")

    if ablation:
        lines.append("## Gap 1 Ablation")
        lines.append("")
        lines.append("| Variant | Precision | Recall | F1 | AUC | Threshold | TP | FP | TN | FN |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        experiments = ablation.get("experiments") or {}
        for name in sorted(experiments.keys()):
            m = experiments[name] or {}
            lines.append(
                f"| {name} | {_fmt(m.get('precision'))} | {_fmt(m.get('recall'))} | {_fmt(m.get('f1'))} | "
                f"{_fmt(m.get('auc'))} | {_fmt(m.get('threshold'))} | {_fmt(m.get('tp'))} | {_fmt(m.get('fp'))} | "
                f"{_fmt(m.get('tn'))} | {_fmt(m.get('fn'))} |"
            )
        lines.append("")

    if runtime:
        lines.append("## Runtime Benchmark")
        lines.append("")
        summary = runtime.get("summary") or {}
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Files | {_fmt(summary.get('count'))} |")
        lines.append(f"| Avg elapsed seconds | {_fmt(summary.get('avg_elapsed_seconds'))} |")
        lines.append(f"| Avg real-time factor | {_fmt(summary.get('avg_real_time_factor'))} |")
        lines.append(f"| Avg seconds per minute audio | {_fmt(summary.get('avg_seconds_per_minute_audio'))} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build thesis-ready markdown results tables.")
    parser.add_argument("--gap-eval-json", required=True, help="Path to JSON from evaluate_gaps.py --output-json")
    parser.add_argument("--benchmark-json", required=True, help="Path to JSON from benchmark_importance_models.py --output-json")
    parser.add_argument("--ablation-json", default=None, help="Optional path to JSON from ablation_gap1.py --output-json")
    parser.add_argument("--runtime-json", default=None, help="Optional path to JSON from benchmark_runtime.py --output-json")
    parser.add_argument("--output-md", default="results/chapter8_results.md", help="Output markdown file path")
    args = parser.parse_args()

    gap_eval = _read_json(args.gap_eval_json)
    benchmark = _read_json(args.benchmark_json)
    ablation = _read_json(args.ablation_json) if args.ablation_json else None
    runtime = _read_json(args.runtime_json) if args.runtime_json else None

    md = build_markdown(gap_eval, benchmark, ablation=ablation, runtime=runtime)
    out_path = args.output_md
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
