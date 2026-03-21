import copy
import re
from typing import Any, Dict


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d[\d\-\s]{7,}\d)\b")
_ID_RE = re.compile(r"\b(?:iit|uow|student)[-_ ]?\d{3,}\b", re.IGNORECASE)


def anonymize_text(text: str) -> str:
    if not text:
        return ""
    out = _EMAIL_RE.sub("[EMAIL]", text)
    out = _PHONE_RE.sub("[PHONE]", out)
    out = _ID_RE.sub("[ID]", out)
    return out


def anonymize_result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a copy of the result payload with sensitive text patterns masked.
    """
    safe = copy.deepcopy(result or {})

    if "summary" in safe and isinstance(safe["summary"], str):
        safe["summary"] = anonymize_text(safe["summary"])

    for key in ("transcript", "highlights"):
        items = safe.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and "text" in item:
                item["text"] = anonymize_text(item.get("text") or "")

    speaker_summaries = safe.get("speaker_summaries") or []
    if isinstance(speaker_summaries, list):
        for item in speaker_summaries:
            if isinstance(item, dict) and "summary" in item:
                item["summary"] = anonymize_text(item.get("summary") or "")

    return safe
