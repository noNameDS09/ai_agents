# ---- Frontend build -------------------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Backend image --------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Project metadata + source first so dependency layers cache well.
COPY pyproject.toml uv.lock* ./
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# FastAPI serves the built SPA at / and /assets.
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Default image is lean: no torch. For on-prem local embeddings, build with
#   docker build --build-arg UV_EXTRAS="--extra local" .
ARG UV_EXTRAS=""
RUN uv sync --no-dev ${UV_EXTRAS}

EXPOSE 8000

# Apply migrations (idempotent), then serve. Use the venv entry points directly
# so startup does not re-resolve/sync dependencies.
CMD ["sh", "-c", "/app/.venv/bin/alembic upgrade head && /app/.venv/bin/uvicorn src.agent_api.main:app --host 0.0.0.0 --port 8000"]
