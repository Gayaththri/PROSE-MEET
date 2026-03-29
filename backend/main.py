"""FastAPI entrypoint and request handling for PROSE-MEET."""

import asyncio
import os
import re
import shutil
import mimetypes
import logging
import time
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

# Allow uploads up to 100 MB (default multipart limit is 1 MB)
MAX_UPLOAD_MB = 100

# Persistent directory for original user recordings (audio/video)
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "recordings")

# Hugging Face: disable symlink warning on Windows; disable unauthenticated-request warning
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

from pipeline.run_gap1 import run_gap1
from pipeline.asr import preload_model
from pipeline.job_control import JobCancelledError
from pipeline.timing import TimingCollector, log_timing_report, timed_stage
from utils.audio_convert import convert_to_wav, create_preview_clip
from utils.anonymize import anonymize_result_payload
from jobs import (
    create_job,
    update_job,
    update_job_status,
    update_job_progress,
    set_partial_result,
    complete_job,
    fail_job,
    get_job,
    set_related_job,
    request_job_cancel,
    is_cancel_requested,
    cancel_job,
    list_meetings,
    get_meeting_result,
    delete_meeting,
    resolve_recording_path,
)


logger = logging.getLogger(__name__)
PREVIEW_SECONDS_DEFAULT = 45
PREVIEW_SECONDS_MIN = 30
PREVIEW_SECONDS_MAX = 60


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_preview_seconds(value) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = PREVIEW_SECONDS_DEFAULT
    return max(PREVIEW_SECONDS_MIN, min(PREVIEW_SECONDS_MAX, seconds))


def _close_upload_file(upload_file) -> None:
    """Close the uploaded file handle to avoid ResourceWarning (SpooledTemporaryFile)."""
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


def _estimate_eta_seconds(job_id: str, progress: Optional[float]) -> Optional[float]:
    if progress is None:
        return None
    if progress <= 0 or progress >= 1:
        return 0.0 if progress >= 1 else None
    job = get_job(job_id)
    started_at = _parse_started_at((job or {}).get("started_at"))
    if started_at is None:
        return None
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    if elapsed <= 0:
        return None
    return max(0.0, (elapsed / progress) - elapsed)


def _build_result_metadata(job_id: str, filename: str, preview: bool, preview_seconds: Optional[int], related_job_id: Optional[str]):
    return {
        "job_id": job_id,
        "filename": filename or "meeting",
        "is_preview": bool(preview),
        "preview_seconds": preview_seconds if preview else None,
        "related_job_id": related_job_id,
    }


def _progress_callback_for(job_id: str):
    def _callback(*, stage, stage_label, progress, partial_result=None):
        current_job = get_job(job_id) or {}
        update_job_progress(
            job_id,
            status="cancelling" if current_job.get("cancel_requested") else "processing",
            stage=stage,
            stage_label=stage_label,
            progress=progress,
            eta_seconds=_estimate_eta_seconds(job_id, progress),
            partial_result=partial_result,
        )

    return _callback


def _cancel_checker_for(job_id: str):
    return lambda: is_cancel_requested(job_id)


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

# Default covers common Vite ports (5174 when 5173 is busy) and localhost vs 127.0.0.1.
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
    """Parse multipart form with a 100 MB per-part limit so large audio files are accepted."""
    return await request.form(max_part_size=MAX_UPLOAD_MB * 1024 * 1024)


def process_gap1_job(
    job_id: str,
    input_audio_path: str,
    filename: str = None,
    preview: bool = False,
    preview_seconds: Optional[int] = None,
    related_job_id: Optional[str] = None,
):
    timing_collector = TimingCollector()
    timing_collector.set_metadata("job_id", job_id)
    timing_collector.set_metadata("filename", filename or "meeting")
    timing_collector.set_metadata("preview", bool(preview))
    temp_paths_to_cleanup = []
    try:
        if is_cancel_requested(job_id):
            cancel_job(job_id)
            return
        with timed_stage(timing_collector, "job_total"):
            update_job_status(
                job_id,
                "processing",
                stage="preparing_audio",
                stage_label="Preparing audio",
                progress=0.02,
            )

            processing_source_path = input_audio_path
            preserved_recording_path = None
            if not preview:
                # Persist the original user-uploaded recording alongside the meeting.
                os.makedirs(RECORDINGS_DIR, exist_ok=True)
                original_ext = os.path.splitext(input_audio_path)[1] or ""
                preserved_recording_path = os.path.join(
                    RECORDINGS_DIR, f"{job_id}{original_ext}"
                )
                with timed_stage(timing_collector, "persist_uploaded_recording"):
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
            if preview:
                with timed_stage(timing_collector, "create_preview_clip"):
                    source_for_pipeline = create_preview_clip(
                        processing_source_path,
                        preview_seconds or PREVIEW_SECONDS_DEFAULT,
                    )
                temp_paths_to_cleanup.append(source_for_pipeline)
            with timed_stage(timing_collector, "convert_to_wav"):
                wav_path = convert_to_wav(source_for_pipeline)
            if os.path.abspath(wav_path) != os.path.abspath(source_for_pipeline):
                temp_paths_to_cleanup.append(wav_path)
            result_metadata = _build_result_metadata(
                job_id=job_id,
                filename=filename or "meeting",
                preview=preview,
                preview_seconds=preview_seconds,
                related_job_id=related_job_id,
            )
            with timed_stage(timing_collector, "pipeline_run_gap1"):
                result = run_gap1(
                    wav_path,
                    timing_collector=timing_collector,
                    progress_callback=_progress_callback_for(job_id),
                    cancel_checker=_cancel_checker_for(job_id),
                    result_metadata=result_metadata,
                )
            if is_cancel_requested(job_id):
                raise JobCancelledError("Processing cancelled by user.")

            anonymize_enabled = os.getenv("ANONYMIZE_TRANSCRIPTS", "").lower() in ("1", "true", "yes")
            consent_status = os.getenv("MEETING_CONSENT_STATUS", "not_provided")
            if anonymize_enabled:
                with timed_stage(timing_collector, "anonymize_result"):
                    result = anonymize_result_payload(result)
            result["consent"] = {
                "status": consent_status,
                "anonymized": anonymize_enabled,
            }

            # Attach metadata so saved meetings know which file was analysed.
            result.update(result_metadata)
            if preserved_recording_path is not None:
                backend_root = os.path.join(os.path.dirname(__file__), "..")
                relative_recording_path = os.path.relpath(
                    preserved_recording_path, backend_root
                )
                result["recording_path"] = relative_recording_path

            with timed_stage(timing_collector, "complete_job_persist"):
                complete_job(
                    job_id,
                    result,
                    filename=filename,
                    persist_result=not preview,
                )
        log_timing_report(f"Job {job_id} timings:", timing_collector)
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



@app.post("/run-gap1")
async def run_gap1_endpoint(
    background_tasks: BackgroundTasks,
    form_data=Depends(form_with_large_limits),
):
    """
    Starts Gap 1 as an async background job. Accepts audio files up to 100 MB.
    Speakers are estimated from transcript timing and turn segmentation.
    """
    file: StarletteUploadFile = form_data.get("file")
    if not file or not isinstance(file, StarletteUploadFile):
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing or invalid 'file' in form data"},
        )
    preview = _parse_bool(form_data.get("preview"))
    preview_seconds = _parse_preview_seconds(form_data.get("preview_seconds"))
    related_job_id = form_data.get("related_job_id") or None

    os.makedirs("temp_audio", exist_ok=True)
    original_filename = _sanitize_upload_filename(file.filename or "audio")
    job_id = create_job(
        filename=original_filename,
        preview=preview,
        preview_seconds=preview_seconds if preview else None,
        related_job_id=related_job_id,
        persist_result=not preview,
    )
    if related_job_id:
        set_related_job(related_job_id, job_id)
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
        preview,
        preview_seconds if preview else None,
        related_job_id,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "is_preview": preview,
        "preview_seconds": preview_seconds if preview else None,
        "related_job_id": related_job_id,
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
        "is_preview": job.get("preview", False),
        "preview_seconds": job.get("preview_seconds"),
        "related_job_id": job.get("related_job_id"),
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


@app.get("/recording/{job_id}")
def get_recording(job_id: str):
    """
    Serve the original recording (audio/video) associated with a completed meeting.
    """
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


@app.delete("/meetings/{job_id}")
def delete_meeting_endpoint(job_id: str):
    """Delete a saved meeting and its associated recording (if any)."""
    ok = delete_meeting(job_id)
    if not ok:
        return JSONResponse(
            status_code=404, content={"detail": "Meeting not found or already deleted"}
        )
    return JSONResponse(status_code=204, content=None)

@app.get("/meetings")
def list_meetings_endpoint():
    """List all saved meetings (persisted to disk). Survives server restart."""
    return list_meetings()


@app.get("/result/{job_id}")
def get_job_result(job_id: str, allow_partial: bool = False):
    job = get_job(job_id)
    if job and job["status"] == "completed" and job.get("result"):
        return job["result"]
    if allow_partial and job and job.get("partial_result") is not None:
        return job["partial_result"]
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
