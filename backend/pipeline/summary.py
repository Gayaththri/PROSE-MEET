def generate_summary(ranked_segments, top_ratio: float = 0.3):
    """
    Generate a prosody-aware meeting summary by selecting
    the most important utterances.

    Parameters:
    - ranked_segments: list of segments sorted by importance
    - top_ratio: proportion of utterances to include

    Returns:
    - summary text (string)
    """

    if not ranked_segments:
        return ""

    # Determine number of utterances to include
    k = max(3, int(len(ranked_segments) * top_ratio))

    # Select top-k important utterances
    selected = ranked_segments[:k]

    # Restore chronological order
    selected = sorted(selected, key=lambda x: x["start"])

    # Build summary text
    summary_lines = []
    for seg in selected:
        summary_lines.append(seg["text"])

    summary = " ".join(summary_lines)
    return summary
