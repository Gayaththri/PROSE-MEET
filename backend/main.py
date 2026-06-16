"""FastAPI entrypoint and request handling for PROSE-MEET."""

import asyncio
import os
import re
import shutil
import mimetypes
import logging
from datetime import datetime, timezone
from typing import Optional

# Load .env from backend directory so WHISPER_MODEL etc. can be set there
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

# Allow uploads up to 100 MB
MAX_UPLOAD_MB = 100

# Original uploaded recordings are stored
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "recordings")

# Hugging Face: disable symlink warning on Windows; disable unauthenticated-request warning
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from pipeline.run_gap1 import run_gap1
from pipeline.asr import preload_model
from pipeline.job_control import JobCancelledError
from pipeline.audio_convert import convert_to_wav
from jobs import (
    create_job,
    update_job,
    update_job_status,
    update_job_progress,
    set_partial_result,
    complete_job,
    fail_job,
    get_job,
    request_job_cancel,
    is_cancel_requested,
    cancel_job,
    list_meetings,
    get_meeting_result,
    delete_meeting,
    resolve_recording_path,
)

# logging
logger = logging.getLogger(__name__)

def _close_upload_file(upload_file) -> None:
    if getattr(upload_file, "file", None) is not None:
        try:
            upload_file.file.close()
        except Exception:
            pass


def _sanitize_upload_filename(filename: Optional[str]) -> str:
    raw = (filename or "audio").strip()
    base = os.path.basename(raw) or "audio"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return safe or "audio"


def _parse_started_at(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# Progress time fraction
_PROGRESS_TIME_FRAC = (
    (0.0, 0.0),
    (0.02, 0.02),
    (0.08, 0.06),
    (0.26, 0.22),
    (0.42, 0.58),
    (0.54, 0.66),
    (0.64, 0.72),
    (0.72, 0.78),
    (0.80, 0.82),
    (0.86, 0.86),
    (0.92, 0.90),
    (0.96, 0.95),
    (1.0, 1.0),
)


def _progress_time_fraction(progress: float) -> float:
    p = max(0.0, min(1.0, float(progress)))
    pairs = _PROGRESS_TIME_FRAC
    if p <= pairs[0][0]:
        return pairs[0][1]
    for i in range(len(pairs) - 1):
        p0, t0 = pairs[i]
        p1, t1 = pairs[i + 1]
        if p <= p1:
            if p1 <= p0:
                return t1
            return t0 + (t1 - t0) * (p - p0) / (p1 - p0)
    return pairs[-1][1]


def _pipeline_budget_seconds(duration: float) -> float:
    if duration is None or duration < 0:
        return 0.0
    rtf = float(os.getenv("PROSE_ASR_RTF", "0.22"))
    post_base = float(os.getenv("PROSE_POST_TRANSCRIBE_SEC", "32"))
    post_per_min = float(os.getenv("PROSE_POST_TRANSCRIBE_PER_MIN", "7"))
    overhead = float(os.getenv("PROSE_PIPELINE_OVERHEAD_SEC", "14"))
    post = post_base + (duration / 60.0) * post_per_min
    return overhead + duration * rtf + post

# Round eta to the nearest step
def _round_eta_seconds(eta: float) -> float:
    if eta <= 0:
        return 0.0
    if eta < 90:
        step = 5.0
    elif eta < 300:
        step = 10.0
    else:
        step = 15.0
    return float(max(step, round(eta / step) * step))

# Estimate ETA seconds
def _estimate_eta_seconds(
    job_id: str,
    progress: Optional[float],
    *,
    audio_duration_seconds: Optional[float] = None,
) -> Optional[float]:
    if progress is None:
        return None
    if progress <= 0 or progress >= 1:
        return 0.0 if progress >= 1 else None
    job = get_job(job_id) or {}
    ref = _parse_started_at(job.get("processing_started_at"))
    if ref is None:
        return None
    elapsed = (datetime.now(timezone.utc) - ref).total_seconds()
    if elapsed <= 0:
        return None

    t_sched = min(1.0, max(0.0, _progress_time_fraction(progress)))

    duration = audio_duration_seconds
    if duration is None:
        raw = job.get("audio_duration_seconds")
        if raw is not None:
            try:
                duration = float(raw)
            except (TypeError, ValueError):
                duration = None

    if duration is not None and duration >= 0:
        budget = _pipeline_budget_seconds(duration)
        if budget <= 0:
            return None
        remaining_wall = max(0.0, budget - elapsed)
        remaining_schedule = max(0.0, budget * (1.0 - t_sched))
        raw_eta = min(remaining_wall, remaining_schedule)
        return _round_eta_seconds(raw_eta)

    return None


def _build_result_metadata(job_id: str, filename: str):
    return {
        "job_id": job_id,
        "filename": filename or "meeting",
    }

# Progress callback for the pipeline
def _progress_callback_for(job_id: str):
    def _callback(
        *,
        stage,
        stage_label,
        progress,
        partial_result=None,
        audio_duration_seconds=None,
    ):
        current_job = get_job(job_id) or {}
        payload = {}
        if audio_duration_seconds is not None:
            payload["audio_duration_seconds"] = float(audio_duration_seconds)
        update_job_progress(
            job_id,
            status="cancelling" if current_job.get("cancel_requested") else "processing",
            stage=stage,
            stage_label=stage_label,
            progress=progress,
            eta_seconds=_estimate_eta_seconds(
                job_id,
                progress,
                audio_duration_seconds=audio_duration_seconds,
            ),
            partial_result=partial_result,
            **payload,
        )

    return _callback


def _cancel_checker_for(job_id: str):
    return lambda: is_cancel_requested(job_id)

# pre load whisper model
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        preload_model()
        print("Whisper model loaded and ready.")
    except Exception as e:
        print(f"Warning: Could not preload Whisper model: {e}. First transcription may be slow or fail.")
    yield
    # shutdown: nothing to clean up

# Create the main FastAPI app
app = FastAPI(title="PROSE-MEET Gap 1 API", lifespan=lifespan)

# Set up CORS middleware
_default_cors_origins = (
    "http://localhost:5173,http://localhost:5174,"
    "http://127.0.0.1:5173,http://127.0.0.1:5174"
)
_cors_origins = os.getenv("BACKEND_CORS_ORIGINS", _default_cors_origins)
_cors_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def form_with_large_limits(request: Request):
    return await request.form(max_part_size=MAX_UPLOAD_MB * 1024 * 1024)

# Background job runner
def process_gap1_job(
    job_id: str,
    input_audio_path: str,
    filename: str = None,
):
    temp_paths_to_cleanup = []
    try:
        if is_cancel_requested(job_id):
            cancel_job(job_id)
            return
        update_job_status(
            job_id,
            "processing",
            stage="preparing_audio",
            stage_label="Preparing audio",
            progress=0.02,
        )

        processing_source_path = input_audio_path
        preserved_recording_path = None
        # Persist the original user uploaded recording alongside the meeting.
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        original_ext = os.path.splitext(input_audio_path)[1] or ""
        preserved_recording_path = os.path.join(
            RECORDINGS_DIR, f"{job_id}{original_ext}"
        )
        try:
            if os.path.abspath(input_audio_path) != os.path.abspath(preserved_recording_path):
                shutil.move(input_audio_path, preserved_recording_path)
                processing_source_path = preserved_recording_path
            else:
                processing_source_path = input_audio_path
        except Exception:
            try:
                shutil.copy2(input_audio_path, preserved_recording_path)
            except Exception:
                preserved_recording_path = None
        if is_cancel_requested(job_id):
            raise JobCancelledError("Processing cancelled by user.")

        # Always run the pipeline on a WAV version of the recording.
        source_for_pipeline = processing_source_path
        wav_path = convert_to_wav(source_for_pipeline)
        if os.path.abspath(wav_path) != os.path.abspath(source_for_pipeline):
            temp_paths_to_cleanup.append(wav_path)
        result_metadata = _build_result_metadata(
            job_id=job_id,
            filename=filename or "meeting",
        )
        result = run_gap1(
            wav_path,
            progress_callback=_progress_callback_for(job_id),
            cancel_checker=_cancel_checker_for(job_id),
            result_metadata=result_metadata,
        )
        if is_cancel_requested(job_id):
            raise JobCancelledError("Processing cancelled by user.")

        consent_status = os.getenv("MEETING_CONSENT_STATUS", "not_provided")
        result["consent"] = {
            "status": consent_status,
            "anonymized": False,
        }

        # Attach metadata so saved meetings know which file was analysed.
        result.update(result_metadata)
        if preserved_recording_path is not None:
            backend_root = os.path.join(os.path.dirname(__file__), "..")
            relative_recording_path = os.path.relpath(
                preserved_recording_path, backend_root
            )
            result["recording_path"] = relative_recording_path

        complete_job(
            job_id,
            result,
            filename=filename,
        )
    except JobCancelledError as e:
        cancel_job(job_id, str(e))
    except Exception as e:
        print(f"Job {job_id} failed: {e}")
        logger.exception("Job %s failed during processing.", job_id)
        fail_job(job_id, "Processing failed. Please try again.")
    finally:
        for path in temp_paths_to_cleanup:
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if os.path.isfile(input_audio_path):
            try:
                os.remove(input_audio_path)
            except Exception:
                pass


# Run Gap 1 endpoint
@app.post("/run-gap1")
async def run_gap1_endpoint(
    background_tasks: BackgroundTasks,
    form_data=Depends(form_with_large_limits),
):
    """
    Starts Gap 1 as an async background job. Accepts audio files up to 100 MB.
    Runs the Gap 1 meeting analysis pipeline as a background job.
    """
    file: StarletteUploadFile = form_data.get("file")
    if not file or not isinstance(file, StarletteUploadFile):
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing or invalid 'file' in form data"},
        )
    os.makedirs("temp_audio", exist_ok=True)
    original_filename = _sanitize_upload_filename(file.filename or "audio")
    job_id = create_job(filename=original_filename)
    temp_input_path = os.path.join("temp_audio", f"{job_id}_{original_filename}")

    try:
        with open(temp_input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        # Close the uploaded file handle to avoid ResourceWarning (SpooledTemporaryFile)
        _close_upload_file(file)
        if hasattr(file, "close") and callable(file.close):
            try:
                if asyncio.iscoroutinefunction(file.close):
                    await file.close()
                else:
                    file.close()
            except Exception:
                pass

    background_tasks.add_task(
        process_gap1_job,
        job_id,
        temp_input_path,
        original_filename,
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

    response = {
        "status": job["status"],
        "error": job.get("error"),
        "stage": job.get("stage"),
        "stage_label": job.get("stage_label"),
        "progress": job.get("progress"),
        "eta_seconds": job.get("eta_seconds"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "cancel_requested": job.get("cancel_requested", False),
    }
    if job.get("partial_result") is not None:
        response["partial_result"] = job.get("partial_result")
    return response


@app.post("/jobs/{job_id}/cancel")
def cancel_job_endpoint(job_id: str):
    job = get_job(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"status": "not_found"})
    if not request_job_cancel(job_id):
        refreshed = get_job(job_id) or {}
        return {
            "status": refreshed.get("status", "not_found"),
            "error": refreshed.get("error"),
        }
    refreshed = get_job(job_id) or {}
    return {
        "status": refreshed.get("status", "cancelling"),
        "error": refreshed.get("error"),
        "cancel_requested": True,
    }

# Get recording endpoint
@app.get("/recording/{job_id}")
def get_recording(job_id: str):
    result = get_meeting_result(job_id)
    if not result:
        return JSONResponse(
            status_code=404, content={"detail": "Recording not found for this meeting"}
        )

    recording_path = result.get("recording_path")
    if not recording_path:
        return JSONResponse(
            status_code=404,
            content={"detail": "This meeting does not have a saved recording"},
        )

    full_path = resolve_recording_path(recording_path)
    if not full_path or not os.path.isfile(full_path):
        return JSONResponse(
            status_code=404, content={"detail": "Recording file is missing on server"}
        )

    media_type, _ = mimetypes.guess_type(full_path)
    return FileResponse(full_path, media_type=media_type or "application/octet-stream")

# Delete meeting endpoint
@app.delete("/meetings/{job_id}")
def delete_meeting_endpoint(job_id: str):
    ok = delete_meeting(job_id)
    if not ok:
        return JSONResponse(
            status_code=404, content={"detail": "Meeting not found or already deleted"}
        )
    return JSONResponse(status_code=204, content=None)

# List meetings endpoint
@app.get("/meetings")
def list_meetings_endpoint():
    return list_meetings()

# Get job result endpoint
@app.get("/result/{job_id}")
def get_job_result(job_id: str, allow_partial: bool = False):
    job = get_job(job_id)
    if job and job["status"] == "completed" and job.get("result"):
        return job["result"]
    if allow_partial and job and job.get("partial_result") is not None:
        return job["partial_result"]
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
