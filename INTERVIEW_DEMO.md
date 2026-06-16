# Interview demo (free) — local backend + local frontend

**Best when Railway is not an option.** Run everything on your laptop and **share your screen** in the interview. No hosting cost, no cold starts, full Whisper pipeline.

| What | Where |
|------|--------|
| **Backend** (FastAPI + Whisper) | Your machine → `http://127.0.0.1:8000` |
| **Frontend** (React UI) | Your machine → `http://localhost:5173` |
| **Optional portfolio link** | [Vercel](https://vercel.com) hosts the UI only — uploads **won’t** work without a backend (see [Optional: Vercel portfolio](#optional-vercel-portfolio-link-only) below) |

---

## One-time setup (do this before interview day)

From the **repository root**:

### 1. Tools

```powershell
python --version    # 3.10+
node --version      # LTS
npm --version
ffmpeg -version     # must work
```

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

In `backend/.env` (optional but recommended for speed):

```env
WHISPER_MODEL=tiny
```

First transcription may download Whisper weights (~75 MB for `tiny`). **Do one test run the day before** so models are cached.

### 3. Frontend

```powershell
cd frontend\prose-meet-frontend
npm ci
```

### 4. Sample audio

Prepare a **30–60 second** `.wav` or `.mp3` of clear speech (meeting-style). Avoid files over ~10 MB for a snappy demo.

---

## Start the demo (interview day)

### Quick start (Windows)

From repo root:

```powershell
.\scripts\start-interview-demo.ps1
```

This opens two terminals (backend + frontend). Wait until you see:

- Backend: `Uvicorn running on http://127.0.0.1:8000`
- Frontend: `Local: http://localhost:5173/`

Open **http://localhost:5173** in your browser.

### Manual start (two terminals)

**Terminal 1 — backend**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload
```

**Terminal 2 — frontend**

```powershell
cd frontend\prose-meet-frontend
npm run dev
```

### Warm-up (5 minutes before the call)

1. Open `http://127.0.0.1:8000/health` → `{"status":"ok",...}`
2. Open `http://127.0.0.1:8000/docs` → keep tab ready to show API
3. Upload your sample audio once → wait for full result (confirms Whisper + pipeline work)
4. Close extra tabs; leave the finished meeting visible or start fresh for the live demo

---

## 3-minute demo script (what to show & say)

1. **Intro (30 s)**  
   *“PROSE-MEET transcribes meeting audio, scores utterance importance using prosody and semantics—Gap 1—and adapts to meeting domain with zero-shot SSL—Gap 2.”*

2. **Upload (60–90 s)**  
   Upload sample audio → point at progress stages (ASR → prosody → importance → domain).

3. **Results (60 s)**  
   - **Transcript** with importance scores  
   - **Heatmap / timeline** → Gap 1 fusion  
   - **Domain label** (corporate / academic / medical) → Gap 2  
   - **Highlights / action board**

4. **API (30 s)**  
   Switch to `http://127.0.0.1:8000/docs` → *“FastAPI, async jobs, same pipeline as the UI.”*

5. **Engineering (30 s)**  
   Mention GitHub: reproducible eval in `results/`, `run_all_experiments.py`, supervised model in `backend/models/`.

---

## Talking points (if they ask technical questions)

| Topic | Answer |
|-------|--------|
| **Gap 1** | Rule-based fusion of TF-IDF + prosody; optional supervised logistic regression (AUC ~0.81 on validation). |
| **Gap 2** | Frozen Sentence-BERT + prototype zero-shot; no domain fine-tuning. |
| **ASR** | faster-whisper (CTranslate2), VAD-tuned for quiet speech. |
| **Why local demo?** | ML backend needs RAM + FFmpeg; hosted demo is optional (see `DEPLOY.md`). |
| **Metrics** | `results/20260428_114739/` — fusion F1 ~0.60, domain accuracy ~73% on eval set. |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ffmpeg` not found | Install FFmpeg and restart terminal; `ffmpeg -version` |
| Frontend can’t reach API | Backend must be on port 8000; check `http://127.0.0.1:8000/health` |
| Upload hangs | Don’t set `Content-Type` manually on upload (handled in code); restart backend |
| Very slow first run | Normal — Whisper downloading; run once before the interview |
| `uvicorn` not found | Use `python -m uvicorn main:app --reload` from `backend/` |
| CORS errors | Should **not** happen on localhost; if you changed ports, see `BACKEND_CORS_ORIGINS` in `.env` |

---

## Optional: Vercel portfolio (link only)

You can deploy the **frontend** to Vercel so recruiters see a URL on your CV. **Processing will not work** on that URL unless a public backend is running.

1. Vercel → Import **PROSE-MEET** → Root Directory: `frontend/prose-meet-frontend`
2. **Do not** set `VITE_API_BASE_URL` (or set it only when you have a public API)
3. On your CV / README, write:  
   *“Live processing: clone repo and run locally — see INTERVIEW_DEMO.md”*  
   Add a **screenshot or screen recording** of the working local demo to the README for visual impact.

---

## Checklist

**Day before**

- [ ] `ffmpeg -version` works  
- [ ] Backend + frontend start without errors  
- [ ] One full upload completes successfully  
- [ ] Sample audio file ready on Desktop  
- [ ] GitHub repo link ready: https://github.com/Gayaththri/PROSE-MEET  

**15 minutes before**

- [ ] Close Slack/notifications  
- [ ] Run `.\scripts\start-interview-demo.ps1`  
- [ ] Warm-up upload done  
- [ ] Browser zoom 100–125% (readable on screen share)  
- [ ] `localhost:5173` and `/docs` tabs ready  
