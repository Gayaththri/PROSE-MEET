import argparse
import csv
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from backend.pipeline.run_gap1 import run_gap1
    from backend.pipeline.run_gap1_legacy import run_gap1_legacy
except ImportError:
    import sys
    _BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)
    from pipeline.run_gap1 import run_gap1
    from pipeline.run_gap1_legacy import run_gap1_legacy

try:
    from .datasets import load_manifest, load_meeting_reference, resolve_path
    from .metrics import (
        accuracy,
        cer,
        macro_f1,
        precision_recall_f1_binary,
        rouge_scores,
        safe_mean,
        wer,
    )
    from .report import write_markdown_summary
except ImportError:
    from evaluation.datasets import load_manifest, load_meeting_reference, resolve_path
    from evaluation.metrics import (
        accuracy,
        cer,
        macro_f1,
        precision_recall_f1_binary,
        rouge_scores,
        safe_mean,
        wer,
    )
    from evaluation.report import write_markdown_summary


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _join_transcript_text(transcript_segments: List[Dict[str, Any]]) -> str:
    by_time = sorted(transcript_segments or [], key=lambda x: x.get("start", 0.0))
    return " ".join((s.get("text") or "").strip() for s in by_time if (s.get("text") or "").strip()).strip()


def _parse_bool_label(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    txt = str(value).strip().lower()
    if txt in {"1", "true", "yes", "important", "high"}:
        return 1
    if txt in {"0", "false", "no", "not_important", "low"}:
        return 0
    return None


def _match_importance_labels(
    predicted: List[Dict[str, Any]],
    reference_utterances: List[Dict[str, Any]],
) -> tuple[List[int], List[int]]:
    if not predicted or not reference_utterances:
        return [], []
    refs_with_label = [r for r in reference_utterances if _parse_bool_label(r.get("important")) is not None]
    if not refs_with_label:
        return [], []

    y_true = []
    ref_has_time = any(r.get("start") is not None and r.get("end") is not None for r in refs_with_label)
    pred_has_time = any(p.get("start") is not None and p.get("end") is not None for p in predicted)

    if ref_has_time and pred_has_time:
        for seg in predicted:
            s0 = seg.get("start")
            s1 = seg.get("end")
            if s0 is None or s1 is None:
                y_true.append(0)
                continue
            best_ref = None
            best_overlap = -1.0
            for ref in refs_with_label:
                r0, r1 = ref.get("start"), ref.get("end")
                if r0 is None or r1 is None:
                    continue
                overlap = max(0.0, min(float(s1), float(r1)) - max(float(s0), float(r0)))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_ref = ref
            if best_ref is None:
                y_true.append(0)
            else:
                y_true.append(_parse_bool_label(best_ref.get("important")) or 0)
    else:
        for idx, seg in enumerate(predicted):
            if idx < len(refs_with_label):
                y_true.append(_parse_bool_label(refs_with_label[idx].get("important")) or 0)
            else:
                y_true.append(0)

    # Placeholder preds returned by caller per mode; keep shape alignment.
    return y_true, [0] * len(y_true)


def _semantic_score(text: str) -> float:
    kws = [
        "need to", "must", "should", "decide", "decision", "finalize", "deadline",
        "budget", "plan", "requirement", "action item", "deliverable",
    ]
    txt = (text or "").strip().lower()
    words = [w for w in re.split(r"\s+", txt) if w]
    score = min(0.35, len(words) / 20.0)
    hits = sum(1 for kw in kws if kw in txt)
    score += min(0.45, 0.15 * hits)
    if re.search(r"\b\d+(?:[\.,]\d+)?\b", txt):
        score += 0.12
    if len(words) < 4:
        score -= 0.22
    return max(0.0, min(1.5, score))


def _prosody_score(seg: Dict[str, Any], means: Dict[str, float], stds: Dict[str, float]) -> float:
    z_pitch = abs((float(seg.get("pitch_variance", 0.0) or 0.0) - means["pitch"]) / stds["pitch"])
    z_energy = abs((float(seg.get("mean_energy", 0.0) or 0.0) - means["energy"]) / stds["energy"])
    z_pause = abs((float(seg.get("pause_ratio", 0.0) or 0.0) - means["pause"]) / stds["pause"])
    return (0.4 * z_pitch) + (0.4 * z_energy) + (0.2 * z_pause)


def _predict_importance_for_mode(transcript: List[Dict[str, Any]], mode: str, full_threshold: float) -> List[int]:
    if not transcript:
        return []

    if mode == "full":
        return [1 if float(s.get("importance_score", 0.0) or 0.0) >= float(full_threshold) else 0 for s in transcript]

    pitch = [float(s.get("pitch_variance", 0.0) or 0.0) for s in transcript]
    energy = [float(s.get("mean_energy", 0.0) or 0.0) for s in transcript]
    pause = [float(s.get("pause_ratio", 0.0) or 0.0) for s in transcript]
    means = {
        "pitch": sum(pitch) / len(pitch),
        "energy": sum(energy) / len(energy),
        "pause": sum(pause) / len(pause),
    }
    stds = {
        "pitch": (sum((x - means["pitch"]) ** 2 for x in pitch) / len(pitch)) ** 0.5 + 1e-6,
        "energy": (sum((x - means["energy"]) ** 2 for x in energy) / len(energy)) ** 0.5 + 1e-6,
        "pause": (sum((x - means["pause"]) ** 2 for x in pause) / len(pause)) ** 0.5 + 1e-6,
    }

    raw_scores = []
    for seg in transcript:
        if mode == "text_only":
            raw_scores.append(_semantic_score(seg.get("text") or ""))
        elif mode == "prosody_only":
            raw_scores.append(_prosody_score(seg, means, stds))
        else:
            raw_scores.append(float(seg.get("importance_score", 0.0) or 0.0))

    if not raw_scores:
        return []
    threshold = sum(raw_scores) / len(raw_scores)
    return [1 if s >= threshold else 0 for s in raw_scores]


def _write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    cols = sorted({k for r in rows for k in r.keys()})
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _domain_group_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    train_domains = sorted({r["domain_true"] for r in rows if str(r.get("split", "")).lower() == "train" and r.get("domain_true")})
    eval_rows = [r for r in rows if str(r.get("split", "")).lower() in {"val", "dev", "test"}]
    if not eval_rows:
        eval_rows = rows

    grouped = {"seen": [], "unseen": []}
    for r in eval_rows:
        domain = r.get("domain_true")
        if not domain:
            continue
        key = "seen" if domain in train_domains else "unseen"
        grouped[key].append(r)

    out = []
    for key, items in grouped.items():
        if not items:
            continue
        out.append(
            {
                "group": key,
                "meetings": len(items),
                "importance_f1": safe_mean([r.get("importance_f1") for r in items]),
                "domain_accuracy": safe_mean(
                    [1.0 if r.get("domain_pred") == r.get("domain_true") else 0.0 for r in items if r.get("domain_true")]
                ),
                "domains": ",".join(sorted({str(r.get("domain_true")) for r in items if r.get("domain_true")})),
            }
        )
    return out


def main():
    parser = argparse.ArgumentParser(description="Dataset-driven experiments for Gap 1/Gap 2.")
    parser.add_argument("--manifest", required=True, help="Path to manifest CSV")
    parser.add_argument("--workspace-root", default=None, help="Workspace root for relative paths")
    parser.add_argument("--output-root", default="results", help="Root directory for timestamped outputs")
    parser.add_argument("--pipeline", choices=["current", "legacy"], default="current", help="Pipeline implementation to evaluate")
    args = parser.parse_args()

    workspace_root = args.workspace_root or os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    manifest_path = resolve_path(args.manifest, workspace_root)
    rows = load_manifest(manifest_path)

    ts = _now_ts()
    out_dir = os.path.join(resolve_path(args.output_root, workspace_root), ts)
    os.makedirs(out_dir, exist_ok=True)

    config = {
        "manifest": manifest_path,
        "workspace_root": workspace_root,
        "output_dir": out_dir,
        "modes": ["text_only", "prosody_only", "full"],
        "pipeline": args.pipeline,
    }
    with open(os.path.join(out_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    per_meeting_rows = []
    ablation_collection = {"text_only": {"y_true": [], "y_pred": []}, "prosody_only": {"y_true": [], "y_pred": []}, "full": {"y_true": [], "y_pred": []}}

    domain_true_all = []
    domain_pred_all = []

    pipeline_runner = run_gap1_legacy if args.pipeline == "legacy" else run_gap1

    for item in rows:
        mid = item["id"]
        audio_path = resolve_path(item.get("audio_path"), workspace_root)
        reference = load_meeting_reference(item, workspace_root)

        t0 = time.perf_counter()
        result = pipeline_runner(audio_path)
        elapsed = time.perf_counter() - t0

        transcript = result.get("transcript") or []
        pred_transcript_text = _join_transcript_text(transcript)
        pred_summary = (result.get("summary") or "").strip()
        full_threshold = float(result.get("importance_threshold", 0.56) or 0.56)

        wer_value = wer(reference.transcript_text or "", pred_transcript_text) if reference.transcript_text else None
        cer_value = cer(reference.transcript_text or "", pred_transcript_text) if reference.transcript_text else None
        rouge = rouge_scores(reference.summary_text or "", pred_summary) if reference.summary_text else {"rouge1_f1": None, "rouge2_f1": None, "rougel_f1": None}

        y_true, _ = _match_importance_labels(transcript, reference.utterances)
        importance_metrics = {"precision": None, "recall": None, "f1": None}
        if y_true:
            y_pred_full = _predict_importance_for_mode(transcript, "full", full_threshold)
            imp = precision_recall_f1_binary(y_true, y_pred_full)
            importance_metrics = {"precision": imp["precision"], "recall": imp["recall"], "f1": imp["f1"]}

            for mode in ("text_only", "prosody_only", "full"):
                y_pred_mode = _predict_importance_for_mode(transcript, mode, full_threshold)
                if len(y_pred_mode) == len(y_true):
                    ablation_collection[mode]["y_true"].extend(y_true)
                    ablation_collection[mode]["y_pred"].extend(y_pred_mode)

        domain_pred = ((result.get("domain") or {}).get("predicted_domain") or "").strip().lower() or None
        domain_true = (item.get("domain") or "").strip().lower() or None
        if domain_true and domain_pred:
            domain_true_all.append(domain_true)
            domain_pred_all.append(domain_pred)

        per_meeting_rows.append(
            {
                "id": mid,
                "split": item.get("split"),
                "domain_true": domain_true,
                "domain_pred": domain_pred,
                "wer": wer_value,
                "cer": cer_value,
                "importance_precision": importance_metrics["precision"],
                "importance_recall": importance_metrics["recall"],
                "importance_f1": importance_metrics["f1"],
                "rouge1_f1": rouge["rouge1_f1"],
                "rouge2_f1": rouge["rouge2_f1"],
                "rougel_f1": rouge["rougel_f1"],
                "latency_seconds": elapsed,
                "duration_seconds": result.get("duration_seconds"),
                "transcript_segments": len(transcript),
            }
        )

    _write_csv(os.path.join(out_dir, "per_meeting.csv"), per_meeting_rows)

    aggregate = {
        "wer": safe_mean([r.get("wer") for r in per_meeting_rows]),
        "cer": safe_mean([r.get("cer") for r in per_meeting_rows]),
        "importance_precision": safe_mean([r.get("importance_precision") for r in per_meeting_rows]),
        "importance_recall": safe_mean([r.get("importance_recall") for r in per_meeting_rows]),
        "importance_f1": safe_mean([r.get("importance_f1") for r in per_meeting_rows]),
        "rouge1_f1": safe_mean([r.get("rouge1_f1") for r in per_meeting_rows]),
        "rouge2_f1": safe_mean([r.get("rouge2_f1") for r in per_meeting_rows]),
        "rougel_f1": safe_mean([r.get("rougel_f1") for r in per_meeting_rows]),
        "domain_accuracy": accuracy(domain_true_all, domain_pred_all),
        "domain_macro_f1": macro_f1(domain_true_all, domain_pred_all),
        "latency_seconds_avg": safe_mean([r.get("latency_seconds") for r in per_meeting_rows]),
    }
    with open(os.path.join(out_dir, "aggregate.json"), "w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2)

    ablation_rows = []
    for mode, data in ablation_collection.items():
        if data["y_true"] and data["y_pred"]:
            m = precision_recall_f1_binary(data["y_true"], data["y_pred"])
            ablation_rows.append(
                {
                    "mode": mode,
                    "importance_precision": m["precision"],
                    "importance_recall": m["recall"],
                    "importance_f1": m["f1"],
                    "tp": m["tp"],
                    "fp": m["fp"],
                    "fn": m["fn"],
                }
            )
        else:
            ablation_rows.append({"mode": mode, "importance_precision": None, "importance_recall": None, "importance_f1": None})
    _write_csv(os.path.join(out_dir, "ablation.csv"), ablation_rows)

    cross_domain_rows = _domain_group_rows(per_meeting_rows)
    _write_csv(os.path.join(out_dir, "cross_domain.csv"), cross_domain_rows)

    worst_by_wer = [r for r in per_meeting_rows if r.get("wer") is not None]
    worst_by_wer.sort(key=lambda x: x.get("wer", 0.0), reverse=True)
    worst_by_imp = [r for r in per_meeting_rows if r.get("importance_f1") is not None]
    worst_by_imp.sort(key=lambda x: x.get("importance_f1", 1.0))
    error_bullets = []
    if worst_by_wer:
        sample = worst_by_wer[0]
        error_bullets.append(f"Highest WER on meeting `{sample['id']}` ({sample['wer']:.3f}); inspect audio quality/ASR confidence.")
    if worst_by_imp:
        sample = worst_by_imp[0]
        error_bullets.append(f"Lowest importance F1 on meeting `{sample['id']}` ({sample['importance_f1']:.3f}); inspect short utterance false positives.")
    if cross_domain_rows:
        unseen = next((r for r in cross_domain_rows if r.get("group") == "unseen"), None)
        seen = next((r for r in cross_domain_rows if r.get("group") == "seen"), None)
        if unseen and seen and unseen.get("importance_f1") is not None and seen.get("importance_f1") is not None:
            gap = float(seen["importance_f1"]) - float(unseen["importance_f1"])
            error_bullets.append(f"Seen vs unseen domain importance-F1 gap: {gap:+.3f}.")

    dataset_summary = {
        "manifest": manifest_path,
        "meetings_total": len(rows),
        "splits": ", ".join(sorted({str(r.get("split", "")) for r in rows})),
        "domains": ", ".join(sorted({str(r.get("domain", "")) for r in rows})),
    }
    md_path = write_markdown_summary(
        out_dir,
        dataset_summary=dataset_summary,
        aggregate=aggregate,
        ablation_rows=ablation_rows,
        cross_domain_rows=cross_domain_rows,
        error_bullets=error_bullets,
    )
    eval_dir_summary = os.path.join(os.path.dirname(__file__), "RESULTS_SUMMARY.md")
    shutil.copyfile(md_path, eval_dir_summary)

    print(f"Evaluation completed. Results written to: {out_dir}")
    print("Files:")
    print(f"- {os.path.join(out_dir, 'config.json')}")
    print(f"- {os.path.join(out_dir, 'per_meeting.csv')}")
    print(f"- {os.path.join(out_dir, 'aggregate.json')}")
    print(f"- {os.path.join(out_dir, 'ablation.csv')}")
    print(f"- {os.path.join(out_dir, 'cross_domain.csv')}")
    print(f"- {os.path.join(out_dir, 'RESULTS_SUMMARY.md')}")
    print(f"- {eval_dir_summary}")


if __name__ == "__main__":
    main()
