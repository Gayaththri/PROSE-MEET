def compute_speaker_contribution(ranked_segments, pause_threshold: float = 1.5):
    """
    Compute importance-weighted speaker contribution using
    pause-based turn-taking.
    """

    if not ranked_segments:
        return []

    speakers = []
    speaker_id = 1

    previous_end = ranked_segments[0]["end"]
    speakers.append({
        "speaker": f"Speaker_{speaker_id}",
        "importance_score": ranked_segments[0]["importance_score"]
    })

    for seg in ranked_segments[1:]:
        gap = seg["start"] - previous_end

        if gap > pause_threshold:
            speaker_id += 1
            speakers.append({
                "speaker": f"Speaker_{speaker_id}",
                "importance_score": seg["importance_score"]
            })
        else:
            speakers[-1]["importance_score"] += seg["importance_score"]

        previous_end = seg["end"]

    # Normalise importance scores to percentages
    total_importance = sum(s["importance_score"] for s in speakers)

    for s in speakers:
        s["importance_percentage"] = (
            (s["importance_score"] / total_importance) * 100
            if total_importance > 0 else 0
        )

    return speakers
