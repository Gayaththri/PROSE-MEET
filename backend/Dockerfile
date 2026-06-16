# PROSE-MEET backend — FastAPI + faster-whisper + FFmpeg (Railway / Docker)
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch keeps the image smaller on Railway
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

# Runtime data lives one level above /app (matches jobs.py / main.py paths)
RUN mkdir -p /data/recordings /data/meetings temp_audio

ENV PYTHONUNBUFFERED=1 \
    WHISPER_MODEL=tiny \
    PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
