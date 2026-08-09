# 1. Bind-mount `./data` into the api container

Date: 2026-08-08

## Status

Accepted

## Context

The stack is split between the host and Docker: `make ingest` runs on the host
(`uv run python -m ingest.flow`) while the api serves from a container. Ingestion
writes to two stores with different visibility:

- **Qdrant** is a network service. The host-run flow reaches it through the
  `localhost:6333` port mapping, and the containerized api reaches the same
  instance at `http://qdrant:6333`. Vectors written from anywhere are visible
  everywhere.
- **DuckDB** (`data/papers.duckdb`) is a file. The host-run flow writes it to
  `./data` on the host, but the api container had no mount covering `/app/data`
  — the image bakes in `data/queries.toml` and `data/snapshot/` (so ingestion
  *can* run in-container), deliberately not the database itself.

The observed symptom: `semantic_search` returned results while `metadata_query`
answered every call with "metadata store unavailable — ingestion may be running
or has not been run yet", even though ingestion had completed successfully.
`MetadataStore.query` collapses every `duckdb.Error` — including a missing file
— into that one message, which made the failure look transient when it was
structural.

A second, quieter problem: the api writes `data/feedback.jsonl` (user
thumbs-up/down) inside the container. With no volume behind it, that data was
destroyed on every container rebuild.

## Decision

Bind-mount the repo's data directory into the api service:

```yaml
  api:
    volumes:
      - ./data:/app/data
```

The host `./data` directory is the single source of truth for file-based data.
Host-run ingestion becomes immediately visible to the containerized api with no
rebuild; container-run ingestion (`docker compose run api uv run --no-sync
python -m ingest.flow`) writes through to the host; feedback survives rebuilds.

Alternatives considered:

- **Named volume for `/app/data`.** Survives rebuilds, but host-run
  `make ingest` cannot write into it directly — every ingest would have to run
  in-container, and inspecting the DuckDB file from the host (DBeaver, `duckdb`
  CLI, notebooks) would require copying it out. Rejected for developer-loop
  friction.
- **Bake `papers.duckdb` into the image.** Makes the image self-contained but
  stale the moment ingestion re-runs, and forces a rebuild per refresh. The
  Dockerfile already draws this line correctly (config and snapshot ship in the
  image, data does not).
- **Move paper metadata to Postgres** (already in the stack). Removes
  file-visibility problems entirely, but SPEC §5 chose DuckDB for the typed
  analytical tool and the single-file store is a feature for evaluation and
  local inspection. Worth revisiting only if concurrent-writer needs appear.

## Consequences

- The bind mount shadows the image's baked-in `/app/data` (`queries.toml`,
  `snapshot/`) with the host copies. In this repo those are the same files, but
  a deployment without the repo checkout must provide `./data` (or switch to a
  named volume plus in-container ingestion).
- DuckDB is single-writer: an in-flight ingest briefly locks the file against
  the api's read-only connections. `core/metadata.py` already retries and then
  degrades to a tool-level error, so this stays a transient blip rather than a
  crash.
- The "metadata store unavailable" message still conflates *file missing* with
  *file locked*; splitting those would have made this incident diagnosable from
  the chat trace alone. Left as a follow-up.
