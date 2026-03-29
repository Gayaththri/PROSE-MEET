"""Orchestrate execution of all configured backend experiments."""

import argparse
import os
import shutil
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


def _pick_runtime_input(repo_root: str) -> str:
    cand = os.path.join(repo_root, "data", "test_audio")
    if os.path.isdir(cand):
        return cand
    rec = os.path.join(repo_root, "data", "recordings")
    if os.path.isdir(rec):
        return rec
    raise FileNotFoundError(
        "No runtime input folder found. Create data/test_audio or data/recordings with at least one "
        "audio file, or skip runtime benchmark. See backend/data/templates/README.md."
    )


def _copy(src: str, dst: str):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"copied: {src} -> {dst}")


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
    try:
        runtime_input = _pick_runtime_input(repo_root)
    except FileNotFoundError:
        runtime_input = None
        print("[warn] Skipping runtime benchmark (no data/test_audio or data/recordings).")
    model_dir = args.model_dir

    gap_eval_json = os.path.join(run_dir, "gap_eval.json")
    benchmark_json = os.path.join(run_dir, "benchmark.json")
    ablation_json = os.path.join(run_dir, "ablation.json")
    runtime_json = os.path.join(run_dir, "runtime.json")
    chapter8_md = os.path.join(run_dir, "chapter8_results.md")
    figures_dir = os.path.join(run_dir, "figures")

    py = sys.executable

    _run([py, "backend/evaluate_gaps.py", "--data", eval_data, "--output-json", gap_eval_json], cwd=repo_root)

    bench_cmd = [py, "backend/benchmark_importance_models.py", "--data", eval_data, "--label-col", "label", "--output-json", benchmark_json]
    if model_dir:
        bench_cmd += ["--model-dir", model_dir]
    _run(bench_cmd, cwd=repo_root)

    abl_cmd = [py, "backend/ablation_gap1.py", "--data", eval_data, "--label-col", "label", "--output-json", ablation_json]
    if model_dir:
        abl_cmd += ["--model-dir", model_dir]
    _run(abl_cmd, cwd=repo_root)

    if runtime_input:
        _run([py, "backend/benchmark_runtime.py", "--inputs", runtime_input, "--output-json", runtime_json], cwd=repo_root)
    else:
        runtime_json = None

    build_cmd = [
        py,
        "backend/build_results_tables.py",
        "--gap-eval-json",
        gap_eval_json,
        "--benchmark-json",
        benchmark_json,
        "--ablation-json",
        ablation_json,
        "--output-md",
        chapter8_md,
    ]
    if runtime_json:
        build_cmd += ["--runtime-json", runtime_json]
    _run(build_cmd, cwd=repo_root)

    _run(
        [
            py,
            "backend/plot_metrics.py",
            "--gap-eval-json",
            gap_eval_json,
            "--ablation-json",
            ablation_json,
            "--benchmark-json",
            benchmark_json,
            "--output-dir",
            figures_dir,
        ],
        cwd=repo_root,
    )

    _run([py, "backend/report_functional_tests.py", "--repo-root", repo_root], cwd=repo_root)
    _run([py, "backend/nfr_tests.py", "--repo-root", repo_root], cwd=repo_root)

    # Copy final thesis artifacts to docs/
    docs_dir = os.path.join(repo_root, "docs")
    docs_figures = os.path.join(docs_dir, "figures")
    os.makedirs(docs_figures, exist_ok=True)
    _copy(chapter8_md, os.path.join(docs_dir, "chapter8_results.md"))
    for fig_name in ("confusion_matrix.png", "roc_curve.png", "pr_curve.png"):
        src = os.path.join(figures_dir, fig_name)
        if os.path.isfile(src):
            _copy(src, os.path.join(docs_figures, fig_name))

    print("\n=== Completed run_all_experiments ===")
    print(f"run_dir={run_dir}")
    print("key_artifacts:")
    print(f"- {os.path.join(repo_root, 'docs', 'chapter8_results.md')}")
    print(f"- {os.path.join(repo_root, 'docs', 'figures', 'confusion_matrix.png')}")
    print(f"- {os.path.join(repo_root, 'docs', 'figures', 'roc_curve.png')}")
    print(f"- {os.path.join(repo_root, 'docs', 'figures', 'pr_curve.png')}")
    print(f"- {os.path.join(repo_root, 'docs', 'functional_test_report.md')}")
    print(f"- {os.path.join(repo_root, 'docs', 'nfr_test_report.md')}")


if __name__ == "__main__":
    main()
