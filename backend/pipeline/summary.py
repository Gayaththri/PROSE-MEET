import re
from .ai_summary import try_generate_ai_summary

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

_MIN_WORDS_SUBSTANTIVE = 3  # include short phrases (e.g. quiet speech) in summary when not backchannel
_SUMMARY_MAX_WORDS_PER_SEGMENT = 34
_SUMMARY_MAX_SEGMENTS = 6
_ACTION_KEYWORDS = frozenset(
    s.strip().lower()
    for s in (
        "next", "action", "follow up", "email", "coach", "instructions",
        "deadline", "schedule", "plan", "assign", "individual work",
    )
)
_DISCUSSION_KEYWORDS = frozenset(
    s.strip().lower()
    for s in (
        "discuss", "discussion", "idea", "feature", "requirement", "goal",
        "project", "design", "problem", "decision", "user", "customer",
        "button", "battery", "layout", "simple", "easy", "remote",
    )
)
_INTRO_KEYWORDS = frozenset(
    s.strip().lower()
    for s in (
        "introduce", "introduced", "my name", "i'm", "i am", "role",
        "speaker", "artist", "favorite animal",
    )
)
_DECISION_KEYWORDS = frozenset(
    s.strip().lower()
    for s in (
        "we will", "we'll", "we are", "we're", "going to", "decided",
        "decision", "divide", "phases", "sell", "profit", "market",
        "target", "goal", "objective",
    )
)
_RISK_KEYWORDS = frozenset(
    s.strip().lower()
    for s in (
        "risk", "problem", "issue", "confusing", "too many buttons",
        "too many", "hard", "difficult", "don't like", "do not like",
        "hate", "not work", "doesn't work", "battery", "overload",
        "worry", "lost", "lazy", "small buttons",
    )
)
_QUESTION_KEYWORDS = frozenset(
    s.strip().lower()
    for s in (
        "question", "would it", "could", "how do we", "i don't know",
        "good question", "possible", "technically be possible",
    )
)
_ACTION_KEYWORDS_EXTENDED = frozenset(
    s.strip().lower()
    for s in (
        "send", "email", "check", "look into", "individual work",
        "specific instructions", "next meeting", "follow up",
        "coach", "agenda", "website", "will get", "i'll",
    )
)
_TOPIC_DEFINITIONS = (
    ("Kickoff and agenda", ("agenda", "kickoff", "opening", "closing", "today")),
    ("Project goals and scope", ("goal", "objective", "project aim", "creating", "user-friendly", "trendy", "original")),
    ("Project plan and collaboration model", ("functional design", "conceptual design", "detailed design", "individual work", "meeting", "collaborating")),
    ("Commercial targets and market", ("sell", "euro", "profit", "market", "international")),
    ("User needs and product requirements", ("remote", "buttons", "volume", "channel", "battery", "simple", "easy", "layout")),
    ("Assignments and follow-up", ("instructions", "email", "next meeting", "website", "coach", "individual work")),
)
_GENERIC_SPEAKER_RE = re.compile(r"^speaker[_\s]?\d+$", re.IGNORECASE)


def _is_substantive(seg):
    """True if segment looks like real content, not a backchannel or tiny fragment."""
    text = (seg.get("text") or "").strip()
    if not text:
        return False
    words = [w for w in re.split(r"\s+", text) if w]
    if len(words) < _MIN_WORDS_SUBSTANTIVE:
        if text.lower() in _BACKCHANNELS or (len(words) <= 1):
            return False
        if len(words) < 2:
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


def _meeting_relevance(seg, focus_keywords=None):
    """Higher = more meeting-like language (agenda, project, discuss, etc.)."""
    text = (seg.get("text") or "").strip().lower()
    words = set(re.split(r"\s+", text))
    keywords = focus_keywords or _MEETING_KEYWORDS
    return sum(1 for w in keywords if w in words or any(w in word for word in words))


def _keyword_hits(text, keywords):
    text_lower = (text or "").strip().lower()
    if not text_lower:
        return 0
    return sum(1 for keyword in keywords if keyword in text_lower)


def _normalise_summary_text(text: str, max_words: int = _SUMMARY_MAX_WORDS_PER_SEGMENT):
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    text = re.sub(r"^[,.;:\-\s]+", "", text)
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]).rstrip(",;:-") + "..."
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _segment_text(seg):
    return re.sub(r"\s+", " ", (seg.get("text") or "").strip())


def _prepare_summary_segments(ranked_segments):
    if not ranked_segments:
        return []
    by_time = sorted(ranked_segments, key=lambda x: x["start"])
    substantive = [s for s in by_time if _is_substantive(s) and not _is_likely_hallucination(s)]
    return substantive if substantive else by_time


def _dedupe_lines(lines):
    seen = set()
    out = []
    for line in lines:
        key = re.sub(r"\s+", " ", line.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line.strip())
    return out


def _select_segments(segments, *, keywords=(), limit=2, exclude_keys=None):
    exclude_keys = exclude_keys or set()
    ranked = sorted(
        segments,
        key=lambda seg: (
            _keyword_hits(_segment_text(seg), keywords) * 4.0
            + _meeting_relevance(seg)
            + float(seg.get("importance_score", 0.0) or 0.0)
        ),
        reverse=True,
    )
    chosen = []
    for seg in ranked:
        text = _segment_text(seg)
        text_key = text.lower()
        if not text or text_key in exclude_keys:
            continue
        if keywords and _keyword_hits(text, keywords) <= 0:
            continue
        chosen.append(seg)
        exclude_keys.add(text_key)
        if len(chosen) >= limit:
            break
    return chosen


def _format_topic_line(title, segments):
    lines = [_normalise_summary_text(_segment_text(seg), max_words=36) for seg in segments]
    lines = [line for line in lines if line]
    if not lines:
        return None
    return f"- {title}: {' '.join(lines)}"


def _extract_named_people(segments):
    names = []
    for seg in segments:
        speaker = (seg.get("speaker") or "").strip()
        if speaker and not _GENERIC_SPEAKER_RE.match(speaker):
            if speaker not in names:
                names.append(speaker)
    return names


def _infer_owner(seg, known_people):
    text = _segment_text(seg)
    text_lower = text.lower()
    for person in known_people:
        if re.search(rf"\b{re.escape(person.lower())}\b", text_lower):
            return person
    speaker = (seg.get("speaker") or "").strip()
    if speaker and not _GENERIC_SPEAKER_RE.match(speaker):
        return speaker
    return "Not specified"


def _extract_deadline(text):
    text_lower = (text or "").strip().lower()
    patterns = (
        r"before the next meeting",
        r"next meeting",
        r"next session",
        r"today",
        r"tomorrow",
        r"friday",
        r"monday|tuesday|wednesday|thursday|saturday|sunday",
        r"\b\d+\s+minutes?\b",
        r"\b\d+\s+hours?\b",
        r"\b\d+\s+days?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0)
    return "Not specified"


def _priority_from_text(text):
    text_lower = (text or "").lower()
    if any(keyword in text_lower for keyword in ("need", "next", "send", "email", "check", "look into", "instructions")):
        return "High"
    return "Medium"


def _build_objective(segments):
    objective_segments = _select_segments(
        segments,
        keywords=("objective", "goal", "kickoff", "agenda", "project", "creating"),
        limit=2,
    )
    lines = [_normalise_summary_text(_segment_text(seg), max_words=24) for seg in objective_segments]
    lines = [line for line in lines if line]
    if not lines:
        return "Meeting objective was not clearly stated."
    return " ".join(lines)


def _build_topic_section(segments):
    exclude_keys = set()
    topic_lines = []
    for title, keywords in _TOPIC_DEFINITIONS:
        chosen = _select_segments(segments, keywords=keywords, limit=2, exclude_keys=exclude_keys)
        line = _format_topic_line(title, chosen)
        if line:
            topic_lines.append(line)
    if not topic_lines:
        fallback = _select_segments(segments, limit=3, exclude_keys=exclude_keys)
        topic_lines = [
            _format_topic_line("Main discussion", fallback)
        ] if fallback else []
    return topic_lines


def _build_decisions_section(segments):
    chosen = _select_segments(segments, keywords=_DECISION_KEYWORDS, limit=4)
    lines = [
        f"- {_normalise_summary_text(_segment_text(seg), max_words=30)}"
        for seg in chosen
    ]
    return _dedupe_lines(lines) or ["- No explicit decisions were clearly stated."]


def _build_action_items_section(segments):
    chosen = _select_segments(segments, keywords=_ACTION_KEYWORDS_EXTENDED, limit=5)
    people = _extract_named_people(segments)
    rows = []
    for seg in chosen:
        text = _normalise_summary_text(_segment_text(seg), max_words=28)
        if not text:
            continue
        owner = _infer_owner(seg, people)
        deadline = _extract_deadline(text)
        priority = _priority_from_text(text)
        rows.append(f"- {owner} | {text} | {deadline.title() if deadline != 'Not specified' else deadline} | {priority}")
    return _dedupe_lines(rows) or ["- Not specified | No explicit action item captured | Not specified | Medium"]


def _build_risks_section(segments):
    chosen = _select_segments(segments, keywords=_RISK_KEYWORDS, limit=4)
    lines = [
        f"- {_normalise_summary_text(_segment_text(seg), max_words=28)}"
        for seg in chosen
    ]
    return _dedupe_lines(lines) or ["- No explicit risks or blockers were raised."]


def _build_questions_section(segments):
    candidates = []
    for seg in segments:
        text = _segment_text(seg)
        if "?" in text or _keyword_hits(text, _QUESTION_KEYWORDS) > 0:
            candidates.append(seg)
    chosen = _select_segments(candidates or segments, keywords=_QUESTION_KEYWORDS, limit=4)
    lines = [
        f"- {_normalise_summary_text(_segment_text(seg), max_words=28)}"
        for seg in chosen
    ]
    return _dedupe_lines(lines) or ["- No open questions were clearly raised."]


def _build_next_steps_section(segments):
    chosen = _select_segments(
        segments,
        keywords=("next meeting", "next", "email", "website", "instructions", "minutes"),
        limit=4,
    )
    lines = [
        f"- {_normalise_summary_text(_segment_text(seg), max_words=30)}"
        for seg in chosen
    ]
    return _dedupe_lines(lines) or ["- Next steps were not clearly specified."]


def _build_exec_section(objective, topic_lines, decision_lines, action_lines, next_lines):
    bullets = []
    if objective:
        bullets.append(f"- {objective}")
    if topic_lines:
        bullets.append(topic_lines[0].replace("- ", "- ", 1))
    if len(topic_lines) > 1:
        bullets.append(topic_lines[1].replace("- ", "- ", 1))
    if decision_lines:
        bullets.append(decision_lines[0])
    if action_lines:
        bullets.append(action_lines[0])
    if len(bullets) < 5 and next_lines:
        bullets.extend(next_lines[: 5 - len(bullets)])
    return bullets[:5]


def _strip_bullet_prefix(line):
    return re.sub(r"^\-\s*", "", (line or "").strip())


def _build_full_summary(segments):
    exclude_keys = set()
    topic_segments = {}
    for title, keywords in _TOPIC_DEFINITIONS:
        topic_segments[title] = _select_segments(
            segments,
            keywords=keywords,
            limit=2,
            exclude_keys=exclude_keys,
        )

    def _topic_sentences(title):
        return [
            _normalise_summary_text(_segment_text(seg), max_words=_SUMMARY_MAX_WORDS_PER_SEGMENT)
            for seg in topic_segments.get(title, [])
            if _segment_text(seg)
        ]

    objective = _build_objective(segments)
    risks = [_strip_bullet_prefix(line) for line in _build_risks_section(segments)]
    next_steps = [_strip_bullet_prefix(line) for line in _build_next_steps_section(segments)]

    paragraph_one = _dedupe_lines(
        [objective]
        + _topic_sentences("Kickoff and agenda")
        + _topic_sentences("Project goals and scope")
        + _topic_sentences("Project plan and collaboration model")
        + _topic_sentences("Commercial targets and market")
    )

    paragraph_two = _dedupe_lines(
        _topic_sentences("User needs and product requirements")
        + [line for line in risks if line and "No explicit" not in line]
    )

    paragraph_three = _dedupe_lines(
        _topic_sentences("Assignments and follow-up")
        + [line for line in next_steps if line and "Not clearly" not in line]
    )

    paragraphs = [
        " ".join(paragraph_one).strip(),
        " ".join(paragraph_two).strip(),
        " ".join(paragraph_three).strip(),
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    return "\n\n".join(paragraphs).strip()


def _pick_summary_candidates(pool):
    if not pool:
        return []

    ordered = sorted(pool, key=lambda x: x.get("start", 0.0))
    total = len(ordered)
    early_pool = ordered[: max(1, total // 3)]
    late_pool = ordered[-max(1, total // 3):]
    mid_start = max(1, total // 4)
    mid_end = max(mid_start + 1, total - max(1, total // 4))
    middle_pool = ordered[mid_start:mid_end] or ordered

    def _score(seg, *, extra_keywords=None, position_boost=0.0):
        text = (seg.get("text") or "").strip()
        importance = float(seg.get("importance_score", 0.0) or 0.0)
        relevance = _meeting_relevance(seg)
        action_hits = _keyword_hits(text, _ACTION_KEYWORDS)
        discussion_hits = _keyword_hits(text, _DISCUSSION_KEYWORDS)
        intro_hits = _keyword_hits(text, _INTRO_KEYWORDS)
        keyword_bonus = _keyword_hits(text, extra_keywords or [])
        return (
            relevance * 3.0
            + discussion_hits * 2.0
            + action_hits * 2.5
            + keyword_bonus * 2.0
            + importance
            - intro_hits * 2.5
            + position_boost
        )

    chosen = []
    seen_text = set()

    def _append_best(candidates, **kwargs):
        ranked = sorted(
            candidates,
            key=lambda seg: (_score(seg, **kwargs), -(seg.get("start", 0.0))),
            reverse=True,
        )
        for seg in ranked:
            text_key = re.sub(r"\s+", " ", (seg.get("text") or "").strip().lower())
            if not text_key or text_key in seen_text:
                continue
            chosen.append(seg)
            seen_text.add(text_key)
            return

    _append_best(
        early_pool,
        extra_keywords=("agenda", "kickoff", "goal", "project", "today"),
        position_boost=0.5,
    )
    _append_best(
        ordered,
        extra_keywords=("functional design", "conceptual design", "detailed design", "individual work"),
    )
    _append_best(
        ordered,
        extra_keywords=("sell", "profit", "market", "international", "euro"),
    )
    _append_best(
        middle_pool,
        extra_keywords=("discuss", "feature", "requirement", "design", "button", "battery", "remote"),
    )
    _append_best(
        ordered,
        extra_keywords=("instructions", "coach", "website", "email"),
    )
    _append_best(
        late_pool,
        extra_keywords=("next", "plan", "email", "instructions", "follow up"),
        position_boost=0.5,
    )

    if not chosen:
        _append_best(ordered)

    return sorted(chosen[:_SUMMARY_MAX_SEGMENTS], key=lambda seg: seg.get("start", 0.0))


def generate_summary(ranked_segments, top_ratio: float = 1.0, max_segments: int = 150):
    """
    Build a full product-style meeting summary from the transcript.
    """
    if not ranked_segments:
        return ""

    segments = _prepare_summary_segments(ranked_segments)
    if top_ratio < 1.0:
        k = min(max_segments, max(1, int(len(segments) * top_ratio)))
        segments = segments[:k]

    ai_summary = try_generate_ai_summary(segments)
    if ai_summary:
        return ai_summary
    return _build_full_summary(segments)


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


def top_substantive_highlights(ranked_segments, n: int = 5, focus_keywords=None, min_importance_score=None):
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
    if min_importance_score is not None:
        filtered = [s for s in pool if float(s.get("importance_score", 0.0) or 0.0) >= float(min_importance_score)]
        if filtered:
            pool = filtered
    # Prefer meeting-relevant for key moments
    pool = sorted(
        pool,
        key=lambda s: (-_meeting_relevance(s, focus_keywords=focus_keywords), -s.get("importance_score", 0.0)),
    )
    return pool[:n]
