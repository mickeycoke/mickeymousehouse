# Mickeymouse House — Frontend

React + Vite + Tailwind single-page app. Talks to the FastAPI backend at
`http://localhost:8000` (run via `docker compose up -d db backend` from the
repo root).

The `dev`/`build`/`test:e2e` scripts intentionally use the vendored Node
runtime in `../.local-tools/` so every agent and machine runs the same
stable version.

## Run locally

```bash
npm install
npm run dev          # http://localhost:5173  (login: admin@example.com / admin123)
```

## Tests

```bash
npm run test:e2e     # Playwright E2E suite (starts db/backend + vite itself)
```

## Where things live

| Path | What it is |
|---|---|
| `src/App.jsx` | All routes; every page is wired here |
| `src/pages/` | Route-level pages, one folder per area (admin, setup, ownership, billing, franchise) |
| `src/components/` | Reusable UI, grouped by area; `ui/` is the shared base kit |
| `src/hooks/` | Data-loading and stateful behavior hooks |
| `src/api/` | All axios calls — components never call axios directly |
| `src/context/AuthContext.jsx` | Login state + token storage |
| `tests/e2e/` | Playwright specs, one file per feature area |

## Rules for agents

- Keep API calls in `src/api/` modules, never inline in components.
- Keep pages thin: routing, data loading, composition only.
- Every interactive element gets a `data-testid`.
- Add or update the matching spec in `tests/e2e/` with any UI change.
