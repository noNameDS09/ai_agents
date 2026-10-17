# agent-api

Production-oriented, general-purpose tool-using agent backend.

**Interface:** FastAPI backend + React/Vite frontend served from the same origin (`/`)
**Inference:** OpenRouter free models only (OpenAI-compatible client)
**Agent loop:** LangGraph with tools + Postgres checkpointer
**Stack:** Python 3.12+, uv, FastAPI, LangGraph, Pydantic v2, SQLAlchemy async, asyncpg
**Tests:** pytest; OpenRouter mocked — no real inference in CI

See `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEPENDENCIES.md`, `docs/SECURITY.md`, `docs/FRONTEND.md`, `docs/RUNBOOK.md`, and `AGENTS.md`.

---

## What it does

`agent-api` is a self-hosted, tool-using AI agent. You send it a message; it decides
whether to answer directly or call one of its 26 built-in tools, then returns the
final answer. Conversation state is persisted in PostgreSQL so threads can be
resumed. A React/Vite UI is served from the same origin.

```
+------------+      HTTPS (OpenAI-compatible)      +------------------+
|  Client    | <----------------------------------> |   OpenRouter     |
| (browser   |      X-API-Key, JSON body           |  (free models)   |
|  or curl)  |                                      +------------------+
+------------+                                      ^
      | JSON over HTTP (same origin)                 | chat completions
      v                                              |
+------------+      asyncpg / psycopg      +---------------+
|  FastAPI   | <-------------------------> | PostgreSQL    |
|            |                             |               |
|  Routers   |  - app_messages (audit)     |  - checkpoints  |
|  Service   |  - audit_events             |  (LangGraph)    |
|  Graph     |                             +---------------+
|  Tools     |
|  Static    |  - frontend/dist/index.html (SPA)
|  Files     |  - frontend/dist/assets/* (JS/CSS)
+------------+
```

## Quick start

### 1. Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- PostgreSQL 14+ (local or remote)
- Node.js 18+ (for the frontend)

### 2. Clone and install

```bash
git clone git@github.com:noNameDS09/ai_agents.git
cd ai_agents
cp .env.example .dev.env   # edit secrets
uv sync
```

### 3. Provision PostgreSQL

```sql
CREATE DATABASE agent_dev;
CREATE DATABASE agent_test;
```

Tables are created automatically on startup (`init_db()`). LangGraph checkpointer
tables are created by `PostgresSaver.setup()`.

### 4. Configure `.dev.env`

```env
API_KEY=dev-secret-key-change-me          # client API key (X-API-Key header)
OPENROUTER_API_KEY=sk-or-your-real-key     # from https://openrouter.ai/keys
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free
DATABASE_URL=postgresql+asyncpg://postgres@/agent_dev?host=%2Frun%2Fpostgresql
TEST_DATABASE_URL=postgresql+asyncpg://postgres@/agent_test?host=%2Frun%2Fpostgresql
CORS_ORIGINS=["*"]
TRUSTED_HOSTS=["localhost","127.0.0.1"]
```

### 5. Run

```bash
uv run pytest                              # 57 tests pass
cd frontend && npm install && npm run build
cd .. && uv run uvicorn src.agent_api.main:app --reload   # http://localhost:8000
```

### 6. Open the UI

Navigate to `http://localhost:8000`. Enter your `API_KEY` value in the X-API-Key
field and start chatting.

---

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Liveness/readiness (DB + inference status) |
| `POST` | `/v1/chat` | `X-API-Key` | Send a message, get agent response |
| `GET` | `/v1/tools` | `X-API-Key` | List allowlisted tools with JSON schemas |
| `GET` | `/v1/threads/{thread_id}` | `X-API-Key` | Retrieve conversation history |
| `GET` | `/` | No | React frontend (SPA) |
| `GET` | `/assets/*` | No | Built frontend assets |

### POST /v1/chat

**Request:**
```json
{
  "thread_id": "optional-uuid (new conversation if omitted)",
  "message": "What is 23 * 17 + 5?",
  "model": "optional override (must be a free OpenRouter model)"
}
```

**Response:**
```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": "23 * 17 + 5 = 396\n\n_(tool called: calculator)_",
  "tool_calls": [{"name": "calculator", "arguments": {"expression": "23 * 17 + 5"}}],
  "steps": 2
}
```

- `message` max 4000 chars (`MAX_MESSAGE_LENGTH`)
- `thread_id` must be a valid UUID when provided
- `model` override must end with `:free`

### GET /v1/tools

Returns all 26 allowlisted tools with name, description, and JSON-schema parameters.

### GET /v1/threads/{thread_id}

Returns stored message history. `404` when the thread has no stored history.

### GET /health

```json
{"status": "ok", "database": "ok", "inference_configured": true}
```

Returns `503` when database or inference configuration is missing.

---

## Available tools (26)

### Core (3)

| Tool | Description |
|------|-------------|
| `calculator` | Safe arithmetic via AST parsing (no `eval`) — `+ - * / % // ** ()` |
| `current_time` | Current UTC time with strftime format string |
| `knowledge_base_lookup` | Static knowledge-base stub (capital of France, largest planet, etc.) |

### Data & JSON (4)

| Tool | Description |
|------|-------------|
| `json_format` | Validate and pretty-print a JSON string |
| `json_get` | Extract a value from JSON by dot-separated path (e.g. `user.name`, `items.0.id`) |
| `csv_parse` | Parse CSV text with a header row into JSON |
| `xml_to_json` | Convert XML to JSON |

### Text (4)

| Tool | Description |
|------|-------------|
| `text_transform` | Uppercase, lowercase, titlecase, reverse, word/char/sentence count, lines, slugify |
| `regex_extract` | Extract regex matches from text (with capture groups) |
| `word_frequency` | Top-N word frequency count |
| `text_similarity` | Levenshtein distance + similarity score between two strings |

### Encoding & Hashing (3)

| Tool | Description |
|------|-------------|
| `base64` | Encode or decode text as Base64 |
| `hash_text` | Hash text using SHA256, SHA1, or MD5 |
| `url_encode_decode` | URL-encode or decode text |

### Math & Numbers (5)

| Tool | Description |
|------|-------------|
| `unit_converter` | Convert length, weight, temperature units |
| `math_stats` | Mean, median, min, max, sum, count, stdev on a list of numbers |
| `number_base_convert` | Convert between bases 2, 8, 10, 16 |
| `random_number` | Generate random integers in a range |
| `roman_numeral` | Convert between Roman numerals and Arabic integers |

### Date & Time (2)

| Tool | Description |
|------|-------------|
| `date_diff` | Difference in days between two dates (YYYY-MM-DD) |
| `cron_describe` | Human-readable description of a 5-field cron expression |

### Security & Identity (4)

| Tool | Description |
|------|-------------|
| `generate_uuid` | Generate 1-10 UUID4 values |
| `password_generator` | Generate secure random passwords with optional symbols |
| `jwt_decode` | Decode JWT header + payload (no signature verification) |
| `ip_validate` | Validate and analyze IPv4/IPv6 addresses (private, loopback, multicast, etc.) |

### Color (1)

| Tool | Description |
|------|-------------|
| `color_convert` | Convert between hex, RGB, and HSL color formats |

All tools are deterministic, local (no outbound network), Pydantic-validated, and
registered in the LangGraph `ToolNode` allowlist (asserted at import time).

---

## Authentication & security

- **API key:** Every stateful endpoint requires `X-API-Key` matching the `API_KEY` setting. `GET /health` is unauthenticated.
- **Rate limiting:** In-memory token bucket per API key. Defaults: 60 requests / 60 seconds. Exceeded → `429` with `Retry-After`.
- **Input validation:** Pydantic v2 models; `message` capped at `MAX_MESSAGE_LENGTH` (4000); client roles restricted to `user` (no system prompt injection); `thread_id` must be a UUID.
- **Tool safety:** Tools defined once in `tools.py`, allowlisted in LangGraph `ToolNode`. All deterministic and local (no network calls).
- **Transport:** CORS origins restricted to `CORS_ORIGINS`; trusted hosts via `TrustedHostMiddleware`; request body size capped at `MAX_REQUEST_BODY_BYTES`.
- **Secrets:** `OPENROUTER_API_KEY` and `API_KEY` from environment only, never hardcoded. `.dev.env` is gitignored.

See `docs/SECURITY.md` for the full security control documentation.

---

## Architecture

```
src/agent_api/
  config.py          # Pydantic Settings (single source of truth)
  security.py        # API key auth, rate limiter, input validation
  database.py        # SQLAlchemy async + asyncpg, init_db()
  tools.py           # 26 allowlisted tools with Pydantic schemas
  graph.py           # LangGraph state graph (model ↔ ToolNode, Postgres checkpointer)
  service/agent.py   # Orchestration: DB audit + graph run
  api/v1/chat.py     # POST /v1/chat, GET /v1/threads/{id}
  api/v1/tools.py    # GET /v1/tools
  main.py            # FastAPI app factory + middleware + SPA fallback
```

**Agent loop (LangGraph):**
1. `POST /v1/chat` receives `thread_id` + `message`
2. Service persists user turn to `app_messages` (audit)
3. LangGraph graph runs with `thread_id` as checkpointer key:
   - **Model node:** LLM (ChatOpenAI → OpenRouter) decides to answer or call a tool
   - **Tool node:** executes the requested allowlisted tool
   - Loop repeats until the model emits a final answer
4. Checkpointer persists full graph state per `thread_id`
5. Service persists assistant turn, returns response with `tool_calls` and `steps`

**Data model:**
- `conversations` — thread metadata
- `app_messages` — queryable conversation history (role, content, tool_calls JSONB, created_at)
- `audit_events` — security-relevant events
- LangGraph checkpoints in `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` tables

See `docs/ARCHITECTURE.md` for the full architecture documentation.

---

## Development

### Run backend + frontend (two servers)

```bash
# Terminal 1 — Backend
uv run uvicorn src.agent_api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend (hot-reload, proxies to backend)
cd frontend && npm run dev
```

Open `http://localhost:5173` for the Vite dev server with hot-reload.

### Run backend only (serves built frontend)

```bash
cd frontend && npm run build
cd .. && uv run uvicorn src.agent_api.main:app --reload
# Open http://localhost:8000
```

### Run tests

```bash
uv run pytest                    # 57 tests
uv run pytest tests/test_tools.py # tool tests only
uv run pytest -v                 # verbose
```

### Makefile targets

```bash
make sync            # install dependencies
make test            # run tests
make run             # start backend
make frontend-dev    # start Vite dev server
make frontend-build  # build frontend to dist/
make dev             # sync + test
```

---

## Configuration

All settings via environment variables (`.dev.env` locally, env vars in production):

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | (required) | Client API key for `X-API-Key` header |
| `OPENROUTER_API_KEY` | `""` | OpenRouter API key (chat returns 503 when unset) |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-lightning:free` | Must be a free OpenRouter model |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base URL |
| `DATABASE_URL` | (required) | PostgreSQL asyncpg DSN |
| `TEST_DATABASE_URL` | (optional) | Test database DSN |
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins (JSON array) |
| `TRUSTED_HOSTS` | `["localhost","127.0.0.1"]` | Trusted hostnames (JSON array) |
| `RATE_LIMIT_REQUESTS` | `60` | Requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window in seconds |
| `MAX_REQUEST_BODY_BYTES` | `262144` | Max request body size |
| `MAX_MESSAGE_LENGTH` | `4000` | Max chat message length |

---

## Production hardening checklist

- [ ] Restrict `CORS_ORIGINS` to exact frontend origins
- [ ] Restrict `TRUSTED_HOSTS` to actual hostnames
- [ ] Rotate `API_KEY` and `OPENROUTER_API_KEY`; store in a secret manager
- [ ] Replace in-memory rate limiter with Redis-backed limiting for multi-node
- [ ] Terminate TLS at a reverse proxy; enforce HTTPS
- [ ] Add database migrations (e.g., Alembic) instead of `init_db()` create-all
- [ ] Add structured logging with request IDs and secret redaction
- [ ] Add JWT/OAuth2 end-user authentication for external users
- [ ] Build frontend (`npm run build`) before deploying
- [ ] Set `OPENROUTER_MODEL` to a verified free model

---

## Documentation

| Doc | Description |
|-----|-------------|
| `docs/ARCHITECTURE.md` | System architecture, layers, data model, deployment |
| `docs/API.md` | Full API reference with request/response schemas |
| `docs/DEPENDENCIES.md` | Dependency choices and governance |
| `docs/SECURITY.md` | Security controls and boundaries |
| `docs/FRONTEND.md` | React/Vite frontend development and deployment |
| `docs/RUNBOOK.md` | Local dev, Postgres provisioning, troubleshooting |
| `AGENTS.md` | Agent conventions and key entry points |

## License

MIT