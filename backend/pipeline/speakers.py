"""
Computes speaker labels and per-speaker contribution metrics from transcript timing and segment importance scores.
"""
def _merge_turns(segments, merge_gap: float = 0.5):
    
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
    Estimate speaker turns and their contribution from pause-aware turn segmentation.

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