"""Compute inter-rater agreement for evaluation outputs."""

import argparse
import csv
import json
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


def _to_binary_label(value: str) -> Optional[int]:
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "important", "high"}:
        return 1
    if text in {"0", "false", "no", "not_important", "low"}:
        return 0
    return None


def _cohen_kappa_binary(a: List[int], b: List[int]) -> Optional[float]:
    if not a or not b or len(a) != len(b):
        return None
    n = len(a)
    agree = sum(1 for x, y in zip(a, b) if x == y) / n

    pa1 = sum(a) / n
    pb1 = sum(b) / n
    pa0 = 1.0 - pa1
    pb0 = 1.0 - pb1
    pe = (pa1 * pb1) + (pa0 * pb0)
    if pe == 1.0:
        return 1.0 if agree == 1.0 else 0.0
    return (agree - pe) / (1.0 - pe)


def _load_single_csv(path: str) -> Tuple[List[int], List[int]]:
    """
    CSV mode A:
      meeting_id,item_id,label_a,label_b
    """
    labels_a = []
    labels_b = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Empty CSV header.")
        required = {"label_a", "label_b"}
        if not required.issubset(set(reader.fieldnames)):
            raise ValueError("Single-file mode requires columns: label_a,label_b")
        for row in reader:
            la = _to_binary_label(row.get("label_a"))
            lb = _to_binary_label(row.get("label_b"))
            if la is None or lb is None:
                continue
            labels_a.append(la)
            labels_b.append(lb)
    return labels_a, labels_b


def _load_dual_csv(path_a: str, path_b: str) -> Tuple[List[int], List[int]]:
    """
    CSV mode B:
      file A/B columns: meeting_id,item_id,label
    """
    def read_map(path: str) -> Dict[Tuple[str, str], int]:
        out = {}
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            needed = {"meeting_id", "item_id", "label"}
            if not reader.fieldnames or not needed.issubset(set(reader.fieldnames)):
                raise ValueError("Dual-file mode requires columns: meeting_id,item_id,label")
            for row in reader:
                lab = _to_binary_label(row.get("label"))
                if lab is None:
                    continue
                key = (str(row.get("meeting_id", "")).strip(), str(row.get("item_id", "")).strip())
                out[key] = lab
        return out

    a_map = read_map(path_a)
    b_map = read_map(path_b)
    keys = sorted(set(a_map.keys()) & set(b_map.keys()))
    return [a_map[k] for k in keys], [b_map[k] for k in keys]


def main():
    parser = argparse.ArgumentParser(description="Compute inter-annotator agreement (Cohen's kappa).")
    parser.add_argument("--labels-csv", default=None, help="Single CSV with label_a,label_b")
    parser.add_argument("--annotator-a-csv", default=None, help="Annotator A CSV")
    parser.add_argument("--annotator-b-csv", default=None, help="Annotator B CSV")
    parser.add_argument("--output-json", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    if args.labels_csv:
        a, b = _load_single_csv(args.labels_csv)
    elif args.annotator_a_csv and args.annotator_b_csv:
        a, b = _load_dual_csv(args.annotator_a_csv, args.annotator_b_csv)
    else:
        raise ValueError(
            "Provide either --labels-csv or both --annotator-a-csv and --annotator-b-csv"
        )

    kappa = _cohen_kappa_binary(a, b)
    agree = sum(1 for x, y in zip(a, b) if x == y) / len(a) if a else None
    out = {
        "items_compared": len(a),
        "raw_agreement": agree,
        "cohen_kappa": kappa,
    }
    print("=== Inter-Annotator Agreement ===")
    print(f"items_compared={out['items_compared']}")
    print(f"raw_agreement={out['raw_agreement']:.3f}" if out["raw_agreement"] is not None else "raw_agreement=-")
    print(f"cohen_kappa={out['cohen_kappa']:.3f}" if out["cohen_kappa"] is not None else "cohen_kappa=-")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"saved={args.output_json}")


if __name__ == "__main__":
    main()
