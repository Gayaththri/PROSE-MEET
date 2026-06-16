"""Orchestrate execution of all configured backend experiments."""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from typing import List


def _run(cmd: List[str], cwd: str):
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip())
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}")


def _pick_eval_dataset(repo_root: str) -> str:
    preferred = os.path.join(repo_root, "backend", "data", "eval_dataset.csv")
    if os.path.isfile(preferred):
        return preferred
    fallback = os.path.join(repo_root, "backend", "data", "eval_dataset_template.csv")
    if os.path.isfile(fallback):
        print(f"[warn] using fallback eval dataset: {fallback}")
        return fallback
    # Seed templates committed under backend/data/templates/
    seed = os.path.join(repo_root, "backend", "data", "templates", "eval_dataset_template.csv")
    if os.path.isfile(seed):
        print(f"[warn] using seed template: {seed}")
        return seed
    raise FileNotFoundError(
        "Missing eval dataset. Create backend/data/eval_dataset.csv, or copy from "
        "backend/data/templates/eval_dataset_template.csv. See backend/data/templates/README.md."
    )


def main():
    parser = argparse.ArgumentParser(description="Run all Chapter 8 experiment scripts and collect artifacts.")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--output-root", default="results", help="Root output folder")
    parser.add_argument("--model-dir", default=None, help="Optional model dir for supervised evaluation")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(repo_root, args.output_root, ts)
    os.makedirs(run_dir, exist_ok=True)

    eval_data = _pick_eval_dataset(repo_root)
    model_dir = args.model_dir

    gap_eval_json = os.path.join(run_dir, "gap_eval.json")
    benchmark_json = os.path.join(run_dir, "benchmark.json")
    ablation_json = os.path.join(run_dir, "ablation.json")

    py = sys.executable

    _run([py, "backend/evaluation/evaluate_gaps.py", "--data", eval_data, "--output-json", gap_eval_json], cwd=repo_root)

    bench_cmd = [py, "backend/evaluation/benchmark_importance_models.py", "--data", eval_data, "--label-col", "label", "--output-json", benchmark_json]
    if model_dir:
        bench_cmd += ["--model-dir", model_dir]
    _run(bench_cmd, cwd=repo_root)

    abl_cmd = [py, "backend/evaluation/ablation_gap1.py", "--data", eval_data, "--label-col", "label", "--output-json", ablation_json]
    if model_dir:
        abl_cmd += ["--model-dir", model_dir]
    _run(abl_cmd, cwd=repo_root)

    print("\n=== Completed run_all_experiments ===")
    print(f"run_dir={run_dir}")
    print("key_artifacts:")
    print(f"- {gap_eval_json}")
    print(f"- {benchmark_json}")
    print(f"- {ablation_json}")


if __name__ == "__main__":
    main()
