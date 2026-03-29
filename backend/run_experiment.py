"""Run a configured experiment and persist its results."""

import argparse
import json
import os
from datetime import datetime, timezone

from evaluate_gaps import _load_rows, evaluate_gap1_importance, evaluate_gap2_domain


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _append_jsonl(path: str, payload: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run reproducible experiment config and log outputs.")
    parser.add_argument("--config", required=True, help="Path to experiment JSON config")
    args = parser.parse_args()

    config = _read_json(args.config)
    data_path = config.get("data")
    model_dir = config.get("model_dir")
    run_name = config.get("run_name", "unnamed_run")
    log_path = config.get("log_path", os.path.join("data", "experiments", "runs.jsonl"))

    if not data_path:
        raise ValueError("Config must include 'data' path.")
    if not os.path.isfile(data_path):
        raise FileNotFoundError(
            f"Configured dataset file not found: {data_path}. "
            "Create data/eval_dataset.csv or update config['data']."
        )

    rows = _load_rows(data_path)
    out = {
        "run_name": run_name,
        "timestamp": _utc_now(),
        "config": config,
        "results": {},
    }

    try:
        out["results"]["gap1"] = evaluate_gap1_importance(rows, model_dir=model_dir)
    except Exception as exc:
        out["results"]["gap1_error"] = str(exc)

    try:
        out["results"]["gap2"] = evaluate_gap2_domain(rows)
    except Exception as exc:
        out["results"]["gap2_error"] = str(exc)

    _append_jsonl(log_path, out)
    print(f"Experiment logged to {log_path}")
    print(json.dumps(out["results"], indent=2))


if __name__ == "__main__":
    main()
