import uuid
import threading

jobs = {}

jobs_lock = threading.Lock()


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


def complete_job(job_id, result):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = result


def fail_job(job_id, error_message):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = error_message


def get_job(job_id):
    with jobs_lock:
        return jobs.get(job_id)
