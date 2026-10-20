# Setup & Run Guide

Complete guide to running all services for the `agent-api` + ComplianceOS system.

---

## 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| PostgreSQL | 14+ | [postgresql.org](https://www.postgresql.org/download/) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| Docker | latest | [docker.com](https://www.docker.com/get-started/) |
| Git | latest | [git-scm.com](https://git-scm.com/) |

---

## 2. Clone & install

```bash
git clone git@github.com:noNameDS09/ai_agents.git
cd ai_agents
cp .env.example .dev.env   # edit secrets
uv sync
```

## 2b. Docker Compose (all-in-one)

Start everything (PostgreSQL + Qdrant + backend) with one command:

```bash
# Start all services (builds the image, including the frontend, on first run)
docker compose up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f backend

# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes all data)
docker compose down -v
```

**Ports are offset to avoid clashing with a local dev setup:**

| Service | Compose host port | Notes |
|---|---|---|
| Backend / UI | `8000` | Serves the built SPA at `/` |
| PostgreSQL | `5433` | Local Postgres keeps `5432` |
| Qdrant | `6335` | A standalone Qdrant keeps `6333` |

The backend talks to `postgres:5432` and `qdrant:6333` on the Compose network.

**Notes:**

- The image runs `alembic upgrade head` on startup (idempotent), then uvicorn.
- The frontend is built inside the Docker build (multi-stage), so no host
  `npm run build` is required for Compose.
- `scripts/init-db.sql` creates `agent_test` and a non-superuser `compliance_app`
  role on first boot. See §16 for switching the runtime to that role.
- Compose reads `OPENROUTER_API_KEY` / `TAVILY_API_KEY` / `API_KEY` from the
  host environment or a `.env` file next to `docker-compose.yml`.

For development with hot-reload, use the manual setup below instead.

---

## 3. PostgreSQL

### Start PostgreSQL

```bash
# Linux (systemd)
sudo systemctl start postgresql
sudo systemctl enable postgresql   # auto-start on boot

# macOS (Homebrew)
brew services start postgresql@16

# Docker
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 postgres:16
```

### Create databases

```bash
psql -U postgres -c "CREATE DATABASE agent_dev;"
psql -U postgres -c "CREATE DATABASE agent_test;"
```

### Verify

```bash
pg_isready
psql -U postgres -d agent_dev -c "\dt"
```

---

## 4. Qdrant (vector store)

```bash
# Start Qdrant container
docker run -d -p 6333:6333 --name qdrant qdrant/qdrant

# Verify
curl http://localhost:6333/
# Should return: {"title":"qdrant - vector search engine",...}

# Stop
docker stop qdrant
docker rm qdrant

# Restart
docker start qdrant
```

---

## 5. Environment variables

Edit `.dev.env` (gitignored, never commit):

```env
# Required
API_KEY=dev-secret-key-change-me
DATABASE_URL=postgresql+asyncpg://postgres@/agent_dev?host=%2Frun%2Fpostgresql
TEST_DATABASE_URL=postgresql+asyncpg://postgres@/agent_test?host=%2Frun%2Fpostgresql

# OpenRouter (free models only)
OPENROUTER_API_KEY=sk-or-your-real-key
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free

# Tavily (web search)
TAVILY_API_KEY=tvly-your-key-here
TAVILY_MCP_URL=https://mcp.tavily.com/mcp/

# Security
CORS_ORIGINS=["*"]
TRUSTED_HOSTS=["localhost","127.0.0.1"]
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
MAX_REQUEST_BODY_BYTES=262144
MAX_MESSAGE_LENGTH=4000

# Compliance (optional)
COMPLIANCE_EMBEDDING_PROVIDER=openrouter
COMPLIANCE_EMBEDDING_MODEL=nvidia/llama-nemotron-embed-vl-1b-v2:free
COMPLIANCE_EMBEDDING_DIM=2048
COMPLIANCE_QDRANT_URL=http://localhost:6333
COMPLIANCE_APSCHEDULER_ENABLED=true
```

---

## 6. Database migrations

```bash
# Apply all migrations
uv run alembic upgrade head

# Check current revision
uv run alembic current

# Create a new migration (after model changes)
uv run alembic revision --autogenerate -m "description"

# Rollback one step
uv run alembic downgrade -1

# Rollback to specific revision
uv run alembic downgrade <revision_id>
```

### Seed reference data

```bash
uv run python scripts/seed_reference_data.py
```

Seeds 6 jurisdictions: CA, NY, TX, FL, IL, Federal (US).

---

## 7. Run the backend (FastAPI)

```bash
# Development (with auto-reload)
uv run uvicorn src.agent_api.main:app --reload --host 0.0.0.0 --port 8000

# Production
uv run uvicorn src.agent_api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Verify

```bash
curl http://localhost:8000/health
curl -H "X-API-Key: dev-secret-key-change-me" http://localhost:8000/v1/tools
curl -H "X-API-Key: dev-secret-key-change-me" http://localhost:8000/v1/compliance/jurisdictions
```

---

## 8. Run the frontend

### Option A — Vite dev server (hot-reload, recommended for development)

```bash
# Terminal 1: Backend
uv run uvicorn src.agent_api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

Open `http://localhost:5173` — Vite proxies `/health` and `/v1` to the backend on `:8000`.

### Option B — Production build (served by FastAPI)

```bash
cd frontend && npm run build
cd .. && uv run uvicorn src.agent_api.main:app --reload
```

Open `http://localhost:8000` — same origin, no separate frontend server needed.

---

## 9. Run tests

```bash
uv run pytest                    # all tests
uv run pytest tests/compliance   # compliance tests only
uv run pytest -v                 # verbose
uv run pytest -k "tools"         # filter by name
```

---

## 10. Stop all services

### Docker Compose (recommended)

```bash
# Stop all services (postgres, qdrant, backend)
docker compose down

# Stop and remove volumes (WARNING: deletes all data)
docker compose down -v

# Stop a specific service
docker compose stop backend
docker compose stop qdrant
docker compose stop postgres
```

### Manual (development mode)

```bash
# Stop uvicorn
pkill -f "uvicorn.*agent_api" 2>/dev/null

# Stop Vite dev server
pkill -f "vite" 2>/dev/null

# Stop Qdrant
docker stop qdrant 2>/dev/null

# Stop PostgreSQL (optional)
sudo systemctl stop postgresql
```

Or use PID files from background runs:
```bash
for f in /tmp/opencode/*.pid; do
  [ -f "$f" ] && kill $(cat "$f") 2>/dev/null
done
docker stop qdrant 2>/dev/null
```

---

## 11. Makefile targets

```bash
make sync            # install dependencies
make test            # run tests
make run             # start backend
make frontend-dev    # start Vite dev server
make frontend-build  # build frontend to dist/
make dev             # sync + test
```

---

## 12. Port summary

| Service | Port | Start command |
|---------|------|---------------|
| FastAPI backend | 8000 | `uv run uvicorn src.agent_api.main:app --reload` |
| Vite dev server | 5173 | `cd frontend && npm run dev` |
| Qdrant (local) | 6333 | `docker run -p 6333:6333 qdrant/qdrant` |
| PostgreSQL (local) | socket (`/run/postgresql`) | system service |
| PostgreSQL (Compose) | 5433 | `docker compose up -d postgres` |
| Qdrant (Compose) | 6335 | `docker compose up -d qdrant` |

---

## 13. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `SettingsError: error parsing value for field "cors_origins"` | Empty env var in shell | `unset CORS_ORIGINS TRUSTED_HOSTS` then re-source `.dev.env` |
| `ModuleNotFoundError: No module named 'compliance'` | `src/` not on Python path | Run from project root; `uv run` handles this |
| `relation "audit_events" already exists` | Duplicate table name | Compliance audit table is `compliance_audit_events` |
| `pgvector` not available | Extension not installed | Use Qdrant (recommended) |
| `interrupt()` not resuming | LangGraph checkpoint mismatch | Check thread_id and checkpoint namespace |
| Frontend shows "no response" | API key not saved | Enter `dev-secret-key-change-me` and click save |
| Chat hangs | Invalid `OPENROUTER_API_KEY` | Set a real key from [openrouter.ai/keys](https://openrouter.ai/keys) |
| `401` on `/v1/tools` | Wrong/missing `X-API-Key` | Match `API_KEY` in `.dev.env` |
| Qdrant connection refused | Qdrant not running | `docker start qdrant` |
| `alembic: command not found` | Not in venv | Use `uv run alembic ...` |

---

## 14. Production hardening checklist

- [ ] Restrict `CORS_ORIGINS` to exact frontend origins
- [ ] Restrict `TRUSTED_HOSTS` to actual hostnames
- [ ] Rotate `API_KEY` and `OPENROUTER_API_KEY`; store in a secret manager
- [ ] Replace in-memory rate limiter with Redis-backed limiting for multi-node
- [ ] Terminate TLS at a reverse proxy; enforce HTTPS
- [x] Add database migrations (Alembic) — `alembic upgrade head`
- [ ] Add structured logging with request IDs and secret redaction
- [ ] Add JWT/OAuth2 end-user authentication for external users
- [x] Build frontend in the container image (multi-stage Docker build)
- [ ] Set `OPENROUTER_MODEL` to a verified free model
- [x] Configure Qdrant (Docker Compose)
- [x] Enable Postgres RLS on all tenant-scoped tables (`FORCE ROW LEVEL SECURITY`)
- [ ] **Connect the app as a non-superuser role** (`compliance_app`); superusers
      bypass RLS regardless of policies. See §16.
- [ ] Issue per-tenant API keys (users.api_key_hash + org_id) — tenant checks are
      enforced in the API, but the bootstrap key is cross-org by design.
- [x] Set up RBAC with at least 4 roles
- [x] Enable hash-chained audit events
- [x] Configure APScheduler for regulatory monitoring
- [ ] Move evidence storage to S3-compatible object storage
- [ ] Run evaluation harness in CI
- [ ] Set up monitoring and alerting
- [ ] Document incident response procedures
- [ ] Conduct security review of all service-backed tools

---

## 16. Optional: local embeddings and the non-superuser DB role

### Local embeddings (sensitive documents)

`sentence-transformers` is an optional extra (it pulls torch, ~2GB), used when
you cannot send document text to a remote embedding API:

```bash
uv sync --extra local
export COMPLIANCE_EMBEDDING_PROVIDER=local
export COMPLIANCE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Local vectors are 384-dim and are stored in a separate, dimension-scoped
collection (`compliance_chunks_384`), so they never mix with 2048-dim
OpenRouter vectors. Switching providers triggers re-indexing of stored
versions via the scheduler.

### Switching runtime to `compliance_app` (enforces RLS)

RLS is bypassed for superusers. To make policies effective:

1. Ensure the role exists (Compose does this on first boot):
   `psql -U postgres -c "\du compliance_app"`.
2. Run migrations as the owner (`postgres`).
3. Point the **runtime** connection at the app role:
   ```
   DATABASE_URL=postgresql+asyncpg://compliance_app:compliance-app-dev@localhost:5433/agent_dev
   ```
4. The API sets the tenant context per request
   (`set_config('app.current_org_id', ..., true)`), so queries only see the
   authenticated principal's organization. Requests without a tenant context
   fail closed (zero rows).

Change the default app password before any shared deployment.

---

## 15. Documentation index

| Doc | Description |
|-----|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, layers, data model, deployment |
| [API.md](API.md) | Full API reference with request/response schemas |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Dependency choices and governance |
| [SECURITY.md](SECURITY.md) | Security controls and boundaries |
| [FRONTEND.md](FRONTEND.md) | React/Vite frontend development and deployment |
| [RUNBOOK.md](RUNBOOK.md) | Local dev, Postgres provisioning, troubleshooting |
| [SETUP.md](SETUP.md) | This file — complete setup and run guide |
| [AGENTS.md](../AGENTS.md) | Agent conventions and key entry points |
| [ai-compliance/](ai-compliance/) | ComplianceOS domain docs (architecture, data model, trust model, agents, API, rules engine, evaluation, runbook) |

## License

MIT