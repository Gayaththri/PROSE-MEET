"""Benchmark runtime performance of pipeline variants."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Dict, List

from pipeline.run_gap1 import run_gap1
from pipeline.run_gap1_legacy import run_gap1_legacy
from pipeline.timing import TimingCollector


ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".mp4", ".mov", ".webm"}


def _resolve_audio_files(paths: List[str]) -> List[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                full = os.path.join(p, name)
                if os.path.isfile(full) and os.path.splitext(name)[1].lower() in ALLOWED_EXTENSIONS:
                    out.append(full)
        elif os.path.isfile(p):
            out.append(p)
    return out


def _extract_stage_seconds(snapshot: Dict) -> Dict[str, float]:
    stages = snapshot.get("stages") or {}
    return {
        name: float((values or {}).get("seconds", 0.0) or 0.0)
        for name, values in stages.items()
    }


def _aggregate(rows: List[Dict]) -> Dict:
    if not rows:
        return {"count": 0}
    elapsed = [float(r["elapsed_seconds"]) for r in rows]
    rtf = [float(r["real_time_factor"]) for r in rows]
    spm = [float(r["seconds_per_minute_audio"]) for r in rows]
    stage_names = sorted({stage for row in rows for stage in (row.get("stage_seconds") or {}).keys()})
    avg_stage_seconds = {}
    for stage_name in stage_names:
        values = [float((row.get("stage_seconds") or {}).get(stage_name, 0.0) or 0.0) for row in rows]
        avg_stage_seconds[stage_name] = round(sum(values) / len(values), 6)
    return {
        "count": len(rows),
        "avg_elapsed_seconds": round(sum(elapsed) / len(elapsed), 6),
        "avg_real_time_factor": round(sum(rtf) / len(rtf), 6),
        "avg_seconds_per_minute_audio": round(sum(spm) / len(spm), 6),
        "max_elapsed_seconds": round(max(elapsed), 6),
        "min_elapsed_seconds": round(min(elapsed), 6),
        "avg_stage_seconds": avg_stage_seconds,
    }


def _runner_for_name(pipeline_name: str):
    if pipeline_name == "legacy":
        return run_gap1_legacy
    return run_gap1


def _measure_once(path: str, pipeline_name: str, save_result_path: str | None = None) -> Dict:
    collector = TimingCollector()
    t0 = time.perf_counter()
    result = _runner_for_name(pipeline_name)(path, timing_collector=collector)
    elapsed = float(time.perf_counter() - t0)
    duration = float(result.get("duration_seconds", 0.0) or 0.0)
    rtf = elapsed / duration if duration > 0 else 0.0
    spm = elapsed / (duration / 60.0) if duration > 0 else 0.0
    timing_snapshot = collector.snapshot()
    row = {
        "file": path,
        "duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 6),
        "real_time_factor": round(rtf, 6),
        "seconds_per_minute_audio": round(spm, 6),
        "transcript_segments": len(result.get("transcript") or []),
        "highlights": len(result.get("highlights") or []),
        "pipeline": pipeline_name,
        "stage_seconds": _extract_stage_seconds(timing_snapshot),
        "timings": timing_snapshot,
    }
    if save_result_path:
        os.makedirs(os.path.dirname(save_result_path), exist_ok=True)
        with open(save_result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        row["result_path"] = save_result_path
    return row


def _child_run(path: str, pipeline_name: str, save_result_path: str | None = None) -> Dict:
    payload = _measure_once(path, pipeline_name=pipeline_name, save_result_path=save_result_path)
    print(json.dumps(payload))
    return payload


def _run_cold(path: str, pipeline_name: str, save_results_dir: str | None = None) -> Dict:
    child_result_path = None
    if save_results_dir:
        os.makedirs(save_results_dir, exist_ok=True)
        child_result_path = os.path.join(
            save_results_dir,
            f"{os.path.splitext(os.path.basename(path))[0]}_cold_result.json",
        )
    command = [sys.executable, __file__, "--child-run", path]
    if child_result_path:
        command.extend(["--child-save-result", child_result_path])
    command.extend(["--pipeline", pipeline_name])
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = (completed.stdout or "").strip().splitlines()
    if not stdout:
        raise RuntimeError("Cold benchmark child process did not return JSON output.")
    return json.loads(stdout[-1])


def _run_warm(path: str, pipeline_name: str, warm_runs: int, save_results_dir: str | None = None) -> Dict:
    warmup_result_path = None
    if save_results_dir:
        os.makedirs(save_results_dir, exist_ok=True)
        warmup_result_path = os.path.join(
            save_results_dir,
            f"{os.path.splitext(os.path.basename(path))[0]}_warmup_result.json",
        )
    warmup = _measure_once(path, pipeline_name=pipeline_name, save_result_path=warmup_result_path)
    measured_rows = []
    for run_idx in range(warm_runs):
        result_path = None
        if save_results_dir:
            result_path = os.path.join(
                save_results_dir,
                f"{os.path.splitext(os.path.basename(path))[0]}_warm_run_{run_idx + 1}.json",
            )
        measured_rows.append(_measure_once(path, pipeline_name=pipeline_name, save_result_path=result_path))
    return {
        "warmup": warmup,
        "files": measured_rows,
        "summary": _aggregate(measured_rows),
    }


def _print_section(label: str, payload: Dict) -> None:
    rows = payload.get("files") or []
    print(f"=== {label} ===")
    for row in rows:
        print(
            f"{os.path.basename(row['file'])} | "
            f"duration={row['duration_seconds']:.1f}s | elapsed={row['elapsed_seconds']:.1f}s | "
            f"RTF={row['real_time_factor']:.2f} | sec/min_audio={row['seconds_per_minute_audio']:.1f}"
        )
        top_stages = sorted(
            (row.get("stage_seconds") or {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        if top_stages:
            formatted = ", ".join(f"{name}={seconds:.3f}s" for name, seconds in top_stages)
            print(f"  top_stages: {formatted}")
    summary = payload.get("summary") or {}
    if summary:
        print("---")
        print(
            f"Files={summary.get('count', 0)} | "
            f"avg_elapsed={summary.get('avg_elapsed_seconds', 0.0):.1f}s | "
            f"avg_RTF={summary.get('avg_real_time_factor', 0.0):.2f} | "
            f"avg_sec/min_audio={summary.get('avg_seconds_per_minute_audio', 0.0):.1f}"
        )


def main():
    parser = argparse.ArgumentParser(description="Benchmark end-to-end runtime for Gap 1 pipeline.")
    parser.add_argument("--inputs", nargs="+", help="One or more audio files and/or directories containing audio files")
    parser.add_argument("--mode", choices=["cold", "warm", "both"], default="both")
    parser.add_argument("--pipeline", choices=["current", "legacy"], default="current")
    parser.add_argument("--warm-runs", type=int, default=1, help="Measured warm runs per file after a warmup pass")
    parser.add_argument("--output-json", default=None, help="Optional output JSON path")
    parser.add_argument("--save-results-dir", default=None, help="Optional directory to save result payloads per run")
    parser.add_argument("--child-run", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--child-save-result", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child_run:
        _child_run(args.child_run, pipeline_name=args.pipeline, save_result_path=args.child_save_result)
        return

    if not args.inputs:
        raise ValueError("--inputs is required unless --child-run is used.")

    files = _resolve_audio_files(args.inputs)
    if not files:
        raise FileNotFoundError("No audio files found from provided inputs.")

    payload = {"mode": args.mode, "pipeline": args.pipeline}

    if args.mode in ("cold", "both"):
        cold_rows = [_run_cold(path, pipeline_name=args.pipeline, save_results_dir=args.save_results_dir) for path in files]
        payload["cold"] = {"files": cold_rows, "summary": _aggregate(cold_rows)}
        _print_section("Cold Runs", payload["cold"])

    if args.mode in ("warm", "both"):
        warm_rows = []
        warmup_rows = []
        for path in files:
            warm_payload = _run_warm(
                path,
                pipeline_name=args.pipeline,
                warm_runs=max(1, args.warm_runs),
                save_results_dir=args.save_results_dir,
            )
            warmup_rows.append(warm_payload["warmup"])
            warm_rows.extend(warm_payload["files"])
        payload["warm"] = {
            "warmups": warmup_rows,
            "files": warm_rows,
            "summary": _aggregate(warm_rows),
        }
        _print_section("Warm Runs", payload["warm"])

    if args.output_json:
        out_dir = os.path.dirname(args.output_json)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"Saved JSON: {args.output_json}")


if __name__ == "__main__":
    main()
