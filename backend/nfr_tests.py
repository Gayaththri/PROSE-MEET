"""Run non-functional requirement checks for the backend."""

import argparse
import csv
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pipeline.run_gap1 import run_gap1


def _pick_audio_path(repo_root: str, preferred: Optional[str]) -> str:
    if preferred:
        p = preferred if os.path.isabs(preferred) else os.path.join(repo_root, preferred)
        if os.path.isfile(p):
            return p
    candidates = [
        os.path.join(repo_root, "data", "test_audio", "meeting.wav"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    rec_dir = os.path.join(repo_root, "data", "recordings")
    if os.path.isdir(rec_dir):
        for name in sorted(os.listdir(rec_dir)):
            p = os.path.join(rec_dir, name)
            if os.path.isfile(p) and name.lower().endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg")):
                return p
    raise FileNotFoundError(
        "No audio file found for NFR tests. Provide --audio-path or add data/test_audio/meeting.wav."
    )


def _latency_test(audio_path: str, max_rtf: float) -> Dict:
    t0 = time.perf_counter()
    result = run_gap1(audio_path)
    elapsed = time.perf_counter() - t0
    duration = float(result.get("duration_seconds", 0.0) or 0.0)
    rtf = elapsed / duration if duration > 0 else 0.0
    return {
        "test_id": "NFR_LATENCY_RTF",
        "name": "Latency / real-time factor check",
        "status": "PASS" if rtf <= max_rtf else "FAIL",
        "metric": "rtf",
        "value": rtf,
        "threshold": max_rtf,
        "notes": f"elapsed={elapsed:.2f}s duration={duration:.2f}s",
    }


def _concurrency_test(audio_path: str, workers: int, jobs: int, max_failure_rate: float) -> Dict:
    start = time.perf_counter()
    failures = 0
    durations = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(run_gap1, audio_path) for _ in range(jobs)]
        for fut in as_completed(futures):
            try:
                res = fut.result()
                durations.append(float(res.get("duration_seconds", 0.0) or 0.0))
            except Exception:
                failures += 1
    elapsed = time.perf_counter() - start
    failure_rate = failures / max(jobs, 1)
    return {
        "test_id": "NFR_CONCURRENCY",
        "name": f"Concurrency/load check ({jobs} jobs, {workers} workers)",
        "status": "PASS" if failure_rate <= max_failure_rate else "FAIL",
        "metric": "failure_rate",
        "value": failure_rate,
        "threshold": max_failure_rate,
        "notes": f"elapsed={elapsed:.2f}s completed={jobs-failures}/{jobs}",
    }


def _invalid_input_test(repo_root: str) -> Dict:
    missing = os.path.join(repo_root, "data", "test_audio", "__missing_input__.wav")
    ok = False
    try:
        run_gap1(missing)
    except Exception:
        ok = True
    return {
        "test_id": "NFR_INVALID_INPUT",
        "name": "Invalid-input resilience check",
        "status": "PASS" if ok else "FAIL",
        "metric": "raises_exception",
        "value": 1.0 if ok else 0.0,
        "threshold": 1.0,
        "notes": "Expected exception on non-existent audio path.",
    }


def _write_csv(path: str, rows: List[Dict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["test_id", "name", "status", "metric", "value", "threshold", "notes"],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _write_md(path: str, rows: List[Dict]):
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "PASS")
    failed = total - passed
    pass_rate = (passed / total * 100.0) if total else 0.0
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    lines = [
        "# Non-Functional Test Report",
        "",
        f"_Generated: {ts}_",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total tests | {total} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Pass rate (%) | {pass_rate:.2f} |",
        "",
        "## Test Results",
        "",
        "| Test ID | Name | Status | Metric | Value | Threshold | Notes |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['test_id']} | {r['name']} | {r['status']} | {r['metric']} | "
            f"{float(r['value']):.4f} | {float(r['threshold']):.4f} | {r['notes']} |"
        )
    lines.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Run non-functional tests and generate report artifacts.")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--audio-path", default=None, help="Optional audio path for runtime checks")
    parser.add_argument("--max-rtf", type=float, default=2.5, help="Pass threshold for real-time factor")
    parser.add_argument("--workers", type=int, default=2, help="Worker threads for concurrency test")
    parser.add_argument("--jobs", type=int, default=2, help="Number of jobs for concurrency test")
    parser.add_argument("--max-failure-rate", type=float, default=0.0, help="Allowed failure rate")
    parser.add_argument("--output-md", default="docs/nfr_test_report.md", help="Markdown report path")
    parser.add_argument("--output-csv", default="docs/nfr_test_results.csv", help="CSV report path")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    audio_path = _pick_audio_path(repo_root, args.audio_path)

    rows = [
        _latency_test(audio_path, max_rtf=args.max_rtf),
        _concurrency_test(
            audio_path,
            workers=max(1, args.workers),
            jobs=max(1, args.jobs),
            max_failure_rate=max(0.0, args.max_failure_rate),
        ),
        _invalid_input_test(repo_root),
    ]

    out_csv = os.path.join(repo_root, args.output_csv)
    out_md = os.path.join(repo_root, args.output_md)
    _write_csv(out_csv, rows)
    _write_md(out_md, rows)

    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "PASS")
    print(f"NFR tests complete: passed={passed}/{total}")
    print(f"Saved: {out_csv}")
    print(f"Saved: {out_md}")


if __name__ == "__main__":
    main()
