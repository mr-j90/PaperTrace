# PaperTrace — LLM Zoomcamp Capstone (Reviewer Guide)

> **You are on the `capstone-review` branch** — a reviewer-oriented walkthrough of this
> project against the [LLM Zoomcamp evaluation criteria](https://github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md).
> The `master` branch carries the portfolio-style README; the code is identical.

**PaperTrace** is an agentic RAG application over the ~13,300 arXiv papers on RAG, LLM
agents, LLM evaluation, and LLMOps. One LLM agent, two grounded tools: hybrid semantic
search over paper text, and typed SQL-backed queries over paper metadata — with every
answer streaming its full reasoning trace (tool calls, evidence, latency) into the UI.

Per the project brief this is *"a RAG application, an agent application, or a
combination of both"* — deliberately the **combination**. The dataset is the sanctioned
**"Articles"** kind (arXiv papers; the course FAQ is not used anywhere).

---

## Reviewer quickstart (10 minutes)

```bash
git clone https://github.com/mr-j90/PaperTrace.git && cd PaperTrace
git checkout capstone-review
cp .env.example .env             # add ANTHROPIC_API_KEY=sk-ant-...  (the only paid API)

make up                          # full stack: web, api, qdrant, postgres, grafana,
                                 #   prefect, langfuse (~first build takes a few minutes)
make ingest                      # knowledge base from the committed snapshot (~10 min:
                                 #   13.3k abstract embeddings + a small full-text tier)
```

Then open:

| URL | What you're looking at |
|---|---|
| http://localhost:3000 | The chat UI — click a suggested chip, expand the **trace** on the answer |
| http://localhost:4200 | Prefect — the ingestion flow run + the registered `daily-delta` schedule |
| http://localhost:3001 | Grafana — the monitoring dashboard (7 charts, no login) |
| http://localhost:3002 | Langfuse — per-turn traces (`dev@papertrace.local` / `papertrace123`) |

Four questions that exercise the four behaviors (they're the UI's suggested chips):

1. *"How do the main approaches to evaluating RAG faithfulness differ?"* — multi-step semantic synthesis
2. *"How many papers about agent evaluation were published each month of 2026?"* — exact analytical counts (watch the SQL in the trace)
3. *"What's new in RAG evaluation this month?"* — date-filtered freshness
4. *"What retrieval approaches does the RAG paper by Lewis et al. combine?"* — targeted lookup, hybrid + rerank at work

---

## The evaluation criteria, one by one

### 1. Problem description

*The problem*: questions about a fast-moving research field come in two shapes —
semantic ("how do X approaches differ?") and analytical ("how many papers per
month?") — and naive RAG is structurally bad at the second (top-k retrieval hands you
a vibe, not a number). PaperTrace routes between a hybrid retriever and a typed
metadata engine via LLM tool choice. Full context: this README, [`SPEC.md`](SPEC.md) §1–2,
and the complete decision record in [`.scratch/arxiv-assistant/`](.scratch/arxiv-assistant/map.md).

### 2. Retrieval flow — knowledge base + LLM, end to end

A LangGraph agent ([`core/agent.py`](core/agent.py)) drives two tools
([`core/tools.py`](core/tools.py)):

- `semantic_search` → **Qdrant** (one layered collection: 13.3k abstract cards + section-level
  full text for a curated tier) — [`core/retrieval.py`](core/retrieval.py)
- `metadata_query` → **DuckDB** (typed, parameter-bound SQL built by the tool, never the LLM) —
  [`core/metadata.py`](core/metadata.py)

Answers cite only papers actually returned as evidence (hallucinated ids are dropped:
`_ground_citations` in [`core/agent.py`](core/agent.py)).

### 3. Retrieval evaluation — multiple approaches, best one used

The 4-way ladder in [`eval/results/report.md`](eval/results/report.md), 140 ground-truth
questions, hit-rate@8 / MRR:

| mode | hit@8 | MRR |
|---|---|---|
| sparse (BM25) | 0.864 | 0.740 |
| dense | 0.721 | 0.552 |
| hybrid | 0.857 | 0.754 |
| **hybrid + rerank (shipped)** | **0.893** | 0.749 |

Reproduce free & locally: `uv run python -m eval.run_retrieval` ([`eval/run_retrieval.py`](eval/run_retrieval.py)).
The shipped default is the winner (`core/retrieval.py`, `mode="hybrid_rerank"`).

### 4. LLM evaluation — multiple approaches, best one used

2 prompts × 2 models, LLM-as-judge (faithfulness / citation correctness / completeness),
in [`eval/results/report.md`](eval/results/report.md): the **citation-strict prompt wins**
(+0.39 over a loose baseline on Haiku) and is the shipped system prompt; Sonnet edges
Haiku, matching the documented model tiering. Judge caveat + raw judgments committed
([`eval/results/judgments.jsonl`](eval/results/judgments.jsonl)).
Reproduce: `uv run python -m eval.run_llm` (~$5). Agent-level metrics too:
**routing accuracy 0.995, tool-arg match 1.0, execution accuracy 1.0** (n=200,
`uv run python -m eval.run_agent`).

### 5. Interface — UI *and* API

- **Web UI** (Next.js, [`web/`](web/)): streaming chat, inline collapsible trace,
  arXiv citation pills, suggested chips, model picker, 👍/👎 + comment feedback.
- **API** (FastAPI, [`api/main.py`](api/main.py)): `POST /chat` streams the agent's events
  over SSE; `POST /feedback`; `GET /healthz`. Try it raw:
  ```bash
  curl -sN -X POST localhost:8000/chat -H 'Content-Type: application/json' \
    -d '{"question": "How many rag papers in June 2026?"}'
  ```

### 6. Ingestion pipeline — automated, dedicated tool (Prefect)

One parameterized **Prefect** flow, two modes ([`ingest/flow.py`](ingest/flow.py),
[`ingest/delta.py`](ingest/delta.py)): snapshot ingest (fetch → normalize → DuckDB →
tier select → HTML-first full text → chunk → embed → index → validation report) and a
**daily delta refresh** (watermark + revision sweep, withdrawal flagging, scheduled
`0 6 * * *` — visible under Deployments at localhost:4200, run by the compose
`scheduler` service).

### 7. Monitoring — feedback collected + dashboard with 5+ charts

Every turn dual-writes ([`api/main.py`](api/main.py), [`core/turnlog.py`](core/turnlog.py)):
a **Langfuse** trace (self-hosted, sessions per conversation, feedback as scores) and a
**Postgres** row. **Grafana** auto-provisions a **7-chart** dashboard as code
([`monitoring/grafana/`](monitoring/grafana/)): query volume, latency p50/p95, route
split, feedback rate, cost/day, turn-error rate, tokens/day — anonymous read at
localhost:3001. User feedback (thumbs + comment) lands in both stores, keyed by turn.

### 8. Containerization — everything in docker-compose

[`docker-compose.yml`](docker-compose.yml): web, api, qdrant, postgres, grafana,
prefect, scheduler, plus the self-hosted Langfuse stack (6 pinned services) as the
`observability` profile. `make up` starts all of it; `make down` / `make reset` manage it.

### 9. Reproducibility

- **Data ships in the repo**: the pinned corpus snapshot ([`data/snapshot/`](data/snapshot/) —
  CC0 metadata for 13,124 papers, manifest with per-topic counts) is committed;
  `make ingest` needs no network calls to arXiv. Regeneration is scripted and rate-limit
  polite ([`ingest/snapshot.py`](ingest/snapshot.py)).
- **Pinned everything**: `uv.lock`, `bun.lock`, pinned Docker images, `.python-version`.
- **CI proves it**: every push runs lint, types, 47 tests, an **eval smoke slice with
  real local models**, and compose validation on a cold runner
  ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).
- Ground truth + eval results committed; full eval re-runnable via
  [`.github/workflows/eval.yml`](.github/workflows/eval.yml) (on-demand).

### 10. Best practices (bonus points)

| Practice | Where | Evidence |
|---|---|---|
| Hybrid search (text + vector) | BM25 sparse + dense bge, RRF fusion in Qdrant (`core/retrieval.py`) | ladder: hybrid 0.857 vs dense 0.721 |
| Document re-ranking | local cross-encoder rescoring fused top-30 (`core/rerank.py`) | ladder: 0.893 hit@8, best rung |
| User query rewriting | the agent's explicit query-formulation step — visible in every trace | trace UI; system prompt in `core/agent.py` |

### Bonus: cloud deployment — **not claimed**

Deliberately descoped ([#11](https://github.com/mr-j90/PaperTrace/issues/11)); the full
Fly.io estate-as-code design is documented in [`SPEC.md`](SPEC.md) §9 for future work.
Everything runs locally with `make up`.

---

## Repo map

```
core/        agent (evidence loop), retrieval, metadata engine, monitoring writer
api/         FastAPI: SSE chat, feedback, health
web/         Next.js chat UI with the inline trace
ingest/      snapshot harvester, Prefect flows (snapshot + daily delta), scheduler
eval/        ground truth, 4 runners, committed results + report, CI smoke gate
monitoring/  Postgres schema, Grafana dashboards-as-code
data/        committed pinned snapshot (CC0) + query definitions
.scratch/    the full decision record (wayfinder map + 10 resolved decision tickets)
SPEC.md      the locked v1 spec every section of this project traces to
CONTEXT.md   the project's domain glossary
```
