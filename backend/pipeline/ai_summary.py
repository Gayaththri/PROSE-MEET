import json
import os
import re
import urllib.error
import urllib.request


_DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_TIMEOUT_SECONDS = 45
_MAX_TRANSCRIPT_CHARS = 18000

_SYSTEM_PROMPT = """You are a meeting intelligence assistant.
Create a product-grade meeting summary from the transcript.

Rules:
- Use only information grounded in the transcript.
- Remove filler, repetition, greetings, and low-value chatter.
- Keep wording professional, precise, and readable.
- Capture the real flow of the meeting, not just the start/end.
- Preserve concrete details such as prices, timings, targets, and commitments.
- Paraphrase in your own words; do not copy transcript sentences verbatim.
- Never output long direct quotes from speakers.
- Return plain text only.
- Write a full meeting summary, not a short generic paragraph.
- Use 2-4 well-written paragraphs.
- Do not use headings, numbering, bullets, or transcript-style fragments.
- Make it read like a real AI-generated meeting summary.
"""


def _summary_enabled():
    return bool(os.getenv("LLM_SUMMARY_MODEL")) and bool(
        os.getenv("OPENAI_API_KEY") or os.getenv("LLM_SUMMARY_API_KEY")
    )


def _build_transcript_text(segments):
    lines = []
    for seg in segments:
        text = re.sub(r"\s+", " ", (seg.get("text") or "").strip())
        if not text:
            continue
        speaker = (seg.get("speaker") or "").strip()
        start = seg.get("start")
        prefix = f"[{start:.1f}s]" if isinstance(start, (int, float)) else ""
        if speaker:
            lines.append(f"{prefix} {speaker}: {text}".strip())
        else:
            lines.append(f"{prefix} {text}".strip())
    transcript = "\n".join(lines).strip()
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:_MAX_TRANSCRIPT_CHARS].rstrip() + "\n...[truncated]"
    return transcript


def _normalise_line(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _looks_templated_or_extractive(summary_text, transcript_text):
    text = (summary_text or "").strip()
    if not text:
        return True

    # Reject the sectioned template style (e.g., "1) Meeting objective")
    if re.search(r"(?mi)^\s*\d+\)\s*(meeting objective|main discussion points|decisions made|action items|open questions|next steps|executive summary)", text):
        return True

    # Reject bullet/number-heavy outputs even if headings differ
    if len(re.findall(r"(?m)^\s*[-*]\s+", text)) >= 3:
        return True
    if len(re.findall(r"(?m)^\s*\d+[.)]\s+", text)) >= 3:
        return True

    # Reject quote-heavy outputs or direct transcript line copying
    quote_count = len(re.findall(r"[\"“”']", text))
    if quote_count >= 8:
        return True

    transcript_lines = {
        _normalise_line(line)
        for line in transcript_text.splitlines()
        if _normalise_line(line)
    }
    copied_line_hits = 0
    for line in text.splitlines():
        norm = _normalise_line(line)
        if len(norm) < 50:
            continue
        if norm in transcript_lines:
            copied_line_hits += 1
            if copied_line_hits >= 2:
                return True

    return False


def try_generate_ai_summary(segments):
    if not _summary_enabled():
        return None

    transcript = _build_transcript_text(segments)
    if not transcript:
        return None

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_SUMMARY_API_KEY")
    model = os.getenv("LLM_SUMMARY_MODEL")
    api_url = os.getenv("LLM_SUMMARY_API_URL", _DEFAULT_API_URL)
    timeout_seconds = int(
        os.getenv("LLM_SUMMARY_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)) or _DEFAULT_TIMEOUT_SECONDS
    )

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Transcript:\n" + transcript,
            },
        ],
    }

    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None

    choices = body.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        return None
    content = content.strip()
    if not content:
        return None

    if _looks_templated_or_extractive(content, transcript):
        return None
    return content
