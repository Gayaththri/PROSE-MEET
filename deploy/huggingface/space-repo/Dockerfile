# Dockerfile for the Hugging Face Space repo root (Gayaththri/PROSE-MEET).
# Clones the GitHub monorepo at build time — only this file + README.md live in the Space repo.

FROM node:22-bookworm-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 https://github.com/Gayaththri/PROSE-MEET.git .
WORKDIR /src/frontend/prose-meet-frontend
RUN npm ci
ENV VITE_API_BASE_URL=
RUN npm run build

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY --from=builder /src/backend/requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY --from=builder /src/backend/ .
COPY --from=builder /src/frontend/prose-meet-frontend/dist ./static

RUN mkdir -p /data/recordings /data/meetings temp_audio

ENV PYTHONUNBUFFERED=1 \
    SERVE_FRONTEND=1 \
    WHISPER_MODEL=tiny \
    PORT=7860

EXPOSE 7860

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
