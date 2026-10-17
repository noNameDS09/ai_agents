# API reference

Base path: `/v1`. All endpoints require `X-API-Key` except `GET /health`.

## Authentication

Send `X-API-Key: <API_KEY>` on every request. The expected key is the
`API_KEY` setting (`.env.example`). Invalid or missing key → `401`.

## Rate limiting

Token bucket per API key. Defaults: 60 requests per 60 seconds
(`RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`). Exceeded → `429` with
`Retry-After` header.

## Endpoints

### POST /v1/chat

Send a user message to the agent. The agent may call tools before answering.

**Request**

```json
{
  "thread_id": "optional-uuid (new conversation if omitted)",
  "message": "What is 23 * 17 + 5?",
  "model": "optional override (must be a free OpenRouter model)"
}
```

- `message` max 4000 chars (setting `MAX_MESSAGE_LENGTH`).
- `thread_id` must be a valid UUID string when provided.

**Response** (`200`)

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": "23 * 17 + 5 = 396",
  "tool_calls": [{"name": "calculator", "arguments": {"expression": "23 * 17 + 5"}}],
  "steps": 1
}
```

**Errors:** `400` invalid input; `401` auth; `429` rate limit;
`502` inference unavailable; `503` OpenRouter API key not configured.

### GET /v1/tools

List allowlisted tools with their JSON-schema parameters.

**Response**

```json
{
  "tools": [
    {"name": "calculator", "description": "...", "parameters": {...}},
    {"name": "current_time", ...},
    {"name": "knowledge_base_lookup", ...}
  ]
}
```

### GET /v1/threads/{thread_id}

Return stored message history for a thread (from `app_messages`).

**Response**

```json
{
  "thread_id": "...",
  "messages": [
    {"role": "user", "content": "What is 2+2?", "created_at": "..."},
    {"role": "assistant", "content": "4", "created_at": "..."}
  ]
}
```

`404` when the thread has no stored history.

### GET /health

Liveness/readiness. No auth required.

```json
{
  "status": "ok",
  "database": "ok",
  "inference_configured": true
}
```

`503` when database or inference configuration is missing.
