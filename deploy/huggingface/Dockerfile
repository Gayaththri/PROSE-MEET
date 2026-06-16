# Hugging Face Space — full stack (React UI + FastAPI + Whisper)
# Build context: repository root (set in Space settings → Dockerfile path: deploy/huggingface/Dockerfile)

FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/prose-meet-frontend/package.json frontend/prose-meet-frontend/package-lock.json ./
RUN npm ci
COPY frontend/prose-meet-frontend/ ./
# Same origin as API when served from this container
ENV VITE_API_BASE_URL=
RUN npm run build

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY backend/ .
COPY --from=frontend /web/dist ./static

RUN mkdir -p /data/recordings /data/meetings temp_audio

ENV PYTHONUNBUFFERED=1 \
    SERVE_FRONTEND=1 \
    WHISPER_MODEL=tiny \
    PORT=7860

EXPOSE 7860

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
