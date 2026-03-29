"""Build aggregate evaluation reports from JSON metrics."""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def write_markdown_summary(
    output_dir: str,
    dataset_summary: Dict[str, Any],
    aggregate: Dict[str, Any],
    ablation_rows: List[Dict[str, Any]],
    cross_domain_rows: List[Dict[str, Any]],
    error_bullets: List[str],
) -> str:
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path = os.path.join(output_dir, "RESULTS_SUMMARY.md")

    lines = []
    lines.append("# Evaluation Summary")
    lines.append("")
    lines.append(f"_Generated: {ts}_")
    lines.append("")
    lines.append("## Dataset Summary")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    for key in ("manifest", "meetings_total", "splits", "domains"):
        lines.append(f"| {key} | {dataset_summary.get(key, '-') } |")
    lines.append("")

    imp_keys = ("importance_precision", "importance_recall", "importance_f1")
    if all(aggregate.get(k) is None for k in imp_keys):
        lines.append("> **Note:** Importance metrics show \"-\" until reference data includes per-utterance importance labels (e.g. in transcript JSON). See `backend/data/templates/README.md`.")
        lines.append("")
    lines.append("## Aggregate Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for key in (
        "wer",
        "cer",
        "importance_precision",
        "importance_recall",
        "importance_f1",
        "rouge1_f1",
        "rouge2_f1",
        "rougel_f1",
        "domain_accuracy",
        "domain_macro_f1",
        "latency_seconds_avg",
    ):
        lines.append(f"| {key} | {_fmt(aggregate.get(key))} |")
    lines.append("")

    lines.append("## Ablation (Gap 1)")
    lines.append("")
    lines.append("| Mode | Importance Precision | Importance Recall | Importance F1 |")
    lines.append("|---|---:|---:|---:|")
    for row in ablation_rows:
        lines.append(
            f"| {row.get('mode')} | {_fmt(row.get('importance_precision'))} | "
            f"{_fmt(row.get('importance_recall'))} | {_fmt(row.get('importance_f1'))} |"
        )
    lines.append("")

    lines.append("## Cross-Domain Generalization")
    lines.append("")
    lines.append("| Group | Meetings | Importance F1 | Domain Accuracy |")
    lines.append("|---|---:|---:|---:|")
    for row in cross_domain_rows:
        lines.append(
            f"| {row.get('group')} | {_fmt(row.get('meetings'))} | "
            f"{_fmt(row.get('importance_f1'))} | {_fmt(row.get('domain_accuracy'))} |"
        )
    lines.append("")

    lines.append("## Error Analysis (Concise)")
    lines.append("")
    if error_bullets:
        for bullet in error_bullets:
            lines.append(f"- {bullet}")
    else:
        lines.append("- No significant error bullets generated (insufficient labeled error data).")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
