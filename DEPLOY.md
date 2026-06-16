# Deploy PROSE-MEET (Vercel + Railway)

Live demo stack:

| Part | Host | URL pattern |
|------|------|-------------|
| **Frontend** (React + Vite) | [Vercel](https://vercel.com) | `https://your-app.vercel.app` |
| **Backend** (FastAPI + Whisper) | [Railway](https://railway.com) | `https://your-api.up.railway.app` |

Estimated cost: **Vercel free tier** + **Railway ~$5–15/month** (usage-based; allocate **2–4 GB RAM** for the API).

---

## Before you start

1. Push this repo to GitHub (already at `Gayaththri/PROSE-MEET`).
2. Create accounts on [railway.com](https://railway.com) and [vercel.com](https://vercel.com) (GitHub login works for both).
3. Plan two URLs — you will wire them together with CORS and `VITE_API_BASE_URL`.

**Demo tip:** Use `WHISPER_MODEL=tiny` on Railway (default in `backend/Dockerfile`). First deploy downloads Whisper + sentence-transformer weights; allow **5–15 minutes** for the first healthy build.

---

## Part 1 — Railway (backend)

### 1. New project from GitHub

1. Railway dashboard → **New Project** → **Deploy from GitHub repo** → select **PROSE-MEET**.
2. Open the new service → **Settings** → **Root Directory** → set to:
   ```
   backend
   ```
3. Railway should detect `backend/Dockerfile` and `backend/railway.toml`.

### 2. Resources

1. **Settings** → **Resources** (or service **Settings** → memory).
2. Set memory to **at least 2 GB** (4 GB recommended if you use `base` or `small` Whisper).

### 3. Environment variables

In **Variables**, add:

| Variable | Value | Notes |
|----------|-------|--------|
| `WHISPER_MODEL` | `tiny` | Fastest/cheapest for demos (`base` needs more RAM) |
| `BACKEND_CORS_ORIGINS` | `https://YOUR-VERCEL-APP.vercel.app` | Add later after Vercel deploy; include `http://localhost:5173` for local dev if needed |
| `PORT` | *(leave unset)* | Railway injects this automatically |

Optional:

| Variable | Value |
|----------|-------|
| `PROSE_DOMAIN_METHOD` | `keyword` | Skips loading sentence-transformers (faster cold start) |
| `WHISPER_CPU_THREADS` | `2` | Limit CPU on small Railway plans |

### 4. Public URL

1. **Settings** → **Networking** → **Generate Domain**.
2. Copy the URL, e.g. `https://prose-meet-production.up.railway.app`.
3. Verify: open `https://YOUR-RAILWAY-URL/health` → should return `{"status":"ok","service":"prose-meet-api"}`.
4. API docs: `https://YOUR-RAILWAY-URL/docs`

### 5. Redeploy after CORS update

Once you have the Vercel URL, set `BACKEND_CORS_ORIGINS` to that exact origin (no trailing slash), then **Redeploy** the Railway service.

Example:

```env
BACKEND_CORS_ORIGINS=https://prose-meet.vercel.app,http://localhost:5173
```

---

## Part 2 — Vercel (frontend)

### 1. Import project

1. Vercel dashboard → **Add New…** → **Project** → import **PROSE-MEET** from GitHub.

### 2. Project settings

| Setting | Value |
|---------|--------|
| **Root Directory** | `frontend/prose-meet-frontend` |
| **Framework Preset** | Vite |
| **Build Command** | `npm run build` (default) |
| **Output Directory** | `dist` (default) |

### 3. Environment variable (required)

Add for **Production** (and Preview if you want preview deploys to work):

| Name | Value |
|------|--------|
| `VITE_API_BASE_URL` | `https://YOUR-RAILWAY-URL` (no trailing slash) |

> Vite embeds this at **build time**. If you change the Railway URL, **redeploy** Vercel.

### 4. Deploy

Click **Deploy**. When finished, open the Vercel URL and upload a short audio clip to test.

### 5. Finish CORS loop

Copy your Vercel URL → paste into Railway `BACKEND_CORS_ORIGINS` → redeploy Railway.

---

## Part 3 — Smoke test

1. `GET https://YOUR-RAILWAY-URL/health` → `ok`
2. Open Vercel app → upload **30–60 s** of speech
3. Watch progress → transcript, importance heatmap, domain, highlights
4. If the browser shows a CORS error: double-check `BACKEND_CORS_ORIGINS` matches the Vercel origin exactly

---

## Local production-like test

```powershell
# Terminal 1 — backend
cd backend
$env:WHISPER_MODEL="tiny"
python -m uvicorn main:app --reload

# Terminal 2 — frontend pointing at local API
cd frontend/prose-meet-frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| **Build fails on Railway (OOM)** | Increase memory; keep `WHISPER_MODEL=tiny` |
| **First transcription very slow** | Normal — model still downloading/loading; wait or hit `/health` then retry |
| **CORS error in browser** | `BACKEND_CORS_ORIGINS` must include exact Vercel URL (`https://…`) |
| **UI calls wrong API** | Rebuild Vercel after changing `VITE_API_BASE_URL` |
| **502 / service crash** | Check Railway logs; often RAM or missing FFmpeg (Dockerfile installs it) |
| **Meetings disappear after restart** | Expected on Railway without a volume — job state is in-memory + `data/` is ephemeral unless you add a Railway volume |

---

## Files added for deploy

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Python 3.11 + FFmpeg + CPU PyTorch + FastAPI |
| `backend/requirements-docker.txt` | Dependencies (torch installed separately) |
| `backend/railway.toml` | Health check on `/health` |
| `backend/.dockerignore` | Smaller Docker context |
| `frontend/prose-meet-frontend/vercel.json` | SPA fallback routing |
| `frontend/prose-meet-frontend/.env.example` | `VITE_API_BASE_URL` template |

---

## Interview demo checklist

- [ ] Warm Railway 5 min before the interview (`/health` + one short upload)
- [ ] Keep a **30–60 s** sample audio file ready
- [ ] Bookmark Vercel app URL and Railway `/docs`
- [ ] Mention: Gap 1 importance + Gap 2 domain, reproducible eval in `results/`
