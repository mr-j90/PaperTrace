.PHONY: check lint type test up down dev logs ingest reset

check: lint type test  ## all local checks (CI runs these + compose validation)

# --- stack lifecycle ---------------------------------------------------------
# the observability profile (Langfuse) is part of the full stack
COMPOSE := docker compose --profile observability

up:  ## build + start the full stack (web :3000, api :8000, prefect :4200, grafana :3001, langfuse :3002)
	$(COMPOSE) up -d --build

down:  ## stop the stack (data volumes survive)
	$(COMPOSE) down

dev:  ## infra only (qdrant/postgres/prefect/grafana) — run api+web from source
	docker compose up -d qdrant postgres prefect grafana

logs:  ## follow logs for the whole stack
	$(COMPOSE) logs -f --tail 100

ingest:  ## build the knowledge base (tiny tier by default; FULLTEXT_BUDGET=n to change)
	PREFECT_API_URL=http://localhost:4200/api \
	PAPERTRACE_FULLTEXT_BUDGET=$(or $(FULLTEXT_BUDGET),25) \
	uv run python -m ingest.flow

reset:  ## stop the stack and DELETE ALL DATA VOLUMES (index, db, dashboards)
	$(COMPOSE) down -v

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy

test:
	uv run pytest
