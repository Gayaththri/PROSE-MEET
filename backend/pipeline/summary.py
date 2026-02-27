import re

# Backchannels and very short phrases to exclude from summary/highlights (prosody often ranks them high)
_BACKCHANNELS = frozenset(
    s.strip().lower()
    for s in (
        "yeah", "yes", "no", "okay", "ok", "mm-hmm", "mmm", "mhm", "uh-huh", "uh huh",
        "right", "sure", "help", "oh", "ah", "hmm", "like", "well", "so", "anyway",
        "thanks", "thank you", "got it", "yep", "nope", "alright", "cool", "nice",
    )
)

# Common ASR hallucinations / off-topic phrases – exclude these from summary and highlights
_HALLUCINATION_BLOCKLIST = frozenset(
    s.strip().lower()
    for s in (
        "mermaid", "whales", "they can swim", "television", "five remotes", "remotes",
        "oh my god", "it's not a mermaid", "the reason i like whales", "if we can help it",
        "they're not too small", "not too small", "profit of this magnitude", "for television",
        "whale",
    )
)

# Words that suggest real meeting content – boost these segments in summary selection
_MEETING_KEYWORDS = frozenset(
    s.strip().lower()
    for s in (
        "agenda", "meeting", "minutes", "project", "plan", "discuss", "discussion",
        "opening", "closing", "today", "we will", "we'll", "going to", "presentation",
        "team", "next", "action", "follow up", "schedule", "deadline", "review",
        "kickoff", "manager", "stakeholder", "goal", "objective", "decision",
    )
)

_MIN_WORDS_SUBSTANTIVE = 4


def _is_substantive(seg):
    """True if segment looks like real content, not a backchannel or tiny fragment."""
    text = (seg.get("text") or "").strip()
    if not text:
        return False
    words = [w for w in re.split(r"\s+", text) if w]
    if len(words) < _MIN_WORDS_SUBSTANTIVE:
        if text.lower() in _BACKCHANNELS or (len(words) <= 1):
            return False
        if len(words) < 3:
            return False
    return True


def _is_likely_hallucination(seg):
    """True if segment text looks like common ASR errors / off-topic content."""
    text = (seg.get("text") or "").strip().lower()
    if not text:
        return True
    for phrase in _HALLUCINATION_BLOCKLIST:
        if phrase in text:
            return True
    return False


def _meeting_relevance(seg):
    """Higher = more meeting-like language (agenda, project, discuss, etc.)."""
    text = (seg.get("text") or "").strip().lower()
    words = set(re.split(r"\s+", text))
    return sum(1 for w in _MEETING_KEYWORDS if w in words or any(w in word for word in words))


def generate_summary(ranked_segments, top_ratio: float = 1.0, max_segments: int = 150):
    """
    Build a full meeting summary in chronological order so it matches the transcript.
    Includes all substantive segments (minus backchannels and hallucinations), so
    sentences are not missing. Capped at max_segments for very long meetings.
    """

    if not ranked_segments:
        return ""

    # Chronological order first – we want start-to-end coverage, not a "best of" subset
    by_time = sorted(ranked_segments, key=lambda x: x["start"])

    # Substantive only, drop likely ASR hallucinations
    substantive = [s for s in by_time if _is_substantive(s) and not _is_likely_hallucination(s)]
    pool = substantive if len(substantive) >= 2 else [s for s in by_time if _is_substantive(s)]
    if len(pool) < 2:
        pool = by_time

    # Take all in order, up to cap (so we don't miss sentences in the middle or end)
    k = min(max_segments, max(2, int(len(pool) * top_ratio)))
    selected = pool[:k]

    # Build summary: join with space, add period between segments that look like sentences
    summary_lines = []
    for seg in selected:
        text = (seg["text"] or "").strip()
        if text:
            summary_lines.append(text)

    summary = " ".join(summary_lines)
    # Normalise spacing
    if summary:
        summary = re.sub(r"\s+", " ", summary).strip()
    return summary


def generate_speaker_summaries(ranked_segments, top_ratio: float = 1.0, max_segments_per_speaker: int = 80):
    """
    Per-speaker summary in chronological order so it matches what they said.
    Includes all substantive segments for that speaker (no missing sentences).
    """

    if not ranked_segments:
        return []

    by_speaker = {}
    for seg in ranked_segments:
        speaker = seg.get("speaker", "Speaker_1")
        by_speaker.setdefault(speaker, []).append(seg)

    speaker_summaries = []
    speakers_ordered = sorted(
        by_speaker.items(),
        key=lambda item: min(s["start"] for s in item[1]),
    )

    for speaker, segs in speakers_ordered:
        # Chronological order so we don't drop sentences from the middle or end
        by_time = sorted(segs, key=lambda x: x["start"])
        substantive = [s for s in by_time if _is_substantive(s) and not _is_likely_hallucination(s)]
        pool = substantive if substantive else [s for s in by_time if _is_substantive(s)]
        if not pool:
            pool = by_time
        k = min(max_segments_per_speaker, max(1, int(len(pool) * top_ratio)))
        selected = pool[:k]

        lines = [s["text"] for s in selected]
        summary_text = " ".join(lines)

        speaker_summaries.append(
            {
                "speaker": speaker,
                "summary": summary_text,
            }
        )

    return speaker_summaries


def top_substantive_highlights(ranked_segments, n: int = 5):
    """
    Return the top n segments by importance that are substantive (not backchannels or tiny fragments).
    Used for Key moments so we show real content, not "Yeah.", "Help.", etc.
    """
    if not ranked_segments:
        return []
    substantive = [s for s in ranked_segments if _is_substantive(s) and not _is_likely_hallucination(s)]
    pool = substantive if substantive else [s for s in ranked_segments if _is_substantive(s)]
    if not pool:
        pool = ranked_segments[:n]
        return pool
    # Prefer meeting-relevant for key moments
    pool = sorted(
        pool,
        key=lambda s: (-_meeting_relevance(s), -s.get("importance_score", 0.0)),
    )
    return pool[:n]
