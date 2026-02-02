from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

import shutil
import os
import uuid

from pipeline.run_gap1 import run_gap1
from utils.audio_convert import convert_to_wav


app = FastAPI(title="PROSE-MEET Gap 1 API")

# =========================
# CORS CONFIGURATION
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# GAP 1 ENDPOINT
# =========================
@app.post("/run-gap1")
async def run_gap1_endpoint(file: UploadFile = File(...)):
    """
    Run prosody-aware importance detection (Gap 1)
    on an uploaded or recorded meeting audio file.

    Supports heterogeneous audio formats by normalizing
    to WAV (16kHz, mono) before analysis.
    """

    # 1. Ensure temp directory exists
    temp_dir = "temp_audio"
    os.makedirs(temp_dir, exist_ok=True)

    # 2. Save uploaded file (webm / wav / mp3 / etc.)
    file_id = str(uuid.uuid4())
    temp_input_path = os.path.join(
        temp_dir, f"{file_id}_{file.filename}"
    )

    with open(temp_input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 3. Normalize audio format → WAV (16kHz, mono)
    wav_path = convert_to_wav(temp_input_path)

    # 4. Run Gap 1 pipeline ONLY on normalized WAV
    result = run_gap1(wav_path)

    # 5. Return structured response to frontend
    return {
        "transcript": result["transcript"],
        "summary": result["summary"],
        "highlights": result["highlights"],
        "speakers": result["speakers"],
    }
