# Links to share

Use these with recruiters and in interviews.

| Link | What they get | Works without your laptop? |
|------|----------------|----------------------------|
| **GitHub (code)** | [github.com/Gayaththri/PROSE-MEET](https://github.com/Gayaththri/PROSE-MEET) | Yes — always |
| **Live demo (HF Space)** | `https://huggingface.co/spaces/Gayaththri/PROSE-MEET` | Yes — after you deploy once (free) |
| **Local interview demo** | Screen-share `http://localhost:5173` | No — see [INTERVIEW_DEMO.md](INTERVIEW_DEMO.md) |

**Best single link for a working demo:** Hugging Face Space (setup below).

---

## 1. GitHub (ready now)

Share immediately:

**https://github.com/Gayaththri/PROSE-MEET**

Good for: code review, README, metrics in `results/`, clone instructions.

---

## 2. Live demo on Hugging Face Spaces (free, one URL)

One link serves **both** the React UI and the FastAPI backend.

### One-time setup (~15 min)

1. Create account: [huggingface.co/join](https://huggingface.co/join)
2. **New Space** → Name: `PROSE-MEET` (or `prose-meet`) → **Docker** → Create
3. Space **Settings** → **Repository**:
   - Connect GitHub repo **Gayaththri/PROSE-MEET**
   - Branch: `main`
   - **Dockerfile path:** `deploy/huggingface/Dockerfile`
4. **Factory** → trigger **Rebuild** (or push to `main` auto-builds)
5. Wait for build (**10–20 min** first time — downloads PyTorch, Whisper, etc.)
6. When status is **Running**, open your Space URL

### Your shareable link

```
https://huggingface.co/spaces/Gayaththri/PROSE-MEET
```

(Replace `Gayaththri` if your HF username differs; Space name must match what you created.)

### Tips for sharing

- Add to CV / LinkedIn: *“Live demo: https://huggingface.co/spaces/Gayaththri/PROSE-MEET”*
- First visitor after idle wait: Space may **sleep** — wake takes **1–3 minutes**
- Recommend **30–60 second** audio clips for a snappy demo
- Pin the Space on your Hugging Face profile for visibility

### If build fails

| Issue | Fix |
|-------|-----|
| Build timeout | Rebuild; HF free CPU builds can be slow |
| OOM on run | Space uses CPU — keep `WHISPER_MODEL=tiny` (default in Dockerfile) |
| 404 on upload | Wait until Space shows **Running**, not **Building** |

---

## 3. Optional: Vercel frontend only

If you only need a **pretty URL** for the UI (uploads won’t work without a public API):

1. [vercel.com](https://vercel.com) → Import **PROSE-MEET**
2. Root Directory: `frontend/prose-meet-frontend`
3. Deploy → share `https://your-project.vercel.app`
4. On CV, pair with GitHub or HF: *“UI preview on Vercel; full demo on Hugging Face”*

To wire Vercel to a hosted API, set `VITE_API_BASE_URL` to your HF Space URL **without** `SERVE_FRONTEND` — the all-in-one HF deploy above is simpler.

---

## What to paste in an email / CV

**Short:**

> **PROSE-MEET** — prosody-aware meeting summarisation (FYP)  
> Live demo: https://huggingface.co/spaces/Gayaththri/PROSE-MEET  
> Code: https://github.com/Gayaththri/PROSE-MEET

**One line:**

> Demo: https://huggingface.co/spaces/Gayaththri/PROSE-MEET · GitHub: https://github.com/Gayaththri/PROSE-MEET

---

## Interview day

- **Remote with link:** Send the **Hugging Face** URL; warm it up 5 min before (open link, one test upload)
- **Live screen-share:** Use [INTERVIEW_DEMO.md](INTERVIEW_DEMO.md) — more reliable if HF is slow
