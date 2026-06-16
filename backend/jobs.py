"""Backend job tracker"""

import copy
import json
import os
import threading
import uuid
from datetime import datetime, timezone

jobs = {}
jobs_lock = threading.Lock()

MEETINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "meetings")
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_RECORDINGS_ROOT = os.path.abspath(os.path.join(_BACKEND_ROOT, "data", "recordings"))


def _ensure_meetings_dir():
    os.makedirs(MEETINGS_DIR, exist_ok=True)


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_recording_path(recording_path: str):
    """
    Resolve a stored recording path to an absolute path under data/recordings.
    Returns None when path is empty, invalid, or outside the recordings root.
    """
    if not recording_path or not isinstance(recording_path, str):
        return None
    try:
        candidate = os.path.abspath(os.path.join(_BACKEND_ROOT, recording_path))
        common = os.path.commonpath([_RECORDINGS_ROOT, candidate])
        if common != _RECORDINGS_ROOT:
            return None
        return candidate
    except Exception:
        return None

#Builds initial template for every new job
def _create_job_state(
    filename=None,
):
    timestamp = _now_iso()
    return {
        "status": "queued",
        "result": None,
        "partial_result": None,
        "error": None,
        "stage": "queued",
        "stage_label": "Queued",
        "progress": 0.0,
        "eta_seconds": None,
        "started_at": timestamp,
        "processing_started_at": None,
        "audio_duration_seconds": None,
        "updated_at": timestamp,
        "cancel_requested": False,
        "filename": filename or "meeting",
    }

#Creates a new job 
def create_job(
    filename=None,
):
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = _create_job_state(
            filename=filename,
        )
    return job_id


def update_job(job_id, **updates):
    with jobs_lock:
        if job_id not in jobs:
            return None
        if updates.get("status") == "processing":
            if (
                jobs[job_id].get("processing_started_at") is None
                and "processing_started_at" not in updates
            ):
                updates = {**updates, "processing_started_at": _now_iso()}
        jobs[job_id].update(updates)
        jobs[job_id]["updated_at"] = _now_iso()
        return copy.deepcopy(jobs[job_id])


def update_job_status(job_id, status, **extra):
    payload = {"status": status}
    payload.update(extra)
    if status == "queued":
        payload.setdefault("progress", 0.0)
        payload.setdefault("stage", "queued")
        payload.setdefault("stage_label", "Queued")
    elif status == "processing":
        payload.setdefault("stage", "starting")
        payload.setdefault("stage_label", "Starting analysis")
    elif status == "completed":
        payload.setdefault("progress", 1.0)
        payload.setdefault("stage", "completed")
        payload.setdefault("stage_label", "Completed")
        payload.setdefault("eta_seconds", 0.0)
    elif status == "failed":
        payload.setdefault("stage", "failed")
        payload.setdefault("stage_label", "Failed")
    elif status == "cancelling":
        payload.setdefault("stage_label", "Cancelling")
    elif status == "cancelled":
        payload.setdefault("progress", 1.0)
        payload.setdefault("stage", "cancelled")
        payload.setdefault("stage_label", "Cancelled")
        payload.setdefault("eta_seconds", 0.0)
    return update_job(job_id, **payload)

# When omitted, leave existing eta_seconds on the job unchanged.
_ETA_SECONDS_OMIT = object()


# live progress updates
def update_job_progress(
    job_id,
    *,
    stage=None,
    stage_label=None,
    progress=None,
    eta_seconds=_ETA_SECONDS_OMIT,
    partial_result=None,
    status=None,
    **extra,
):
    payload = dict(extra)
    if status:
        payload["status"] = status
    if stage is not None:
        payload["stage"] = stage
    if stage_label is not None:
        payload["stage_label"] = stage_label
    if progress is not None:
        payload["progress"] = float(max(0.0, min(1.0, progress)))
    if eta_seconds is not _ETA_SECONDS_OMIT:
        if eta_seconds is None:
            payload["eta_seconds"] = None
        else:
            payload["eta_seconds"] = float(max(0.0, eta_seconds))
    if partial_result is not None:
        payload["partial_result"] = partial_result
    return update_job(job_id, **payload)


def set_partial_result(job_id, partial_result):
    return update_job(job_id, partial_result=partial_result)


def request_job_cancel(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return False
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return False
        job["cancel_requested"] = True
        if job.get("status") == "queued":
            job["status"] = "cancelled"
            job["stage"] = "cancelled"
            job["stage_label"] = "Cancelled"
            job["progress"] = 1.0
            job["eta_seconds"] = 0.0
            job["error"] = "Processing cancelled by user."
        elif job.get("status") != "cancelled":
            job["status"] = "cancelling"
            job["stage_label"] = "Cancelling"
        job["updated_at"] = _now_iso()
        return True


def is_cancel_requested(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        return bool(job and job.get("cancel_requested"))


def cancel_job(job_id, message="Processing cancelled by user."):
    return update_job_status(
        job_id,
        "cancelled",
        error=message,
        cancel_requested=True,
        partial_result=None,
    )


def complete_job(job_id, result, filename=None, persist_result=True):
    # Ensure transcript is always chronological before exposing/saving result.
    if isinstance(result, dict) and isinstance(result.get("transcript"), list):
        result["transcript"] = sorted(
            result["transcript"],
            key=lambda x: float((x or {}).get("start", 0.0) or 0.0),
        )
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = result
            jobs[job_id]["partial_result"] = None
            jobs[job_id]["progress"] = 1.0
            jobs[job_id]["stage"] = "completed"
            jobs[job_id]["stage_label"] = "Completed"
            jobs[job_id]["eta_seconds"] = 0.0
            jobs[job_id]["updated_at"] = _now_iso()
    if persist_result:
        save_meeting(job_id, result, filename)


def save_meeting(job_id, result, filename=None):
    """Persist meeting as JSON under data/meetings/."""
    _save_meeting_file(job_id, result, filename=filename)


def _save_meeting_file(job_id, result, filename=None):
    _ensure_meetings_dir()
    if isinstance(result, dict) and isinstance(result.get("transcript"), list):
        result["transcript"] = sorted(
            result["transcript"],
            key=lambda x: float((x or {}).get("start", 0.0) or 0.0),
        )
    path = os.path.join(MEETINGS_DIR, f"{job_id}.json")
    payload = {
        "id": job_id,
        "filename": filename or "meeting",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "result": result,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=0)


def fail_job(job_id, error_message):
    update_job_status(job_id, "failed", error=error_message)


def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        return copy.deepcopy(job) if job is not None else None


def list_meetings():
    """Return saved meetings from JSON files, sorted by created_at descending."""
    _ensure_meetings_dir()
    out = []
    for name in os.listdir(MEETINGS_DIR):
        if not name.endswith(".json"):
            continue
        path = os.path.join(MEETINGS_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = data.get("result") or {}
            out.append({
                "id": data.get("id", name.replace(".json", "")),
                "filename": data.get("filename", "meeting"),
                "created_at": data.get("created_at", ""),
                "duration_seconds": result.get("duration_seconds"),
            })
        except Exception:
            continue
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def get_meeting_result(job_id):
    """Load meeting result from memory, then from JSON file."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job and job.get("status") == "completed" and job.get("result"):
            return job["result"]
    path = os.path.join(MEETINGS_DIR, f"{job_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = data.get("result") or {}
        # Ensure filename is on result for overview panel (from wrapper if not in result)
        if "filename" not in result:
            result["filename"] = data.get("filename") or "meeting"
        return result
    except Exception:
        return None


def delete_meeting(job_id: str):
    """
    Delete a saved meeting JSON file and remove the associated recording if present.
    """
    # Load result once so we can clean up the recording afterwards.
    result = get_meeting_result(job_id)

    removed = False
    path = os.path.join(MEETINGS_DIR, f"{job_id}.json")
    if os.path.isfile(path):
        try:
            os.remove(path)
            removed = True
        except Exception:
            removed = False

    if removed and result:
        recording_path = result.get("recording_path")
        if recording_path:
            full_path = resolve_recording_path(recording_path)
            if full_path and os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass

    with jobs_lock:
        jobs.pop(job_id, None)

    return removed
