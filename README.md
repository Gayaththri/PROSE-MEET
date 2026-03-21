# PROSE-MEET

Meeting audio pipeline: transcription (faster-whisper), prosody, utterance importance, and summaries — with an optional web UI to upload/record audio and view results.

## Prerequisites

- **Python 3.x** — backend (ASR, importance, domain detection).
- **Node.js** — frontend (Vite + React).
- **Optional:** [PostgreSQL](https://www.postgresql.org/download/) — persist meeting results (otherwise stored as JSON under `data/meetings/`).
- **Optional:** [Hugging Face token](https://hf.co/settings/tokens) — for speaker diarization (pyannote); without it, the app uses pause-based speaker estimation.

## Quick start

**1. Backend**

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

API: **http://127.0.0.1:8000**

**2. Frontend** (separate terminal)

```bash
cd frontend/prose-meet-frontend
npm install
npm run dev
```

Open the URL shown (e.g. **http://localhost:5173**). The UI talks to the backend at `http://127.0.0.1:8000`.

## Documentation

- **[backend/README.md](backend/README.md)** — API overview, env vars (`.env.example`), supervised importance model training, evaluation (Gap 1/Gap 2), benchmark/ablation scripts, seed data templates (`backend/data/templates/`), PostgreSQL setup, speaker diarization, deployment/production, and fine-tuned Whisper usage.
- **[frontend/prose-meet-frontend/README.md](frontend/prose-meet-frontend/README.md)** — Frontend setup and `VITE_API_BASE_URL` for configuring the backend API URL.

## Deployment

For production or a hosted deployment:

- **Backend:** Set `DATABASE_URL` to a PostgreSQL instance, configure `WHISPER_MODEL` (path or preset), and set `BACKEND_CORS_ORIGINS` to your frontend origin(s). See [backend/README.md](backend/README.md) § Deployment / production and `backend/.env.example`.
- **Frontend:** Set `VITE_API_BASE_URL` to your backend API URL when building (`npm run build`). See [frontend/prose-meet-frontend/README.md](frontend/prose-meet-frontend/README.md).
- **Paths:** Recordings and meeting JSON (if not using PostgreSQL) live under `data/`; use a persistent volume or object store if needed.

## Reproducibility

To regenerate Chapter 8 results and evaluation artifacts from a fresh clone:

1. (Optional) Copy and fill `backend/data/importance_labels.csv` from `backend/data/templates/`, then run `python backend/train_importance_model.py --data backend/data/importance_labels.csv --label-col label` so the “Supervised” row is populated.
2. From repo root: `python backend/run_all_experiments.py --repo-root . --output-root results`
3. Outputs: timestamped dir under `results/` (gap_eval.json, benchmark.json, ablation.json, etc.), updated `docs/chapter8_results.md`, and `docs/figures/` plots. Seed templates in `backend/data/templates/` are used for eval data if `backend/data/eval_dataset.csv` is missing.

## Project layout

- `backend/` — FastAPI app, faster-whisper ASR, importance/domain pipeline, evaluation scripts.
- `frontend/prose-meet-frontend/` — React + Vite UI for upload/record and viewing transcripts, summaries, and highlights.
- `backend/data/templates/` — Seed CSV/manifest templates; see `backend/data/templates/README.md` for running eval and experiments on a fresh clone.
