import copy
import json
import os
import threading
import uuid
from datetime import datetime, timezone

jobs = {}
jobs_lock = threading.Lock()

MEETINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "meetings")


def _use_postgres():
    return bool(os.getenv("DATABASE_URL"))


def _ensure_meetings_dir():
    os.makedirs(MEETINGS_DIR, exist_ok=True)


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _create_job_state(
    filename=None,
    preview=False,
    preview_seconds=None,
    related_job_id=None,
    persist_result=True,
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
        "updated_at": timestamp,
        "cancel_requested": False,
        "filename": filename or "meeting",
        "preview": bool(preview),
        "preview_seconds": preview_seconds,
        "related_job_id": related_job_id,
        "persist_result": bool(persist_result),
    }


def create_job(
    filename=None,
    preview=False,
    preview_seconds=None,
    related_job_id=None,
    persist_result=True,
):
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = _create_job_state(
            filename=filename,
            preview=preview,
            preview_seconds=preview_seconds,
            related_job_id=related_job_id,
            persist_result=persist_result,
        )
    return job_id


def update_job(job_id, **updates):
    with jobs_lock:
        if job_id not in jobs:
            return None
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


def update_job_progress(
    job_id,
    *,
    stage=None,
    stage_label=None,
    progress=None,
    eta_seconds=None,
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
    if eta_seconds is not None:
        payload["eta_seconds"] = float(max(0.0, eta_seconds))
    if partial_result is not None:
        payload["partial_result"] = partial_result
    return update_job(job_id, **payload)


def set_partial_result(job_id, partial_result):
    return update_job(job_id, partial_result=partial_result)


def set_related_job(job_id, related_job_id):
    return update_job(job_id, related_job_id=related_job_id)


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
    """Persist meeting to PostgreSQL (if DATABASE_URL set) or fallback to JSON files."""
    if _use_postgres():
        try:
            from database import save_meeting_to_db
            save_meeting_to_db(job_id, result, filename=filename)
        except Exception as e:
            # Fallback to file if DB fails (e.g. connection error)
            _save_meeting_file(job_id, result, filename=filename)
    else:
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
    """Return saved meetings (PostgreSQL or file) sorted by created_at descending."""
    if _use_postgres():
        try:
            from database import list_meetings_from_db
            return list_meetings_from_db()
        except Exception:
            pass
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
    """Load meeting result from memory, then PostgreSQL or file."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job and job.get("status") == "completed" and job.get("result"):
            return job["result"]
    if _use_postgres():
        try:
            from database import get_meeting_result_from_db
            result = get_meeting_result_from_db(job_id)
            if result is not None:
                return result
        except Exception:
            pass
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
    Delete a saved meeting from PostgreSQL or file storage.
    Also removes the associated recording file if present.
    """
    # Load result once so we can clean up the recording afterwards.
    result = get_meeting_result(job_id)

    removed = False
    if _use_postgres():
        try:
            from database import delete_meeting_from_db
            removed = delete_meeting_from_db(job_id)
        except Exception:
            removed = False
    else:
        path = os.path.join(MEETINGS_DIR, f"{job_id}.json")
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed = True
            except Exception:
                removed = False

    # Best-effort cleanup of the original recording file (if we know it).
    if result:
        recording_path = result.get("recording_path")
        if recording_path:
            backend_root = os.path.join(os.path.dirname(__file__), "..")
            full_path = os.path.join(backend_root, recording_path)
            if os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass

    # Also clear from in-memory jobs map if present.
    with jobs_lock:
        jobs.pop(job_id, None)

    return removed
