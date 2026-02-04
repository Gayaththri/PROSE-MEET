from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os

from pipeline.run_gap1 import run_gap1
from utils.audio_convert import convert_to_wav
from jobs import (
    create_job,
    update_job_status,
    complete_job,
    fail_job,
    get_job,
)

app = FastAPI(title="PROSE-MEET Gap 1 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def process_gap1_job(job_id: str, input_audio_path: str):
    try:
        update_job_status(job_id, "processing")

        # Convert if needed
        wav_path = convert_to_wav(input_audio_path)

        # Run Gap 1
        result = run_gap1(wav_path)

        complete_job(job_id, result)

    except Exception as e:
        fail_job(job_id, str(e))



@app.post("/run-gap1")
async def run_gap1_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Starts Gap 1 as an async background job.
    """

    os.makedirs("temp_audio", exist_ok=True)

    job_id = create_job()

    temp_input_path = os.path.join(
        "temp_audio", f"{job_id}_{file.filename}"
    )

    with open(temp_input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    background_tasks.add_task(
        process_gap1_job,
        job_id,
        temp_input_path
    )

    return {
        "job_id": job_id,
        "status": "queued",
    }


@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)

    if not job:
        return {"status": "not_found"}

    return {
        "status": job["status"],
        "error": job.get("error"),
    }


@app.get("/result/{job_id}")
def get_job_result(job_id: str):
    job = get_job(job_id)

    if not job:
        return {"error": "Job not found"}

    if job["status"] != "completed":
        return {
            "status": job["status"],
            "error": "Job not completed yet",
        }

    return job["result"]
