# Agent-oriented repo instructions (`AGENTS.md`)

This file tells coding agents how to work in this repository. Humans: see `README.md` and `docs/`.

## Project purpose

A simple, production-oriented, general-purpose tool-using agent backend:
- **Interface:** FastAPI backend + React/Vite frontend served from the same origin (`/`)
- **Inference:** OpenRouter free models only (OpenAI-compatible client)
- **Agent loop:** LangGraph state graph with a tool node (ReAct-style)
- **State/audit:** PostgreSQL (LangGraph checkpointer + app audit tables)
- **Stack:** Python 3.12+, `uv`, FastAPI, LangGraph, Pydantic v2, SQLAlchemy 2 async, asyncpg; frontend: React + Vite + TypeScript
- **Quality:** automated tests (pytest), security controls (API keys, rate limiting, CORS, input validation, tool allowlist)

## Repository layout

```
AGENTS.md              # this file: agent/conventions
README.md              # human-facing overview
pyproject.toml         # uv-managed deps, build, pytest config
.env.example           # copy to .dev.env (gitignored) for local secrets
Makefile               # sync / test / run targets
docs/                  # ARCHITECTURE, API, DEPENDENCIES, SECURITY, FRONTEND, RUNBOOK
frontend/              # React + Vite UI built to dist/, served by FastAPI at / and /assets
src/agent_api/         # application package
tests/                 # pytest suite
```

## Conventions (must follow)

1. **Dependency changes:** edit `pyproject.toml`, then run `uv sync`. Commit `uv.lock` only if your workflow pins it (this repo treats `uv.lock` as gitignored; regenerate per environment).
2. **Environment:** never commit real secrets. Copy `.env.example` to `.dev.env` (gitignored). Tests inject their own env via `tests/conftest.py`.
3. **OpenRouter free models only:** `OPENROUTER_MODEL` must be a free variant (name typically ends in `:free`). Do not add paid-model defaults. If you change the default, update `docs/DEPENDENCIES.md` and `src/agent_api/config.py`. The default is `nvidia/nemotron-3.5-lightning:free`.
4. **Tool safety:** tools live in `src/agent_api/tools.py` and are allowlisted in the LangGraph `ToolNode`. Clients can never invoke arbitrary functions. Add a tool only with: Pydantic `args_schema`, deterministic implementation (no outbound network unless reviewed), and a test in `tests/test_tools.py`.
5. **Security:** all mutations and chat require a valid `X-API-Key`. Do not log headers, API keys, or request bodies. Add new endpoints under `src/agent_api/api/v1/` and register them in `src/agent_api/main.py`.
6. **Database:** app tables use SQLAlchemy async + asyncpg; LangGraph checkpoints use `langgraph-checkpoint-postgres` (`PostgresSaver`) wrapped in `asyncio.to_thread` because its saver is synchronous. Migrations are not automated yet — create tables via `database.init_db()` (dev/tests) and document schema changes in `docs/RUNBOOK.md`.
7. **Tests:** every new feature needs test coverage in `tests/`. Run with `uv run pytest` (or `make test`). Tests use the `agent_test` database and mock OpenRouter (`respx`) — no real inference in CI.
8. **Python style:** type-annotated public functions, docstrings on modules/classes/public methods, Pydantic v2 models for all request/response bodies.

## Common commands

```bash
make dev          # uv sync + run tests
uv sync           # install/refresh dependencies
uv run pytest     # run tests
uv run uvicorn src.agent_api.main:app --reload  # dev server
```

## Key entry points

- `src/agent_api/main.py` — FastAPI app factory + middleware + routers + static frontend SPA fallback.
- `src/agent_api/config.py` — Pydantic Settings (single source of truth for config).
- `src/agent_api/security.py` — API key auth, rate limiter, input validation.
- `src/agent_api/database.py` — SQLAlchemy async engine/session + `init_db`.
- `src/agent_api/tools.py` — allowlisted agent tools.
- `src/agent_api/graph.py` — LangGraph state graph (model + tools + checkpointer).
- `src/agent_api/service/agent.py` — orchestration: app DB audit + graph run.
- `src/agent_api/api/v1/chat.py` — `POST /v1/chat`, `GET /v1/threads/{id}`.
- `src/agent_api/api/v1/tools.py` — `GET /v1/tools`.
- `tests/conftest.py` — fixtures: env, test DB, ASGI test client.

## When in doubt

Read `docs/ARCHITECTURE.md` first, then `docs/SECURITY.md` before touching auth/rate-limiting/tool code.
