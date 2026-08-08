FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/data/hf-cache

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY core/ core/
COPY api/ api/
COPY ingest/ ingest/
# snapshot + queries ship in the image so indexing can run in-container:
#   docker compose run api uv run --no-sync python -m ingest.index_abstracts
COPY data/queries.toml data/queries.toml
COPY data/snapshot/ data/snapshot/

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
