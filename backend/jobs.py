import json
import os
import threading
import uuid
from datetime import datetime

jobs = {}
jobs_lock = threading.Lock()

MEETINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "meetings")


def _use_postgres():
    return bool(os.getenv("DATABASE_URL"))


def _ensure_meetings_dir():
    os.makedirs(MEETINGS_DIR, exist_ok=True)


def create_job():
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "result": None,
            "error": None,
        }
    return job_id


def update_job_status(job_id, status):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = status


def complete_job(job_id, result, filename=None):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = result
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
    path = os.path.join(MEETINGS_DIR, f"{job_id}.json")
    payload = {
        "id": job_id,
        "filename": filename or "meeting",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "result": result,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=0)


def fail_job(job_id, error_message):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = error_message


def get_job(job_id):
    with jobs_lock:
        return jobs.get(job_id)


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
            out.append({
                "id": data.get("id", name.replace(".json", "")),
                "filename": data.get("filename", "meeting"),
                "created_at": data.get("created_at", ""),
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
        return data.get("result")
    except Exception:
        return None
