# Frontend

A React + Vite client served by the same FastAPI process at `/` (SPA fallback) and
`/assets/` (built JS/CSS). It consumes the same `/v1` API as any other client,
inheriting auth, rate limiting, and input validation.

## Stack

- React 19 + TypeScript
- Vite (build tool, dev server)
- No UI framework — plain React/CSS, kept minimal and dependency-light

## Files

```
frontend/
  index.html          # Vite entry HTML
  vite.config.ts      # Vite config (builds to dist/)
  src/main.tsx        # React entry point
  src/App.tsx         # shell: health, chat, threads, tools
  src/api.ts          # same-origin API client (fetch)
  src/components/     # ApiKeyBar, MessageList, ToolsPanel, ThreadList, Composer
  dist/               # built output (gitignored, served by FastAPI)
```

## Development (two servers)

Run both the backend and the Vite dev server simultaneously for hot-reload:

**Terminal 1 — Backend:**
```bash
uv run uvicorn src.agent_api.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend (hot-reload):**
```bash
cd frontend && npm run dev
```

Vite dev server runs on `http://localhost:5173` and proxies `/health` and `/v1`
to the backend on `:8000`. Open the UI at `http://localhost:5173`.

Alternatively, use the Makefile targets:
```bash
make run            # backend
make frontend-dev   # frontend (in a second terminal)
```

In production, build once and serve everything from FastAPI:
```bash
cd frontend && npm run build
uv run uvicorn src.agent_api.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000 (no separate frontend server needed)
```

## Production serving

`src/agent_api/main.py` mounts `frontend/dist/assets` at `/assets` and returns
`frontend/dist/index.html` for any non-API path (SPA fallback). If `dist/` is
missing, the server returns `503` with a message to run `npm run build`.

## Security notes

- The frontend inherits the backend's auth, rate limiting, and input validation.
- The user's `X-API-Key` is typed into an input field and stored in
  `localStorage` only (browser-side). It is never logged, never sent to OpenRouter,
  and never leaves the browser except as the `X-API-Key` header to the same-origin
  backend.
- Because the API key lives in the browser, treat the frontend as suited for
  trusted users / internal tooling. For external end-users, add proper end-user
  authentication (JWT/OAuth2) before exposing it — see `docs/RUNBOOK.md`.
