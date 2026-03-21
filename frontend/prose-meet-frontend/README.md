# PROSE-MEET Frontend

React + Vite UI for the PROSE-MEET meeting pipeline: upload or record audio, run Gap 1 processing, and view transcripts, summaries, highlights, and importance.

## Quick start

```bash
npm install
npm run dev
```

Open the URL shown (e.g. http://localhost:5173). The app talks to the backend API; start the backend first (see root [README](../../README.md)).

## Configuring the API base URL

By default the app uses **http://127.0.0.1:8000** as the backend API base URL. To override (e.g. for a different host or port):

- **Development:** Create `.env.local` in this directory:
  ```env
  VITE_API_BASE_URL=http://127.0.0.1:8000
  ```
  Change the value to your backend URL. Vite only exposes variables prefixed with `VITE_`.

- **Production build:** Set `VITE_API_BASE_URL` in the environment when running `npm run build`, or in your CI/deploy config, e.g.:
  ```bash
  VITE_API_BASE_URL=https://api.example.com npm run build
  ```

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
