# agent-api

Production-oriented, general-purpose tool-using agent backend.

- **Interface:** FastAPI backend + React/Vite frontend served from the same origin (`/`)
- **Inference:** OpenRouter free models only
- **Agent loop:** LangGraph with tools + Postgres checkpointer
- **Stack:** Python 3.12+, uv, FastAPI, LangGraph, Pydantic v2, SQLAlchemy async, asyncpg
- **Tests:** pytest; OpenRouter mocked — no real inference in CI

See `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEPENDENCIES.md`, `docs/SECURITY.md`, `docs/FRONTEND.md`, `docs/RUNBOOK.md`, and `AGENTS.md`.
