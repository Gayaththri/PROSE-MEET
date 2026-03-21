import re
from typing import Optional


def _merge_turns(segments, merge_gap: float = 0.5):
    """
    Merge consecutive segments separated by very short gaps into single turns.
    Returns list of (start, end, segment_indices) so we can assign one speaker per turn.
    """
    if not segments:
        return []
    segments = sorted(segments, key=lambda x: x["start"])
    turns = []
    turn_start = segments[0]["start"]
    turn_end = segments[0]["end"]
    turn_indices = [0]

    for i in range(1, len(segments)):
        seg = segments[i]
        gap = seg["start"] - turn_end
        if gap <= merge_gap:
            # Same turn: extend
            turn_end = seg["end"]
            turn_indices.append(i)
        else:
            turns.append((turn_start, turn_end, list(turn_indices)))
            turn_start = seg["start"]
            turn_end = seg["end"]
            turn_indices = [i]
    turns.append((turn_start, turn_end, list(turn_indices)))
    return turns


def compute_speaker_contribution(segments, pause_threshold: float = 0.7, merge_gap: float = 0.5):
    """
    Estimate speaker turns and their contribution (fallback when diarization is unavailable).

    Uses turn merging (merge consecutive segments with gap < merge_gap) then
    assigns a new speaker when gap between turns > pause_threshold. A lower
    threshold (e.g. 0.7s) helps multi-person meetings where turn-taking has short pauses.
    """

    if not segments:
        return []

    # Chronological order
    segments = sorted(segments, key=lambda x: x["start"])

    # Merge very short gaps into single turns so we don't flip speaker on every comma
    turns = _merge_turns(segments, merge_gap=merge_gap)
    if not turns:
        for seg in segments:
            seg["speaker"] = "Speaker_1"
        return [{"speaker": "Speaker_1", "talk_time_seconds": 0.0, "talk_time_percentage": 100.0, "importance_percentage": 100.0}]

    speakers = []
    speaker_id = 1
    turn_start, turn_end, turn_indices = turns[0]
    first_dur = max(0.0, turn_end - turn_start)
    first_weight = sum(
        segments[i].get("importance_score", 0.0) * max(0.0, segments[i]["end"] - segments[i]["start"])
        for i in turn_indices
    )
    first_speaker_label = f"Speaker_{speaker_id}"
    for i in turn_indices:
        segments[i]["speaker"] = first_speaker_label
    speakers.append(
        {
            "speaker": first_speaker_label,
            "segments": len(turn_indices),
            "total_duration": first_dur,
            "weighted_importance": first_weight,
        }
    )
    previous_end = turn_end

    for turn_start, turn_end, turn_indices in turns[1:]:
        gap = turn_start - previous_end
        dur = max(0.0, turn_end - turn_start)
        weight = sum(
            segments[i].get("importance_score", 0.0) * max(0.0, segments[i]["end"] - segments[i]["start"])
            for i in turn_indices
        )

        if gap > pause_threshold:
            speaker_id += 1
            speaker_label = f"Speaker_{speaker_id}"
            for i in turn_indices:
                segments[i]["speaker"] = speaker_label
            speakers.append(
                {
                    "speaker": speaker_label,
                    "segments": len(turn_indices),
                    "total_duration": dur,
                    "weighted_importance": weight,
                }
            )
        else:
            speaker_label = speakers[-1]["speaker"]
            for i in turn_indices:
                segments[i]["speaker"] = speaker_label
            s = speakers[-1]
            s["segments"] += len(turn_indices)
            s["total_duration"] += dur
            s["weighted_importance"] += weight

        previous_end = turn_end

    total_time = sum(s["total_duration"] for s in speakers)
    total_weight = sum(s["weighted_importance"] for s in speakers)

    for s in speakers:
        # How much time this speaker talked
        s["talk_time_seconds"] = s["total_duration"]
        s["talk_time_percentage"] = (
            (s["total_duration"] / total_time) * 100 if total_time > 0 else 0.0
        )

        # Importance-weighted contribution (what the UI currently displays)
        s["importance_percentage"] = (
            (s["weighted_importance"] / total_weight) * 100
            if total_weight > 0
            else 0.0
        )

        # Internal fields no longer needed by the frontend
        del s["total_duration"]
        del s["weighted_importance"]

    return speakers


def compute_speaker_contribution_from_labels(segments):
    """
    Compute speaker contribution stats when segments already have "speaker" set
    (e.g. from voice-based diarization). Does not modify segment speaker labels.
    """
    if not segments:
        return []
    by_speaker = {}
    for seg in segments:
        sp = seg.get("speaker", "Speaker_1")
        by_speaker.setdefault(sp, {"segments": [], "total_duration": 0.0, "weighted_importance": 0.0})
        s = by_speaker[sp]
        dur = max(0.0, seg["end"] - seg["start"])
        s["segments"].append(seg)
        s["total_duration"] += dur
        s["weighted_importance"] += seg.get("importance_score", 0.0) * dur

    total_time = sum(x["total_duration"] for x in by_speaker.values())
    total_weight = sum(x["weighted_importance"] for x in by_speaker.values())

    # Order by first appearance in transcript
    seen_order = []
    for seg in sorted(segments, key=lambda x: x["start"]):
        sp = seg.get("speaker", "Speaker_1")
        if sp not in seen_order:
            seen_order.append(sp)

    result = []
    for speaker in seen_order:
        s = by_speaker[speaker]
        result.append({
            "speaker": speaker,
            "talk_time_seconds": s["total_duration"],
            "talk_time_percentage": (
                (s["total_duration"] / total_time) * 100 if total_time > 0 else 0.0
            ),
            "importance_percentage": (
                (s["weighted_importance"] / total_weight) * 100
                if total_weight > 0 else 0.0
            ),
        })
    return result


def _extract_name_from_phrase(text: Optional[str]) -> Optional[str]:
    """Extract a person name from self-introduction phrases. Returns None if not found or invalid."""
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    if len(text) < 2:
        return None
    # "my name is X", "I'm X", "I am X", "this is X", "call me X" – X = one or two words (first name, or first + last)
    patterns = [
        r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z\'\-]+(?:\s+[A-Za-z][A-Za-z\'\-]+)?)",
        r"\bI\'m\s+([A-Za-z][A-Za-z\'\-]+(?:\s+[A-Za-z][A-Za-z\'\-]+)?)(?:\s|,|\.|$)",
        r"\bI\s+am\s+([A-Za-z][A-Za-z\'\-]+(?:\s+[A-Za-z][A-Za-z\'\-]+)?)(?:\s|,|\.|$)",
        r"\bthis\s+is\s+([A-Za-z][A-Za-z\'\-]+)(?:\s|,|\.|$)",
        r"\bcall\s+me\s+([A-Za-z][A-Za-z\'\-]+)(?:\s|,|\.|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Skip common false positives
            if name.lower() in ("the", "a", "an", "so", "just", "going", "really", "sorry"):
                continue
            # Title-case and limit length
            name = name.title()[:35]
            return name if len(name) >= 2 else None
    return None


def infer_and_apply_speaker_names(segments, speaker_summaries, speakers_list):
    """
    Infer speaker names from transcript content (e.g. "My name is Rose", "I'm Alima")
    and replace Speaker_1, Speaker_2, ... with those names everywhere.
    """
    if not segments:
        return
    # speaker -> inferred name (first strong match wins per speaker)
    mapping = {}
    for seg in sorted(segments, key=lambda x: x["start"]):
        sp = seg.get("speaker")
        if not sp or sp in mapping:
            continue
        text = (seg.get("text") or "").strip()
        name = _extract_name_from_phrase(text)
        if name:
            mapping[sp] = name

    if not mapping:
        return

    def replace_speaker(s):
        return mapping.get(s, s)

    for seg in segments:
        if seg.get("speaker"):
            seg["speaker"] = replace_speaker(seg["speaker"])
    for item in speaker_summaries:
        if item.get("speaker"):
            item["speaker"] = replace_speaker(item["speaker"])
    for item in speakers_list:
        if item.get("speaker"):
            item["speaker"] = replace_speaker(item["speaker"])