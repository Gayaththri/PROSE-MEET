from fastapi import FastAPI, UploadFile, File
import shutil
import os
import uuid

from pipeline.run_gap1 import run_gap1
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PROSE-MEET Gap 1 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/run-gap1")
async def run_gap1_endpoint(file: UploadFile = File(...)):
    """
    Run prosody-aware importance detection (Gap 1)
    on an uploaded meeting audio file.
    """

    # Create temp directory if not exists
    os.makedirs("temp_audio", exist_ok=True)

    # Save uploaded file
    file_id = str(uuid.uuid4())
    temp_path = f"temp_audio/{file_id}_{file.filename}"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Run Gap 1 pipeline
    result = run_gap1(temp_path)

    return {
        "transcript": result["transcript"],
        "summary": result["summary"],
        "highlights": result["highlights"],
        "speakers": result["speakers"]
    }
