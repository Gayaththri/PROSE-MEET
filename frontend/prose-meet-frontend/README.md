# PROSE-MEET Frontend

React + Vite UI for the PROSE-MEET meeting pipeline: upload audio, run Gap 1 processing, and view transcripts, summaries, highlights, and importance.

## Prerequisites

- **Node.js** (current LTS recommended) — use the same `node` / `npm` pair (e.g. via [nvm](https://github.com/nvm-sh/nvm) or the official installer).

## Quick start

From this directory (`frontend/prose-meet-frontend/`):

```bash
npm ci
npm run dev
```

Use **`npm ci`** for a clean, lockfile-pinned install (typical for CI and fresh clones). Use **`npm install`** if you are changing dependencies and updating the lockfile.

Open the URL shown (e.g. http://localhost:5173). The app talks to the backend API; start the backend first (see root [README](../../README.md)).

### Verify lint and production build

```bash
npm run lint
npm run build
```

## Configuring the API base URL

By default the app uses **http://127.0.0.1:8000** as the backend API base URL. To override (e.g. for a different host or port):

- **Development:** Create `.env.local` in this directory (see `.env.example`).
- **Production (Vercel):** Set `VITE_API_BASE_URL` in Vercel → Project → Environment Variables, then redeploy. See [DEPLOY.md](../../DEPLOY.md).

## Scripts

- `npm run dev` — Start dev server with HMR.
- `npm run build` — Production build (output in `dist/`).
- `npm run preview` — Preview the production build locally.
- `npm run lint` — Run ESLint.

## Stack

- React 19
- Vite 7
- Tailwind CSS
- Axios for API calls
- Recharts (acoustic / prosody charts)
