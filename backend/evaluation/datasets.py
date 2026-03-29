"""Dataset loading and validation helpers for evaluation."""

import csv
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


REQUIRED_MANIFEST_COLUMNS = [
    "id",
    "audio_path",
    "transcript_ref_path",
    "summary_ref_path",
    "domain",
    "split",
]


@dataclass
class MeetingReference:
    transcript_text: Optional[str]
    summary_text: Optional[str]
    utterances: List[Dict[str, Any]]


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _normalise_utterances(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        start = item.get("start")
        end = item.get("end")
        out.append(
            {
                "id": item.get("id", idx),
                "text": text,
                "start": float(start) if start is not None else None,
                "end": float(end) if end is not None else None,
                "important": item.get("important"),
            }
        )
    return out


def _load_transcript_reference(path: str) -> tuple[Optional[str], List[Dict[str, Any]]]:
    if not path or not os.path.isfile(path):
        return None, []

    if path.lower().endswith(".txt"):
        return _read_text_file(path), []

    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if isinstance(payload, dict):
            # Supports persisted meeting payload format: {"result": {"transcript": [...], "summary": "..."}}
            if isinstance(payload.get("result"), dict):
                result_obj = payload.get("result") or {}
                transcript_obj = result_obj.get("transcript")
                if isinstance(transcript_obj, list):
                    utterances = _normalise_utterances(transcript_obj)
                    transcript = " ".join(u["text"] for u in utterances).strip()
                    return transcript or None, utterances
                if isinstance(transcript_obj, str):
                    return transcript_obj.strip(), []
            if isinstance(payload.get("utterances"), list):
                utterances = _normalise_utterances(payload["utterances"])
                if payload.get("transcript"):
                    return str(payload["transcript"]).strip(), utterances
                transcript = " ".join(u["text"] for u in utterances).strip()
                return transcript or None, utterances
            if isinstance(payload.get("transcript"), str):
                return payload["transcript"].strip(), []

        if isinstance(payload, list):
            utterances = _normalise_utterances(payload)
            transcript = " ".join(u["text"] for u in utterances).strip()
            return transcript or None, utterances

    # Fallback: treat as plain text.
    return _read_text_file(path), []


def _load_summary_reference(path: str) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    if path.lower().endswith(".txt"):
        return _read_text_file(path)
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            if isinstance(payload.get("result"), dict):
                result_obj = payload.get("result") or {}
                if isinstance(result_obj.get("summary"), str):
                    return result_obj["summary"].strip()
            if isinstance(payload.get("summary"), str):
                return payload["summary"].strip()
            if isinstance(payload.get("text"), str):
                return payload["text"].strip()
        if isinstance(payload, str):
            return payload.strip()
    return _read_text_file(path)


def load_manifest(manifest_path: str) -> List[Dict[str, str]]:
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        missing = [c for c in REQUIRED_MANIFEST_COLUMNS if c not in cols]
        if missing:
            raise ValueError(
                f"Manifest missing required columns: {', '.join(missing)}"
            )
        rows = [dict(r) for r in reader]
    if not rows:
        raise ValueError("Manifest is empty.")
    return rows


def load_meeting_reference(manifest_row: Dict[str, str], workspace_root: str) -> MeetingReference:
    transcript_path = resolve_path(manifest_row.get("transcript_ref_path"), workspace_root)
    summary_path = resolve_path(manifest_row.get("summary_ref_path"), workspace_root)
    transcript_text, utterances = _load_transcript_reference(transcript_path)
    summary_text = _load_summary_reference(summary_path)
    return MeetingReference(
        transcript_text=transcript_text,
        summary_text=summary_text,
        utterances=utterances,
    )


def resolve_path(path: Optional[str], workspace_root: str) -> str:
    if not path:
        return ""
    path = path.strip()
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(workspace_root, path))
