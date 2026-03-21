import argparse
import csv
import json
import os
from typing import Dict, List


REQUIRED_COLUMNS = [
    "id",
    "audio_path",
    "transcript_ref_path",
    "summary_ref_path",
    "domain",
    "split",
]


def _resolve(path: str, workspace_root: str) -> str:
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(workspace_root, path))


def validate_manifest(path: str, workspace_root: str) -> Dict:
    result = {
        "manifest": path,
        "valid": True,
        "rows": 0,
        "missing_files": [],
        "missing_columns": [],
        "errors": [],
    }
    if not os.path.isfile(path):
        result["valid"] = False
        result["errors"].append(f"Manifest file not found: {path}")
        return result

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing_cols:
            result["valid"] = False
            result["missing_columns"] = missing_cols
            result["errors"].append(f"Missing required columns: {', '.join(missing_cols)}")
            return result

        for idx, row in enumerate(reader, start=2):
            result["rows"] += 1
            for col in ("audio_path", "transcript_ref_path", "summary_ref_path"):
                raw = (row.get(col) or "").strip()
                abs_path = _resolve(raw, workspace_root)
                if not raw or not os.path.isfile(abs_path):
                    result["valid"] = False
                    result["missing_files"].append(
                        {
                            "line": idx,
                            "column": col,
                            "raw_path": raw,
                            "resolved_path": abs_path,
                            "message": f"Missing file at line {idx}, column '{col}': {abs_path}",
                        }
                    )

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate dataset manifest files and referenced paths.")
    parser.add_argument(
        "--manifests",
        nargs="+",
        default=[
            "data/manifests/custom.csv",
            "data/manifests/ami.csv",
            "data/manifests/icsi.csv",
        ],
        help="Manifest CSV paths",
    )
    parser.add_argument("--workspace-root", default=".", help="Workspace root for resolving relative paths")
    parser.add_argument("--output-json", default=None, help="Optional JSON report path")
    args = parser.parse_args()

    workspace_root = os.path.abspath(args.workspace_root)
    reports: List[Dict] = []

    print("=== Manifest Validation ===")
    for manifest in args.manifests:
        mpath = _resolve(manifest, workspace_root)
        rep = validate_manifest(mpath, workspace_root)
        reports.append(rep)

        status = "VALID" if rep["valid"] else "INVALID"
        print(f"- {manifest} -> {status} (rows={rep['rows']})")
        if rep["missing_columns"]:
            print(f"  missing columns: {', '.join(rep['missing_columns'])}")
        for item in rep["missing_files"]:
            print(f"  {item['message']}")

    all_valid = all(r["valid"] for r in reports)
    print(f"overall_status={'VALID' if all_valid else 'INVALID'}")

    payload = {
        "workspace_root": workspace_root,
        "overall_valid": all_valid,
        "manifests": reports,
    }
    if args.output_json:
        out_path = _resolve(args.output_json, workspace_root)
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"saved_report={out_path}")


if __name__ == "__main__":
    main()
