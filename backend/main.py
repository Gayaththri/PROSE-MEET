import os
import shutil

# Load .env from backend directory so WHISPER_MODEL etc. can be set there
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

# Allow uploads up to 100 MB (default multipart limit is 1 MB)
MAX_UPLOAD_MB = 100

# Hugging Face: disable symlink warning on Windows; disable unauthenticated-request warning
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from pipeline.run_gap1 import run_gap1
from pipeline.asr import preload_model
from utils.audio_convert import convert_to_wav
from jobs import (
    create_job,
    update_job_status,
    complete_job,
    fail_job,
    get_job,
    list_meetings,
    get_meeting_result,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("DATABASE_URL"):
        try:
            from database import init_db
            init_db()
            print("PostgreSQL: tables ready.")
        except Exception as e:
            print(f"Warning: Database init failed: {e}. Meetings will use file fallback if DATABASE_URL is unset.")
    try:
        preload_model()
        print("Whisper model loaded and ready.")
    except Exception as e:
        print(f"Warning: Could not preload Whisper model: {e}. First transcription may be slow or fail.")
    yield
    # shutdown: nothing to clean up


app = FastAPI(title="PROSE-MEET Gap 1 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def form_with_large_limits(request: Request):
    """Parse multipart form with a 100 MB per-part limit so large audio files are accepted."""
    return await request.form(max_part_size=MAX_UPLOAD_MB * 1024 * 1024)


def process_gap1_job(job_id: str, input_audio_path: str, filename: str = None):
    try:
        update_job_status(job_id, "processing")
        wav_path = convert_to_wav(input_audio_path)
        result = run_gap1(wav_path)
        complete_job(job_id, result, filename=filename)
    except Exception as e:
        print(f"Job {job_id} failed: {e}")
        fail_job(job_id, str(e))



@app.post("/run-gap1")
async def run_gap1_endpoint(
    background_tasks: BackgroundTasks,
    form_data=Depends(form_with_large_limits),
):
    """
    Starts Gap 1 as an async background job. Accepts audio files up to 100 MB.
    """
    file: StarletteUploadFile = form_data.get("file")
    if not file or not isinstance(file, StarletteUploadFile):
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing or invalid 'file' in form data"},
        )

    os.makedirs("temp_audio", exist_ok=True)
    job_id = create_job()
    original_filename = file.filename or "audio"
    temp_input_path = os.path.join("temp_audio", f"{job_id}_{original_filename}")

    with open(temp_input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    background_tasks.add_task(process_gap1_job, job_id, temp_input_path, original_filename)

    return {"job_id": job_id, "status": "queued"}


@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)

    if not job:
        return {"status": "not_found"}

    return {
        "status": job["status"],
        "error": job.get("error"),
    }


@app.get("/meetings")
def list_meetings_endpoint():
    """List all saved meetings (persisted to disk). Survives server restart."""
    return list_meetings()


@app.get("/result/{job_id}")
def get_job_result(job_id: str):
    job = get_job(job_id)
    if job and job["status"] == "completed" and job.get("result"):
        return job["result"]
    # Load from disk (e.g. after reload or server restart)
    result = get_meeting_result(job_id)
    if result is not None:
        return result
    if job:
        if job["status"] != "completed":
            return {
                "status": job["status"],
                "error": "Job not completed yet",
            }
    return {"error": "Job not found"}
