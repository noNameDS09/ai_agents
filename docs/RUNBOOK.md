# Runbook

## Local development

```bash
# 1. Copy environment template (edit values, never commit real secrets)
cp .env.example .dev.env

# 2. Install dependencies
uv sync

# 3. Ensure PostgreSQL is reachable at DATABASE_URL / TEST_DATABASE_URL
#    (this repo expects agent_dev and agent_test databases to exist)

# 4. Run tests
uv run pytest

# 5. Start the server
uv run uvicorn src.agent_api.main:app --reload --host 0.0.0.0 --port 8000
```

## Provisioning PostgreSQL

```sql
CREATE DATABASE agent_dev;
CREATE DATABASE agent_test;
-- Optionally create a dedicated app role with a password and update DSNs.
```

The app creates its own tables via `database.init_db()` on startup (dev/tests).
LangGraph checkpointer tables are created automatically by `PostgresSaver.setup()`.

## Running with OpenRouter

1. Get a free API key from https://openrouter.ai/keys.
2. Set `OPENROUTER_API_KEY` and confirm `OPENROUTER_MODEL` is a free variant
   (typically suffixed `:free`).
3. Start the server. `GET /health` reports `inference_configured`.

Without `OPENROUTER_API_KEY`, the server starts but `/v1/chat` returns `503`.

## Production hardening checklist

- [ ] Restrict `CORS_ORIGINS` to exact frontend origins.
- [ ] Restrict `TRUSTED_HOSTS` to actual hostnames.
- [ ] Rotate `API_KEY` and `OPENROUTER_API_KEY`; store in a secret manager.
- [ ] Replace in-memory rate limiter with Redis-backed limiting for multi-node.
- [ ] Terminate TLS at a reverse proxy; enforce `HTTPS` and secure cookies.
- [ ] Add database migrations (e.g., Alembic) instead of `init_db()` create-all.
- [ ] Add structured logging with request IDs and secret redaction.
- [ ] Add JWT/OAuth2 end-user authentication if serving external users.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `503 inference not configured` | `OPENROUTER_API_KEY` missing | Set it in env; restart |
| `401` on all requests | Wrong/missing `X-API-Key` | Match `API_KEY` setting |
| `429` | Rate limit exceeded | Wait, or raise `RATE_LIMIT_REQUESTS` |
| DB connection failed | Wrong `DATABASE_URL` / PG down | Check DSN, socket path, `pg_isready` |
| Model returns paid-model error | `OPENROUTER_MODEL` not free | Switch to a `:free` variant |
