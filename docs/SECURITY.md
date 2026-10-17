# Security controls

## Authentication

- Every stateful endpoint requires `X-API-Key` matching the `API_KEY` setting.
- `GET /health` is intentionally unauthenticated (liveness only, no data returned).
- API keys are never logged or echoed in responses.

## Rate limiting

- In-memory token bucket per API key (`security.RateLimiter`).
- Configurable via `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`.
- Excess requests → `429` with `Retry-After`.
- Note: per-process memory. Multi-node deployments should replace with a Redis-backed limiter.

## Input validation

- All request bodies validated with Pydantic v2.
- `message` capped at `MAX_MESSAGE_LENGTH` (default 4000).
- Client-supplied roles are restricted to `user`; the system prompt is server-side only — clients cannot inject system messages.
- `thread_id` must be a UUID.

## Tool safety

- Tools are defined once in `tools.py` and allowlisted in the LangGraph `ToolNode`.
- The model can only call names present in the allowlist.
- Local deterministic tools (no outbound network):
  - `calculator` — whitelisted AST arithmetic only (`+ - * / % // ** ()`), no `eval`.
  - `current_time` — returns UTC timestamp.
  - `knowledge_base_lookup` — static stub (no retrieval pipeline).
  - All other utility tools (json_format, text_transform, hash_text, etc.) — pure computation, no network.
- Service-backed tools (outbound network, security-sensitive):
  - `web_search`, `url_extract`, `web_crawl`, `web_map`, `web_research` — Tavily MCP (remote server).
    - API key from `TAVILY_API_KEY` env var only, never hardcoded.
    - Content size limits applied to extracted text.
    - SSRF prevention: URL validation before extraction/crawl.
    - Rate limited via Tavily's own limits + app-level rate limiter.
    - All calls audit-logged via `audit_events` table.

## Network / transport

- `CORSMiddleware`: origins limited to `CORS_ORIGINS` (default `*` for local dev; must be restricted before production).
- `TrustedHostMiddleware`: hosts limited to `TRUSTED_HOSTS`.
- Request body size capped at `MAX_REQUEST_BODY_BYTES`.
- OpenRouter calls send only the chat payload; API key transmitted via `Authorization: Bearer` header to `openrouter.ai` over HTTPS.

## Secrets

- `OPENROUTER_API_KEY` and `API_KEY` must come from the environment (Pydantic Settings), never hardcoded.
- `.env.example` contains placeholders only; `.dev.env` is gitignored.

## Security boundary / out of scope

- This is a backend-only service. Client-side key storage, end-user auth (OAuth2/JWT), and encryption-at-rest for the database are deployment-layer concerns and documented as future work in `docs/RUNBOOK.md`.
