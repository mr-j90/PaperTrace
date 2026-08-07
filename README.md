# PaperTrace — an agentic RAG app for the RAG/agents/eval/LLMOps literature

An AI research assistant over the ~12,500 arXiv papers on **RAG, LLM agents, LLM
evaluation, and LLMOps** — the literature about the very techniques it's built from.
Ask it a question and watch it think: an agent visibly rewrites your query, chooses
tools, gathers evidence across paper text *and* paper metadata, then answers with
citations back to arXiv.

This is my LLM Zoomcamp capstone: an end-to-end agentic RAG application — ingestion to
cloud — built and owned by me. The full decision trail lives in
[`SPEC.md`](SPEC.md) and the wayfinder map under
[`.scratch/arxiv-assistant/`](.scratch/arxiv-assistant/map.md).

---

## The problem

Questions about a fast-moving research field come in two shapes, and most tools serve
only one:

- **Semantic** — *"How do the main approaches to evaluating RAG faithfulness differ?"*
  Needs meaning-level search over paper text and multi-paper synthesis.
- **Analytical** — *"How many agent-evaluation papers were published each month of
  2026?"* Needs counting, filtering, grouping — things vector search is structurally
  bad at.

Big scholarly tools (Elicit, ScholarQA, alphaXiv) answer over all of science and can't
afford per-paper depth on one niche; no open tool serves this niche with both layers.
PaperTrace treats it as an **agent problem**: one LLM loop, two grounded tools —

- `semantic_search` — hybrid (dense + sparse) retrieval with cross-encoder re-ranking
  over a layered index: every paper's abstract, plus section-level full text for a
  curated ~2,000-paper tier.
- `metadata_query` — typed filters/aggregations over the full corpus's metadata in
  DuckDB. Counts are counted, not vibed.

The agent's whole thought process — rewritten queries, tool calls, evidence, latency —
streams into the chat as an inline, collapsible **trace** on every answer.

## How it works

```
 browser ──► Next.js chat (inline agent trace, citations, 👍/👎)
                │ SSE
                ▼
            FastAPI ──► LangGraph agent (evidence loop)
                          ├── semantic_search ──► Qdrant   (hybrid + re-rank)
                          └── metadata_query  ──► DuckDB   (CC0 arXiv metadata)
                                   ▲
                     Prefect ingestion (snapshot | daily delta)
                                   ▲
                     arXiv API (pinned queries, polite rate)

 every turn ──► Langfuse trace (self-hosted)  +  Postgres row ──► Grafana (6 charts)
```

- **Corpus:** ~12,526 papers (8 pinned topical queries, 2020→now, verified against
  arXiv search). Metadata and abstracts are CC0 and ship in the repo; full text is
  fetched at ingest (HTML-first) and never redistributed. A **pinned snapshot** makes
  every eval and every reviewer run reproducible; the live instance refreshes daily.
- **Agent:** LangGraph evidence loop — rewrite → tool-choice → gather → synthesize —
  with Claude by default (Haiku dev / Sonnet demo), swappable to OpenAI/Groq/Ollama
  with one env change. Embeddings and re-ranker run locally; the chat LLM is the only
  paid API.
- **Ingestion:** one parameterized Prefect flow, two modes (snapshot / daily delta):
  fetch → normalize → load DuckDB → select full-text tier → parse → chunk → embed →
  index → validate.

## The eval story

No open-source paper assistant I surveyed ships a real evaluation. This one treats the
eval as a first-class deliverable (`eval/`, results committed, report linked here):

| Layer | What's measured |
|---|---|
| Retrieval | 4-way ladder — BM25 → dense → hybrid → hybrid+re-rank — hit-rate@k / MRR on 140 pinned questions; winner ships |
| Answers | 2 prompts × 2 models, LLM-as-judge (faithfulness, citation correctness, completeness) + hand spot-checks |
| Agent | Routing accuracy, tool-arg exact match, execution accuracy on analytical queries |
| CI | A free smoke slice runs on every push and fails on regression |

Ground truth: ~200 LLM-generated, hand-checked questions pinned to the corpus snapshot,
every record labeled with its expected tool.

## Ops

Every turn dual-writes: a full **Langfuse** trace (self-hosted — the whole LLMOps stack
runs in this repo's compose) and a flat **Postgres** row feeding a **Grafana**
dashboard-as-code with six charts (volume, latency p50/p95, route split, feedback rate,
cost/day, tool-error rate). User feedback (👍/👎 + comment) lands in both.

Deployment is **Fly.io, fully self-hosted, estate-as-code**: a `fly.toml` per app plus
an idempotent `bootstrap.sh` — the same compose stack you run locally is what runs in
production. GitHub Actions lint/test/eval-smoke every PR and auto-deploy green merges.
The live demo is guarded by a per-session rate limit and a $2/day LLM spend cap.

## Quickstart

```bash
git clone https://github.com/mr-j90/llm-zoomcamp-project-capstone.git
cd llm-zoomcamp-project-capstone
cp .env.example .env            # set ANTHROPIC_API_KEY (or swap provider — see docs)
docker compose up               # api, web, qdrant, postgres, grafana, prefect
                                # (+ langfuse via: --profile observability)
# open http://localhost:3000
```

1. Ingest the pinned snapshot: `docker compose run ingest snapshot`
   (or a fast, tiny full-text tier: `FULLTEXT_BUDGET=25 docker compose run ingest snapshot`)
2. Ask something — try the suggested chips, and open the trace on any answer.
3. Evals: `uv run eval/run_retrieval.py` (see `eval/README` for the full harness);
   dashboards at `localhost:3001` (Grafana), traces at `localhost:3002` (Langfuse).

## Development

```bash
uv sync        # install (Python 3.12, pinned via .python-version)
make check     # everything CI runs: ruff lint+format, mypy, pytest
```

CI (GitHub Actions) runs `make check`'s steps plus a compose validation on every PR
and push to master.

### Corpus snapshot

The pinned corpus ships in the repo — `data/snapshot/` holds the metadata JSONL
(CC0), the sorted ID list, and a manifest with per-topic counts; **you don't need to
fetch anything to use it.** To regenerate it from the committed query definitions
(`data/queries.toml`, the corpus's source of truth):

```bash
uv run python -m ingest.snapshot              # full harvest, ~5 min at arXiv's polite rate
uv run python -m ingest.snapshot --limit 50   # quick smoke run (don't commit)
```

The harvester respects arXiv's API terms (1 request / 3 s, single connection) and
fails loudly rather than committing a short corpus.

## Rubric map (for reviewers)

| Criterion | Where |
|---|---|
| Problem description | This README + [SPEC §1](SPEC.md) |
| Retrieval flow | Knowledge base (Qdrant + DuckDB) + LLM agent |
| Retrieval evaluation | 4-way ladder, best used · `eval/` |
| LLM evaluation | 2×2 grid, LLM-judge + execution accuracy · `eval/` |
| Interface | Next.js UI **and** FastAPI API |
| Ingestion pipeline | Prefect (dedicated tool) · `ingest/` |
| Monitoring | Feedback + Grafana dashboard (6 charts) · `monitoring/` |
| Containerization | Everything in docker-compose |
| Reproducibility | Pinned snapshot + committed queries/IDs + pinned deps |
| Best practices | Hybrid search · re-ranking · query rewriting (all evidenced in `eval/`) |
| Cloud | Fly.io, estate-as-code · `deploy/fly/` |

## v2 (explicitly deferred)

Live fetch of out-of-corpus papers · paper upload · per-paper deep-dive surface ·
scheduled digests · text-to-SQL for the metadata store · MCP server exposure.

## License

MIT
