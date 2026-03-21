import argparse
import csv
import json
import os
from typing import Dict, List


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_per_meeting(path: str) -> List[Dict]:
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "id": row.get("id"),
                    "split": row.get("split"),
                    "domain_true": row.get("domain_true"),
                    "domain_pred": row.get("domain_pred"),
                    "wer": _to_float(row.get("wer")),
                    "importance_f1": _to_float(row.get("importance_f1")),
                    "rougel_f1": _to_float(row.get("rougel_f1")),
                    "latency_seconds": _to_float(row.get("latency_seconds")),
                }
            )
    return rows


def _reason(row: Dict) -> str:
    reasons = []
    if row.get("wer") is not None and row["wer"] > 0.35:
        reasons.append("high ASR error")
    if row.get("importance_f1") is not None and row["importance_f1"] < 0.50:
        reasons.append("importance mismatch")
    if row.get("domain_true") and row.get("domain_pred") and row["domain_true"] != row["domain_pred"]:
        reasons.append("domain misclassification")
    if row.get("latency_seconds") is not None and row["latency_seconds"] > 120:
        reasons.append("high runtime latency")
    return ", ".join(reasons) if reasons else "general quality degradation"


def _fix_suggestion(row: Dict) -> str:
    if row.get("wer") is not None and row["wer"] > 0.35:
        return "Improve ASR model/domain prompt; inspect audio quality and VAD settings."
    if row.get("domain_true") and row.get("domain_pred") and row["domain_true"] != row["domain_pred"]:
        return "Increase domain-balanced training examples and add domain-specific terms."
    if row.get("importance_f1") is not None and row["importance_f1"] < 0.50:
        return "Expand hard-negative labels and recalibrate importance threshold."
    return "Inspect transcript-level alignment and tune context/reliability weighting."


def main():
    parser = argparse.ArgumentParser(description="Generate concise error-case report from per_meeting.csv")
    parser.add_argument("--per-meeting-csv", required=True, help="Path to per_meeting.csv")
    parser.add_argument("--output-dir", default=None, help="Optional output directory")
    parser.add_argument("--top-n", type=int, default=10, help="How many cases to output")
    args = parser.parse_args()

    rows = _load_per_meeting(args.per_meeting_csv)
    if not rows:
        raise ValueError("No rows found in per_meeting.csv")

    scored = []
    for r in rows:
        severity = 0.0
        if r.get("wer") is not None:
            severity += r["wer"]
        if r.get("importance_f1") is not None:
            severity += (1.0 - r["importance_f1"])
        if r.get("rougel_f1") is not None:
            severity += (1.0 - r["rougel_f1"]) * 0.5
        if r.get("domain_true") and r.get("domain_pred") and r["domain_true"] != r["domain_pred"]:
            severity += 0.5
        r2 = dict(r)
        r2["severity"] = severity
        scored.append(r2)

    scored.sort(key=lambda x: x["severity"], reverse=True)
    top = scored[: max(1, args.top_n)]

    cases = []
    bullets = []
    for row in top:
        reason = _reason(row)
        suggestion = _fix_suggestion(row)
        case = {
            "id": row.get("id"),
            "split": row.get("split"),
            "domain_true": row.get("domain_true"),
            "domain_pred": row.get("domain_pred"),
            "wer": row.get("wer"),
            "importance_f1": row.get("importance_f1"),
            "rougel_f1": row.get("rougel_f1"),
            "latency_seconds": row.get("latency_seconds"),
            "severity": row.get("severity"),
            "likely_reason": reason,
            "suggested_fix": suggestion,
        }
        cases.append(case)
        bullets.append(f"{case['id']}: {reason}; fix -> {suggestion}")

    output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.per_meeting_csv))
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "error_cases.json")
    md_path = os.path.join(output_dir, "error_cases.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"cases": cases, "bullets": bullets}, f, indent=2)

    lines = ["# Error Cases", ""]
    for b in bullets:
        lines.append(f"- {b}")
    lines.append("")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"saved={json_path}")
    print(f"saved={md_path}")


if __name__ == "__main__":
    main()
