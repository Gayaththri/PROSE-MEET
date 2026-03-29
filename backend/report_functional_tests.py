"""Generate reports for functional test executions."""

import argparse
import csv
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List


FR_MAPPING = {
    "test_short_filler_is_downweighted": "FR01",
    "test_domain_adaptation_boosts_domain_relevant_segments": "FR03",
    "test_highlights_respect_focus_keywords": "FR02",
    "test_run_gap1_to_result_flow": "FR04",
}


def _run_tests(repo_root: str) -> str:
    cmd = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "backend/tests",
        "-p",
        "test_*.py",
        "-v",
    ]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "") + "\n" + (proc.stderr or "")


def _parse_test_output(text: str) -> List[Dict]:
    rows = []
    pending = None
    for line in text.splitlines():
        stripped = line.strip()
        # Example: test_name (module.Class) ... ok
        m = re.match(r"^(test\w+)\s+\(([^)]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR)$", stripped)
        if not m:
            # Handle multiline case:
            # test_name (...) ...  <warnings...>
            # ok
            m2 = re.match(r"^(test\w+)\s+\(([^)]+)\)\s+\.\.\.\s*$", stripped)
            if m2:
                pending = (m2.group(1), m2.group(2))
                continue
            if pending and stripped in {"ok", "FAIL", "ERROR"}:
                test_name, location = pending
                rows.append(
                    {
                        "test_name": test_name,
                        "location": location,
                        "status": stripped,
                        "fr_mapping": FR_MAPPING.get(test_name, "UNMAPPED"),
                    }
                )
                pending = None
            continue
        test_name, location, status = m.group(1), m.group(2), m.group(3)
        rows.append(
            {
                "test_name": test_name,
                "location": location,
                "status": status,
                "fr_mapping": FR_MAPPING.get(test_name, "UNMAPPED"),
            }
        )
        pending = None
    return rows


def _write_csv(path: str, rows: List[Dict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["test_name", "location", "status", "fr_mapping"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _write_md(path: str, rows: List[Dict], raw_output: str):
    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "ok")
    failed = total - passed
    pass_rate = (passed / total * 100.0) if total else 0.0

    by_fr = {}
    for r in rows:
        fr = r["fr_mapping"]
        by_fr.setdefault(fr, {"total": 0, "passed": 0})
        by_fr[fr]["total"] += 1
        if r["status"] == "ok":
            by_fr[fr]["passed"] += 1

    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [
        "# Functional Test Report",
        "",
        f"_Generated: {ts}_",
        "",
        "## Overall Pass Rate",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total tests | {total} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Pass rate (%) | {pass_rate:.2f} |",
        "",
        "## FR Mapping Coverage",
        "",
        "| FR | Tests | Passed | Pass rate (%) |",
        "|---|---:|---:|---:|",
    ]
    for fr in sorted(by_fr.keys()):
        t = by_fr[fr]["total"]
        p = by_fr[fr]["passed"]
        pr = (p / t * 100.0) if t else 0.0
        lines.append(f"| {fr} | {t} | {p} | {pr:.2f} |")

    lines.extend(
        [
            "",
            "## Test Cases",
            "",
            "| Test | Status | FR Mapping |",
            "|---|---|---|",
        ]
    )
    for r in rows:
        lines.append(f"| {r['test_name']} | {r['status']} | {r['fr_mapping']} |")

    lines.extend(
        [
            "",
            "## Raw Command Output (trimmed)",
            "",
            "```text",
            "\n".join(raw_output.strip().splitlines()[-60:]),
            "```",
            "",
        ]
    )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Run backend functional tests and generate report artifacts.")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--output-md", default="results/functional_test_report.md", help="Markdown report path")
    parser.add_argument("--output-csv", default="results/functional_test_results.csv", help="CSV results path")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    output = _run_tests(repo_root)
    rows = _parse_test_output(output)

    _write_csv(os.path.join(repo_root, args.output_csv), rows)
    _write_md(os.path.join(repo_root, args.output_md), rows, output)

    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "ok")
    pass_rate = (passed / total * 100.0) if total else 0.0
    print(f"Functional tests parsed: total={total}, passed={passed}, pass_rate={pass_rate:.2f}%")
    print(f"Saved: {os.path.join(repo_root, args.output_csv)}")
    print(f"Saved: {os.path.join(repo_root, args.output_md)}")


if __name__ == "__main__":
    main()
