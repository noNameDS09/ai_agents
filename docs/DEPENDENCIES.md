# Dependency choices

## Runtime dependencies

| Package | Purpose | Why chosen |
|---------|---------|------------|
| `fastapi` | Web framework | Production-grade, async-native, excellent Pydantic integration |
| `uvicorn[standard]` | ASGI server | FastAPI's standard server; `standard` includes watchfiles loop |
| `pydantic` / `pydantic-settings` | Validation, settings management | Settings are typed, env-driven, validated at startup (fail-fast) |
| `langgraph` | Agent orchestration | State-graph agent loop with built-in tool node and checkpointer support |
| `langchain-core` | Tool primitives (`@tool`) | Standard tool definition used by LangGraph |
| `langchain-openai` | OpenAI-compatible chat model | Powers `ChatOpenAI` pointed at OpenRouter's base URL |
| `langgraph-checkpoint-postgres` | Postgres checkpointer | Durable per-thread conversation state (production-grade) |
| `sqlalchemy[asyncio]` + `asyncpg` | App database (audit/history) | Async ORM + native PostgreSQL driver; non-blocking I/O |
| `python-dotenv` | Local env loading | Loads `.dev.env` for development (not used in production) |

Free inference only: `langchain-openai` talks to
`https://openrouter.ai/api/v1`. `OPENROUTER_MODEL` defaults to
`nvidia/nemotron-3.5-lightning:free` (a verified OpenRouter free model). No paid-model defaults anywhere in
the codebase. Operators must verify the pinned model is on OpenRouter's free
list before deploying (`https://openrouter.ai/models`).

## Dev dependencies

| Package | Purpose |
|---------|---------|
| `pytest`, `pytest-asyncio` | Test runner + async test support |
| `httpx` | ASGI test client for endpoint tests |
| `respx` | Mock OpenRouter HTTP (no real inference in tests) |

## Dependency governance

- Add/remove packages in `pyproject.toml`, then `uv sync`.
- Pin major versions; allow patch/minor within the same major.
- New runtime dependencies require: justification, license check, and (if network-facing) a security review.
- Avoid adding new dependencies for features the standard library already covers (e.g., the rate limiter is hand-rolled to avoid an extra package).
