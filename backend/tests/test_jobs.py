"""Tests for in-memory job tracking."""

import jobs


def test_create_and_complete_job():
    job_id = jobs.create_job(filename="demo.wav")

    assert job_id
    job = jobs.get_job(job_id)
    assert job is not None
    assert job["status"] == "queued"
    assert job["filename"] == "demo.wav"

    jobs.update_job_status(job_id, "processing", progress=0.5)
    jobs.complete_job(job_id, {"summary": "done"}, filename="demo.wav")

    finished = jobs.get_job(job_id)
    assert finished["status"] == "completed"
    assert finished["result"]["summary"] == "done"


def test_resolve_recording_path_rejects_traversal():
    assert jobs.resolve_recording_path("../../etc/passwd") is None
    assert jobs.resolve_recording_path("") is None
