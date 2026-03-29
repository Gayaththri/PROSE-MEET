"""Prepare AMI-derived data files for evaluation workflows."""

import argparse
import csv
import json
import os
import random
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from pipeline.audio import preprocess_audio
from pipeline.prosody import extract_prosody

NITE_NS = {"nite": "http://nite.sourceforge.net/"}


def _meeting_domain(_meeting_id: str) -> str:
    # AMI meetings are treated as a single domain (corporate-like) for labels;
    # academic/medical come from other datasets.
    return "corporate"


def _clean_token(token: str) -> str:
    return (token or "").strip()


def _join_tokens(tokens: List[Tuple[str, bool]]) -> str:
    out = ""
    for token, is_punc in tokens:
        t = _clean_token(token)
        if not t:
            continue
        if is_punc and out:
            out += t
        elif not out:
            out = t
        else:
            out += " " + t
    return out.strip()


def _parse_word_index(word_id: str) -> Optional[int]:
    m = re.search(r"words(\d+)$", word_id or "")
    if not m:
        return None
    return int(m.group(1))


def _load_words(words_xml_path: str) -> Dict[int, Tuple[str, bool]]:
    tree = ET.parse(words_xml_path)
    root = tree.getroot()
    by_index: Dict[int, Tuple[str, bool]] = {}
    for node in root:
        tag = node.tag.split("}")[-1]
        if tag != "w":
            continue
        wid = node.attrib.get("{http://nite.sourceforge.net/}id", "")
        idx = _parse_word_index(wid)
        if idx is None:
            continue
        token = node.text or ""
        is_punc = (node.attrib.get("punc") or "").lower() == "true"
        by_index[idx] = (token, is_punc)
    return by_index


def _extract_word_range(href: str) -> Tuple[Optional[int], Optional[int]]:
    # Example: EN2001a.A.words.xml#id(EN2001a.A.words2)..id(EN2001a.A.words13)
    m = re.search(r"#id\(([^)]+)\)\.\.id\(([^)]+)\)", href or "")
    if m:
        start_idx = _parse_word_index(m.group(1))
        end_idx = _parse_word_index(m.group(2))
        return start_idx, end_idx
    m_single = re.search(r"#id\(([^)]+)\)", href or "")
    if m_single:
        idx = _parse_word_index(m_single.group(1))
        return idx, idx
    return None, None


def _parse_any_id_range(href: str) -> Tuple[Optional[str], Optional[str]]:
    m = re.search(r"#id\(([^)]+)\)\.\.id\(([^)]+)\)", href or "")
    if m:
        return m.group(1), m.group(2)
    m_single = re.search(r"#id\(([^)]+)\)", href or "")
    if m_single:
        one = m_single.group(1)
        return one, one
    return None, None


def _parse_file_from_href(href: str) -> str:
    return (href or "").split("#", 1)[0].strip()


def _id_suffix_num(item_id: str) -> Optional[int]:
    m = re.search(r"\.(\d+)$", item_id or "")
    if not m:
        return None
    return int(m.group(1))


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return not (a1 < b0 or b1 < a0)


def _append_range(store: Dict[str, List[Tuple[int, int]]], words_key: str, start_idx: int, end_idx: int) -> None:
    if start_idx is None or end_idx is None:
        return
    if end_idx < start_idx:
        start_idx, end_idx = end_idx, start_idx
    store.setdefault(words_key, []).append((start_idx, end_idx))


def _load_dialog_act_ranges(dialogue_acts_dir: str) -> Dict[str, Tuple[str, int, int]]:
    ranges: Dict[str, Tuple[str, int, int]] = {}
    files = [n for n in os.listdir(dialogue_acts_dir) if n.endswith(".dialog-act.xml")]
    for name in files:
        path = os.path.join(dialogue_acts_dir, name)
        tree = ET.parse(path)
        root = tree.getroot()
        for dact in root.findall("dact", NITE_NS):
            dact_id = dact.attrib.get("{http://nite.sourceforge.net/}id", "")
            child = dact.find("nite:child", NITE_NS)
            if not dact_id or child is None:
                continue
            href = child.attrib.get("href", "")
            start_idx, end_idx = _extract_word_range(href)
            if start_idx is None or end_idx is None:
                continue
            words_file = _parse_file_from_href(href)
            words_key = words_file.replace(".xml", "")
            ranges[dact_id] = (words_key, start_idx, end_idx)
    return ranges


def _build_positive_ranges(
    extractive_dir: str,
    decision_manual_dir: str,
    dialogue_acts_dir: str,
) -> Tuple[Dict[str, List[Tuple[int, int]]], set[str], Dict[str, int]]:
    positive_ranges: Dict[str, List[Tuple[int, int]]] = {}
    annotated_meetings: set[str] = set()
    stats = {"from_extractive": 0, "from_decision": 0}
    dialog_act_ranges = _load_dialog_act_ranges(dialogue_acts_dir)

    for name in sorted(os.listdir(extractive_dir)):
        if not name.endswith(".extsumm.xml"):
            continue
        meeting_id = name.split(".")[0]
        annotated_meetings.add(meeting_id)
        path = os.path.join(extractive_dir, name)
        tree = ET.parse(path)
        root = tree.getroot()
        for child in root.findall(".//nite:child", NITE_NS):
            href = child.attrib.get("href", "")
            file_name = _parse_file_from_href(href)
            start_id, end_id = _parse_any_id_range(href)
            if not file_name or not start_id or not end_id:
                continue
            # extsumm points to dialog acts. Convert them to word ranges.
            if file_name.endswith(".dialog-act.xml"):
                s_num = _id_suffix_num(start_id)
                e_num = _id_suffix_num(end_id)
                if s_num is None or e_num is None:
                    # Single fallback.
                    match = dialog_act_ranges.get(start_id)
                    if match is not None:
                        words_key, s_idx, e_idx = match
                        _append_range(positive_ranges, words_key, s_idx, e_idx)
                        stats["from_extractive"] += 1
                    continue
                low, high = sorted((s_num, e_num))
                prefix = start_id.rsplit(".", 1)[0]
                for idx in range(low, high + 1):
                    did = f"{prefix}.{idx}"
                    match = dialog_act_ranges.get(did)
                    if match is None:
                        continue
                    words_key, s_idx, e_idx = match
                    _append_range(positive_ranges, words_key, s_idx, e_idx)
                    stats["from_extractive"] += 1

    if os.path.isdir(decision_manual_dir):
        for name in sorted(os.listdir(decision_manual_dir)):
            if not name.endswith(".decision.xml"):
                continue
            meeting_id = name.split(".")[0]
            annotated_meetings.add(meeting_id)
            path = os.path.join(decision_manual_dir, name)
            tree = ET.parse(path)
            root = tree.getroot()
            for child in root.findall(".//nite:child", NITE_NS):
                href = child.attrib.get("href", "")
                words_file = _parse_file_from_href(href)
                start_idx, end_idx = _extract_word_range(href)
                if not words_file or start_idx is None or end_idx is None:
                    continue
                words_key = words_file.replace(".xml", "")
                _append_range(positive_ranges, words_key, start_idx, end_idx)
                stats["from_decision"] += 1

    return positive_ranges, annotated_meetings, stats


def _resolve_meeting_audio(meeting_id: str, signals_root: str) -> Optional[str]:
    if not signals_root or not os.path.isdir(signals_root):
        return None

    preferred_names = [
        f"{meeting_id}.Mix-Headset.wav",
        f"{meeting_id}.Headset.wav",
        f"{meeting_id}.Headset-0.wav",
        f"{meeting_id}.Array1-01.wav",
    ]

    # AMI download scripts create:
    #   amicorpus/<meetingID>/audio/<filename>.wav
    meeting_audio_dir = os.path.join(signals_root, meeting_id, "audio")
    if os.path.isdir(meeting_audio_dir):
        for name in preferred_names:
            candidate = os.path.join(meeting_audio_dir, name)
            if os.path.isfile(candidate):
                return candidate
        # Fallback: any wav inside the meeting audio dir.
        for name in os.listdir(meeting_audio_dir):
            if name.lower().endswith(".wav") and name.startswith(meeting_id + "."):
                return os.path.join(meeting_audio_dir, name)

    # Fallback: older/alternate layout where audio files sit at the root.
    for name in preferred_names:
        candidate = os.path.join(signals_root, name)
        if os.path.isfile(candidate):
            return candidate
    for name in os.listdir(signals_root):
        if name.lower().endswith(".wav") and name.startswith(meeting_id + "."):
            return os.path.join(signals_root, name)

    return None


def _compute_meeting_prosody_cache(
    meeting_ids: List[str],
    signals_root: Optional[str],
) -> Tuple[Dict[str, Dict], Dict[str, int]]:
    cache: Dict[str, Dict] = {}
    stats = {"meetings_with_audio": 0, "meetings_without_audio": 0}
    if not signals_root:
        stats["meetings_without_audio"] = len(meeting_ids)
        return cache, stats

    for mid in sorted(set(meeting_ids)):
        audio_path = _resolve_meeting_audio(mid, signals_root)
        if not audio_path:
            stats["meetings_without_audio"] += 1
            continue
        try:
            audio, sr = preprocess_audio(audio_path)
            pros = extract_prosody(audio, sr=sr)
            cache[mid] = {
                "pitch": pros["pitch"],
                "energy": pros["energy"],
                "silence": pros["silence"],
                "hop_length": pros.get("hop_length", 1024),
                "sr": sr,
            }
            stats["meetings_with_audio"] += 1
        except Exception:
            stats["meetings_without_audio"] += 1
    return cache, stats


def _segment_prosody_features(start: float, end: float, meeting_prosody: Optional[Dict]) -> Tuple[float, float, float]:
    if not meeting_prosody:
        return 0.0, 0.0, 0.0
    pitch = meeting_prosody["pitch"]
    energy = meeting_prosody["energy"]
    silence = meeting_prosody["silence"]
    sr = int(meeting_prosody["sr"])
    hop_length = int(meeting_prosody["hop_length"])
    num_frames = len(silence)
    if num_frames <= 0:
        return 0.0, 0.0, 0.0

    start_frame = max(0, int(float(start) * sr / hop_length))
    end_frame = min(num_frames, int(float(end) * sr / hop_length))
    if end_frame <= start_frame:
        end_frame = min(start_frame + 1, num_frames)
    if end_frame <= start_frame:
        return 0.0, 0.0, 0.0

    seg_pitch = pitch[start_frame:end_frame]
    seg_energy = energy[start_frame:end_frame]
    seg_silence = silence[start_frame:end_frame]
    pitch_var = float(seg_pitch.var()) if len(seg_pitch) > 0 else 0.0
    mean_energy = float(seg_energy.mean()) if len(seg_energy) > 0 else 0.0
    pause_ratio = float(seg_silence.mean()) if len(seg_silence) > 0 else 0.0
    return pitch_var, mean_energy, pause_ratio


def _build_rows(
    words_dir: str,
    segments_dir: str,
    positive_ranges: Dict[str, List[Tuple[int, int]]],
    annotated_meetings: set[str],
    meeting_prosody_cache: Dict[str, Dict],
) -> List[Dict]:
    rows: List[Dict] = []
    segment_files = sorted(
        [name for name in os.listdir(segments_dir) if name.endswith(".segments.xml")]
    )
    words_cache: Dict[str, Dict[int, Tuple[str, bool]]] = {}

    for seg_name in segment_files:
        segment_path = os.path.join(segments_dir, seg_name)
        base = seg_name.replace(".segments.xml", "")
        meeting_id = base.split(".")[0]
        speaker_id = base.split(".")[1] if "." in base else ""
        words_name = f"{base}.words.xml"
        words_path = os.path.join(words_dir, words_name)
        if not os.path.isfile(words_path):
            continue

        if words_name not in words_cache:
            words_cache[words_name] = _load_words(words_path)
        word_map = words_cache[words_name]

        tree = ET.parse(segment_path)
        root = tree.getroot()
        for seg in root.findall("segment", NITE_NS):
            seg_id = seg.attrib.get("{http://nite.sourceforge.net/}id", "")
            start = seg.attrib.get("transcriber_start")
            end = seg.attrib.get("transcriber_end")
            child = seg.find("nite:child", NITE_NS)
            if child is None:
                continue
            href = child.attrib.get("href", "")
            start_idx, end_idx = _extract_word_range(href)
            if start_idx is None or end_idx is None or end_idx < start_idx:
                continue

            words_key = words_name.replace(".xml", "")
            if meeting_id not in annotated_meetings:
                continue
            positives = positive_ranges.get(words_key, [])
            label = 1 if any(_overlaps(start_idx, end_idx, p0, p1) for p0, p1 in positives) else 0

            tokens: List[Tuple[str, bool]] = []
            for idx in range(start_idx, end_idx + 1):
                item = word_map.get(idx)
                if item is None:
                    continue
                tokens.append(item)
            text = _join_tokens(tokens)
            if not text:
                continue
            pitch_var, mean_energy, pause_ratio = _segment_prosody_features(
                float(start) if start is not None else 0.0,
                float(end) if end is not None else 0.0,
                meeting_prosody_cache.get(meeting_id),
            )

            rows.append(
                {
                    "meeting_id": meeting_id,
                    "speaker_id": speaker_id,
                    "segment_id": seg_id,
                    "true_domain": _meeting_domain(meeting_id),
                    "start": float(start) if start is not None else 0.0,
                    "end": float(end) if end is not None else 0.0,
                    "duration": (
                        max(0.0, float(end) - float(start))
                        if start is not None and end is not None
                        else 0.0
                    ),
                    "text": text,
                    "label": label,
                    "label_source": "ami_extractive_or_decision",
                    "pitch_variance": pitch_var,
                    "mean_energy": mean_energy,
                    "pause_ratio": pause_ratio,
                }
            )
    return rows


def _split_rows(rows: List[Dict], seed: int = 42) -> Dict[str, List[Dict]]:
    by_meeting = defaultdict(list)
    for r in rows:
        by_meeting[r["meeting_id"]].append(r)
    meetings = sorted(by_meeting.keys())
    rng = random.Random(seed)
    rng.shuffle(meetings)

    n = len(meetings)
    n_train = int(n * 0.8)
    n_val = int(n * 0.1)
    train_meetings = set(meetings[:n_train])
    val_meetings = set(meetings[n_train : n_train + n_val])
    test_meetings = set(meetings[n_train + n_val :])

    split_rows = {"train": [], "val": [], "test": []}
    for r in rows:
        mid = r["meeting_id"]
        if mid in train_meetings:
            split_rows["train"].append(r)
        elif mid in val_meetings:
            split_rows["val"].append(r)
        elif mid in test_meetings:
            split_rows["test"].append(r)
    return split_rows


def _write_csv(path: str, fieldnames: List[str], rows: List[Dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def main():
    parser = argparse.ArgumentParser(
        description="Convert AMI manual annotations to PROSE-MEET CSVs."
    )
    parser.add_argument(
        "--ami-root",
        default=os.path.join("backend", "data", "ami_manual"),
        help="Path to extracted AMI manual annotations root",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join("backend", "data"),
        help="Directory to write output CSV files",
    )
    parser.add_argument(
        "--signals-root",
        default=None,
        help="Optional directory containing AMI wav signals (e.g., Mix-Headset files).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Split random seed")
    args = parser.parse_args()

    words_dir = os.path.join(args.ami_root, "words")
    segments_dir = os.path.join(args.ami_root, "segments")
    extractive_dir = os.path.join(args.ami_root, "extractive")
    decision_manual_dir = os.path.join(args.ami_root, "decision", "manual")
    dialogue_acts_dir = os.path.join(args.ami_root, "dialogueActs")
    if not os.path.isdir(words_dir) or not os.path.isdir(segments_dir):
        raise FileNotFoundError(
            f"Could not find AMI words/segments directories under: {args.ami_root}"
        )
    if not os.path.isdir(extractive_dir) or not os.path.isdir(dialogue_acts_dir):
        raise FileNotFoundError(
            f"Could not find AMI extractive/dialogueActs directories under: {args.ami_root}"
        )

    positive_ranges, annotated_meetings, positive_stats = _build_positive_ranges(
        extractive_dir=extractive_dir,
        decision_manual_dir=decision_manual_dir,
        dialogue_acts_dir=dialogue_acts_dir,
    )
    meeting_prosody_cache, audio_stats = _compute_meeting_prosody_cache(
        meeting_ids=list(annotated_meetings),
        signals_root=args.signals_root,
    )

    rows = _build_rows(
        words_dir=words_dir,
        segments_dir=segments_dir,
        positive_ranges=positive_ranges,
        annotated_meetings=annotated_meetings,
        meeting_prosody_cache=meeting_prosody_cache,
    )
    if not rows:
        raise ValueError("No rows were extracted from AMI annotations.")
    if len({r["label"] for r in rows}) < 2:
        raise ValueError("AMI-derived labeling produced a single class. Check annotation parsing.")

    split_rows = _split_rows(rows, seed=args.seed)

    train_out = [
        {
            "text": r["text"],
            "label": r["label"],
            "start": r["start"],
            "end": r["end"],
            "duration": r["duration"],
            "pitch_variance": r["pitch_variance"],
            "mean_energy": r["mean_energy"],
            "pause_ratio": r["pause_ratio"],
            "meeting_id": r["meeting_id"],
            "true_domain": r["true_domain"],
            "speaker_id": r["speaker_id"],
            "segment_id": r["segment_id"],
            "label_source": r["label_source"],
        }
        for r in split_rows["train"]
    ]
    val_out = [
        {
            "text": r["text"],
            "label": r["label"],
            "start": r["start"],
            "end": r["end"],
            "duration": r["duration"],
            "pitch_variance": r["pitch_variance"],
            "mean_energy": r["mean_energy"],
            "pause_ratio": r["pause_ratio"],
            "meeting_id": r["meeting_id"],
            "true_domain": r["true_domain"],
            "speaker_id": r["speaker_id"],
            "segment_id": r["segment_id"],
            "label_source": r["label_source"],
        }
        for r in split_rows["val"]
    ]
    eval_out = [
        {
            "text": r["text"],
            "label": r["label"],
            "meeting_id": r["meeting_id"],
            "true_domain": r["true_domain"],
            "start": r["start"],
            "end": r["end"],
            "duration": r["duration"],
            "pitch_variance": r["pitch_variance"],
            "mean_energy": r["mean_energy"],
            "pause_ratio": r["pause_ratio"],
        }
        for r in split_rows["test"]
    ]

    _write_csv(
        os.path.join(args.output_dir, "importance_labels.csv"),
        [
            "text",
            "label",
            "start",
            "end",
            "duration",
            "pitch_variance",
            "mean_energy",
            "pause_ratio",
            "meeting_id",
            "true_domain",
            "speaker_id",
            "segment_id",
            "label_source",
        ],
        train_out,
    )
    _write_csv(
        os.path.join(args.output_dir, "importance_labels_val.csv"),
        [
            "text",
            "label",
            "start",
            "end",
            "duration",
            "pitch_variance",
            "mean_energy",
            "pause_ratio",
            "meeting_id",
            "true_domain",
            "speaker_id",
            "segment_id",
            "label_source",
        ],
        val_out,
    )
    _write_csv(
        os.path.join(args.output_dir, "eval_dataset.csv"),
        [
            "text",
            "label",
            "meeting_id",
            "true_domain",
            "start",
            "end",
            "duration",
            "pitch_variance",
            "mean_energy",
            "pause_ratio",
        ],
        eval_out,
    )

    report = {
        "ami_root": os.path.abspath(args.ami_root),
        "rows_total": len(rows),
        "rows_train": len(train_out),
        "rows_val": len(val_out),
        "rows_test_eval": len(eval_out),
        "meetings_total": len({r["meeting_id"] for r in rows}),
        "domains": sorted({r["true_domain"] for r in rows}),
        "label_source": "ami_extractive_or_decision",
        "label_counts": {
            "positive": int(sum(1 for r in rows if r["label"] == 1)),
            "negative": int(sum(1 for r in rows if r["label"] == 0)),
        },
        "annotation_stats": positive_stats,
        "audio_stats": audio_stats,
        "note": (
            "Positive labels are derived from AMI manual extractive summary and "
            "decision annotations. Negative labels are non-overlapping segments "
            "within the same annotated meetings."
        ),
    }
    with open(
        os.path.join(args.output_dir, "ami_conversion_report.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(report, f, indent=2)

    print("AMI conversion complete.")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
