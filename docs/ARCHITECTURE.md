# Architecture

## Overview

Stateless FastAPI backend exposing a general-purpose, tool-using agent.
Inference is provided exclusively by OpenRouter free models through an
OpenAI-compatible client. Conversation checkpoints and an application audit
log are stored in PostgreSQL.

```
+------------+      HTTPS (OpenAI-compatible)      +------------------+
|  Client    | <----------------------------------> |   OpenRouter     |
| (any HTTP) |      X-API-Key, JSON body           |  (free models)   |
+------------+                                      +------------------+
      |                                                    ^
      | JSON over HTTP                                     | chat completions
      v                                                    |
+------------+      asyncpg / psycopg      +---------------+
|  FastAPI   | <-------------------------> | PostgreSQL    |
|            |                             |               |
|  Routers   |  - app_messages (audit)     |  - checkpoints  |
|  Service   |  - audit_events             |  - checkpoints  |
|  Graph     |                             +---------------+
|  Tools     |  calculator, current_time, KB lookup, |
|           |  json_format, text_transform, unit_converter, |
|           |  base64, hash_text, generate_uuid, regex_extract, |
|           |  math_stats, date_diff, random_number |
|  Static    |  - frontend/dist/index.html (SPA)     |
|  Files     |  - frontend/dist/assets/* (JS/CSS)    |
+------------+
```

## Frontend

A React + Vite UI (`frontend/`) served by FastAPI at `/` (SPA fallback) and
`/assets/` (built JS/CSS). It calls the same `/v1` endpoints as any other client,
inheriting auth, rate limiting, and input validation. Built with `npm run build`
into `frontend/dist/` before deployment; can be replaced by a dedicated SPA later
without touching the backend.

## Layers

| Layer | Responsibility | Key files |
|-------|----------------|-----------|
| **API** | HTTP request/response, auth, rate limiting, validation | `src/agent_api/main.py`, `api/v1/` |
| **Security** | API key auth, token-bucket rate limiting, CORS/TrustedHost, input sanitization | `security.py` |
| **Service** | Thread/audit bookkeeping, orchestrates graph runs | `service/agent.py` |
| **Graph** | LangGraph state machine: LLM ↔ ToolNode loop | `graph.py` |
| **Tools** | Allowlisted deterministic tools (calculator, time, KB stub) | `tools.py` |
| **Data** | SQLAlchemy async engine/session, `init_db`, Postgres checkpointer | `database.py` |
| **Config** | Single Pydantic Settings source of truth | `config.py` |

## Agent loop (LangGraph)

1. `chat` endpoint receives `thread_id` + user `message`.
2. Service inserts an `app_messages` audit row (user turn).
3. LangGraph graph runs with `config = {"configurable": {"thread_id": ...}}`:
   - **Model node:** LLM (ChatOpenAI → OpenRouter) bound to the tool allowlist; decides to answer or call a tool.
   - **Tool node:** executes the requested allowlisted tool, returns result as a tool message.
   - Loop repeats until the model emits a final answer (`tools_condition`).
4. Checkpointer (`PostgresSaver`) persists full graph state per `thread_id` so conversations can be resumed.
5. Service inserts the assistant turn into `app_messages`, returns the final response.

The checkpointer is synchronous (psycopg-based), so graph execution is wrapped in
`asyncio.to_thread(asyncio.run, ...)` to avoid blocking the FastAPI event loop.

## Data model

- `app_messages(id, thread_id, role, content, tool_calls, created_at)` — queryable conversation history used by `/v1/threads/{thread_id}`.
- `audit_events(id, event, actor, details, created_at)` — security-relevant events (auth failures, rate-limit trips).
- LangGraph checkpoints live in the checkpointer's own tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) managed by `langgraph-checkpoint-postgres`.

## Deployment assumptions

- Single-node FastAPI behind a reverse proxy (TLS termination).
- Rate limiter is in-memory (per-process); scale horizontally requires replacing it with Redis-backed limiting.
- No frontend: callers are scripts, other services, or a future SPA (CORS must be explicitly configured for any origin).
