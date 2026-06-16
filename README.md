# PROSE-MEET

**Prosody-aware, domain-adaptable meeting summarisation** — upload or record meeting audio, transcribe with faster-whisper, score utterance importance (semantics + prosody), detect meeting domain (corporate / academic / medical), and surface highlights and summaries in a React UI.

### Research contributions

| Gap | Problem | Approach |
|-----|---------|----------|
| **Gap 1** | Which utterances matter? | Rule-based fusion of TF-IDF semantics + prosody (pitch, energy, pauses), with an optional **supervised** logistic-regression classifier trained on labelled utterances. |
| **Gap 2** | Meetings differ by domain | **Self-supervised zero-shot** domain detection (frozen Sentence-BERT + prototype matching), with domain-adaptive ranking boosts. Lexical baseline available via `PROSE_DOMAIN_METHOD=keyword`. |

### Key results (committed under `results/20260428_114739/`)

Evaluated on 6,513 labelled utterances across 15 meetings (AMI-derived seed data):

| Metric | Result | Notes |
|--------|--------|-------|
| **Gap 1 — fusion (rule-based)** | F1 **0.60**, AUC **0.75** | Best interpretable baseline (`ablation.json` → `fusion_rule_based`). |
| **Gap 1 — semantics only** | F1 **0.61**, AUC **0.76** | Strongest single signal in ablation. |
| **Gap 1 — supervised model** | AUC **0.81**, val F1 **0.60** | See `backend/models/importance_classifier_meta.json` for validation metrics. |
| **Gap 2 — domain accuracy** | **73%** overall (15 meetings) | Per-domain breakdown in `gap_eval.json`. |

Re-run evaluation: `python backend/run_all_experiments.py --repo-root . --output-root results`

### Demo flow (for interviews)

1. **Quick start (Windows):** `.\scripts\start-interview-demo.ps1` from repo root — or start backend + frontend manually (see **[INTERVIEW_DEMO.md](INTERVIEW_DEMO.md)**).
2. Open **http://localhost:5173** → upload a short meeting clip.
3. Show transcript, importance heatmap, domain label, and highlights.
4. Open **http://127.0.0.1:8000/docs** to show the REST API.

## Prerequisites (install before running)

| Tool | Why | Notes |
|------|-----|--------|
| **Python** | Backend API and pipeline | **3.10+** recommended. Use `python --version`. On Windows, prefer **Python from [python.org](https://www.python.org/downloads/)** or the Microsoft Store so `python` and `pip` match. |
| **Node.js** | Frontend build and dev server | **Current LTS** (e.g. 20.x or 22.x). Use `node --version` and `npm --version`. |
| **FFmpeg** | Converts uploads to 16 kHz mono WAV | Must be on your **`PATH`**. Verify: `ffmpeg -version` (PowerShell/CMD/macOS/Linux). [Download FFmpeg](https://ffmpeg.org/download.html) if the command is not found. |
| **Git** | Clone this repository | Optional if you already have the files. |

**Optional:**

- **[Hugging Face](https://huggingface.co/models)** — only if you override the default Gap 2 sentence-transformer via `PROSE_SSL_MODEL` in `.env`.

**Disk and network:** First run may download Whisper and (if used) sentence-transformer weights — ensure several GB free and a stable connection.

---

## Setup: run the project locally

Do these steps **in order** (backend first, then frontend in a second terminal).

### 1. Backend (FastAPI)

From the **repository root**:

```bash
cd backend
```

(Optional but recommended) create and use a virtual environment so Python packages stay isolated:

```bash
python -m venv .venv
```

- **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
- **Windows (Command Prompt):** `.venv\Scripts\activate.bat`
- **macOS / Linux:** `source .venv/bin/activate`

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

**Environment file (recommended):** copy the example file and edit if needed.

From repo root (PowerShell):

```powershell
Copy-Item backend\.env.example backend\.env
```

Or from inside `backend/`:

```powershell
Copy-Item .env.example .env
```

See [backend/.env.example](backend/.env.example) for `WHISPER_MODEL`, `BACKEND_CORS_ORIGINS`, and Gap 2 options. Defaults work for local dev; the first transcription may download a Whisper model.

**Start the API** — run this from the **`backend/`** directory (so `main:app` resolves correctly):

```bash
uvicorn main:app --reload
```

If `uvicorn` is not found on your `PATH` (common on Windows), use the same interpreter you used for `pip install`:

```bash
python -m uvicorn main:app --reload
```

- API base URL: **http://127.0.0.1:8000**
- Interactive docs: **http://127.0.0.1:8000/docs**

**Backend validation** (optional): run the evaluation scripts under `backend/evaluation/` — see [Reproducibility](#reproducibility) and [backend/README.md](backend/README.md).

### 2. Frontend (Vite + React)

Open a **new terminal**. From the **repository root**:

```bash
cd frontend/prose-meet-frontend
npm ci
```

If you do not have `package-lock.json` or `npm ci` fails, use:

```bash
npm install
```

Start the dev server:

```bash
npm run dev
```

Open the URL printed in the terminal (usually **http://localhost:5173**). The UI calls the backend at **http://127.0.0.1:8000** by default.

To point the UI at another API URL, set `VITE_API_BASE_URL` (see [frontend/prose-meet-frontend/README.md](frontend/prose-meet-frontend/README.md)).

**Lint / production build** (optional):

```bash
npm run lint
npm run build
```

---

## Quick reference (experienced users)

**Backend:** `cd backend` → `python -m pip install -r requirements.txt` → copy `.env.example` to `.env` → `uvicorn main:app --reload` (or `python -m uvicorn main:app --reload`)

**Frontend:** `cd frontend/prose-meet-frontend` → `npm ci` (or `npm install`) → `npm run dev`

## Documentation

- **[backend/README.md](backend/README.md)** — API overview, env vars (`.env.example`), supervised importance model training, evaluation (Gap 1/Gap 2), benchmark/ablation scripts, seed data templates (`backend/data/templates/`), deployment/production, and fine-tuned Whisper usage.
- **[frontend/prose-meet-frontend/README.md](frontend/prose-meet-frontend/README.md)** — Frontend setup and `VITE_API_BASE_URL`.
- **[INTERVIEW_DEMO.md](INTERVIEW_DEMO.md)** — Free local interview demo (screen-share), warm-up checklist, and talking points.
- **[DEPLOY.md](DEPLOY.md)** — Hosted deploy (Vercel + Railway).

## Deployment & interview demo

**Free interview demo (recommended):** Run backend + frontend **locally** and screen-share — no Railway cost. Step-by-step: **[INTERVIEW_DEMO.md](INTERVIEW_DEMO.md)** · quick start: `.\scripts\start-interview-demo.ps1`

**Full hosted demo (paid):** [Vercel](https://vercel.com) + [Railway](https://railway.com) — see **[DEPLOY.md](DEPLOY.md)**.

For self-hosted production:

- **Backend:** Configure `WHISPER_MODEL` (path or preset) and set `BACKEND_CORS_ORIGINS` to your frontend origin(s). See the **Deployment / production** section in [backend/README.md](backend/README.md) and `backend/.env.example`. Docker: `backend/Dockerfile`.
- **Frontend:** Set `VITE_API_BASE_URL` to your backend API URL when building (`npm run build`). See [frontend/prose-meet-frontend/README.md](frontend/prose-meet-frontend/README.md) and `frontend/prose-meet-frontend/.env.example`.
- **Paths:** Recordings and meeting JSON live under `data/`; use a persistent volume or object store if needed.

## Reproducibility

To regenerate Chapter 8 results and evaluation artifacts from a fresh clone:

1. (Optional) Copy and fill `backend/data/importance_labels.csv` from `backend/data/templates/`, then run `python backend/train_importance_model.py --data backend/data/importance_labels.csv --label-col label` so the “Supervised” row is populated.
2. From repo root: `python backend/run_all_experiments.py --repo-root . --output-root results`
3. Outputs: timestamped dir under `results/` (gap_eval.json, benchmark.json, ablation.json, etc.). Seed templates in `backend/data/templates/` are used for eval data if `backend/data/eval_dataset.csv` is missing.

## Project layout

- `backend/` — FastAPI app, faster-whisper ASR, importance/domain pipeline, evaluation scripts.
- `frontend/prose-meet-frontend/` — React + Vite UI for upload/record and viewing transcripts, summaries, and highlights.
- `data/` (repo root, gitignored) — Runtime data: `meetings/` (saved results JSON), `recordings/` (uploaded audio). Folders are created as you use the app; clearing them does not break the UI.
- `results/` — Timestamped evaluation outputs (`gap_eval.json`, `benchmark.json`, `ablation.json`) from `run_all_experiments.py`.
- `backend/data/templates/` — Seed CSV/manifest templates; see `backend/data/templates/README.md` for running eval and experiments on a fresh clone.
