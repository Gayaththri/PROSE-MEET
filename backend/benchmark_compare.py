"""Compare benchmark outputs across experiment runs."""

import argparse
import json
from typing import Dict


def _load(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _summary_for_mode(payload: Dict, mode: str) -> Dict:
    return ((payload or {}).get(mode) or {}).get("summary") or {}


def _print_summary_table(mode: str, before: Dict, after: Dict) -> None:
    print(f"## {mode.title()} latency")
    print("| Metric | Before | After | Delta |")
    print("|---|---:|---:|---:|")
    keys = [
        "avg_elapsed_seconds",
        "avg_real_time_factor",
        "avg_seconds_per_minute_audio",
        "max_elapsed_seconds",
        "min_elapsed_seconds",
    ]
    for key in keys:
        before_value = float(before.get(key, 0.0) or 0.0)
        after_value = float(after.get(key, 0.0) or 0.0)
        delta = after_value - before_value
        print(f"| {key} | {before_value:.3f} | {after_value:.3f} | {delta:+.3f} |")
    print()


def _print_stage_table(mode: str, before: Dict, after: Dict) -> None:
    before_stages = before.get("avg_stage_seconds") or {}
    after_stages = after.get("avg_stage_seconds") or {}
    stage_names = sorted(set(before_stages.keys()) | set(after_stages.keys()))
    if not stage_names:
        return
    print(f"## {mode.title()} stages")
    print("| Stage | Before (s) | After (s) | Delta (s) |")
    print("|---|---:|---:|---:|")
    for stage_name in stage_names:
        before_value = float(before_stages.get(stage_name, 0.0) or 0.0)
        after_value = float(after_stages.get(stage_name, 0.0) or 0.0)
        delta = after_value - before_value
        print(f"| {stage_name} | {before_value:.3f} | {after_value:.3f} | {delta:+.3f} |")
    print()


def main():
    parser = argparse.ArgumentParser(description="Compare before/after benchmark_runtime JSON outputs.")
    parser.add_argument("--before", required=True, help="Path to baseline benchmark JSON")
    parser.add_argument("--after", required=True, help="Path to optimized benchmark JSON")
    args = parser.parse_args()

    before_payload = _load(args.before)
    after_payload = _load(args.after)

    for mode in ("cold", "warm"):
        before_summary = _summary_for_mode(before_payload, mode)
        after_summary = _summary_for_mode(after_payload, mode)
        if not before_summary and not after_summary:
            continue
        _print_summary_table(mode, before_summary, after_summary)
        _print_stage_table(mode, before_summary, after_summary)


if __name__ == "__main__":
    main()
