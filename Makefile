.PHONY: sync lint test run dev frontend-dev frontend-build docker-up docker-down docker-logs

sync: ## Install production and dev dependencies with uv
	uv sync

lint: ## Run ruff if installed, otherwise skip
	@ruff check src tests 2>/dev/null || echo "ruff not installed (optional)"

test: ## Run the automated test suite
	uv run pytest

run: ## Run the API server (requires .dev.env)
	uv run uvicorn src.agent_api.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev: ## Run Vite dev server with hot-reload (proxies to backend on :8000)
	cd frontend && npm run dev

frontend-build: ## Build the React/Vite frontend into frontend/dist
	cd frontend && npm run build

docker-up: ## Start all services (postgres, qdrant, backend) via Docker Compose
	docker compose up -d

docker-down: ## Stop all services via Docker Compose
	docker compose down

docker-logs: ## View backend logs
	docker compose logs -f backend

dev: sync test ## Set up environment and run tests (developer onboarding)
