# SPEC — PaperTrace (LLM Zoomcamp Capstone)

> **Status: v1 — locked.** Every build-blocking decision below was made through the
> wayfinder map at [`.scratch/arxiv-assistant/map.md`](.scratch/arxiv-assistant/map.md);
> each section links its decision ticket. Changing a decision means reopening its ticket,
> not editing this file ad hoc.
> Domain vocabulary lives in [`CONTEXT.md`](CONTEXT.md).

## 1. Problem

The literature on RAG, LLM agents, LLM evaluation, and LLMOps is its own fast-moving
field — roughly 12,500 arXiv papers since 2020 and dozens more each week. The people
building these systems ask two kinds of questions of that literature, and today's tools
serve neither well in one place:

- **Semantic** — "How do the main approaches to evaluating RAG faithfulness differ?"
  General-purpose paper tools (Elicit, ScholarQA, alphaXiv) answer over *all* of science
  and can't afford per-paper depth on one niche.
- **Analytical** — "How many agent-evaluation papers came out each month of 2026?"
  Vector search is structurally bad at counting and filtering; no cited-QA tool in the
  niche exposes the metadata layer.

**PaperTrace** is an agentic RAG application over exactly this slice of arXiv:
an agent that visibly gathers evidence across both layers — semantic search over paper
text and structured queries over paper metadata — and synthesizes cited answers.
It is "a RAG application, an agent application, or a combination of both" in the
[project brief](https://github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md)'s
terms: deliberately the combination.
*(Decisions: [01](.scratch/arxiv-assistant/issues/01-v1-capability-scope.md),
prior art: [03](.scratch/arxiv-assistant/issues/03-prior-art.md).)*

## 2. Capabilities

**V1 ships** ([01](.scratch/arxiv-assistant/issues/01-v1-capability-scope.md)):

1. **Cited Q&A** over the corpus — every claim cites papers, links to `arxiv.org/abs/{id}`.
2. **Multi-step agentic retrieval** — the *evidence loop* (search → gather evidence →
   synthesize), streamed to the UI as an inline trace. This is the demo lead.
3. **Analytical/metadata queries** — counts, filters, groupings over paper metadata via a
   typed tool inside the agent loop (LLM tool-choice; no separate router).
4. **Freshness queries** — "what's new in RAG eval this week?" = date-filtered metadata
   query + synthesis.
5. In-corpus single-paper questions ride the normal chat flow.

**Explicitly deferred to v2:** live fetch of out-of-corpus papers (v1 answers gracefully
that the paper isn't indexed), paper upload, a dedicated per-paper deep-dive surface,
scheduled digests/recommendations, text-to-SQL for the metadata store, MCP server
exposure.

## 3. Architecture

```
 browser ──► Next.js (chat + inline trace + feedback)
                │ SSE
                ▼
            FastAPI  POST /chat (streams agent events) · POST /feedback · GET /healthz
                │
                ▼
          LangGraph agent (evidence loop: rewrite → tool-choice → gather → synthesize)
                │                                    │
     semantic_search(query, scope)          metadata_query(filters, group_by, agg)
                │                                    │
                ▼                                    ▼
        Qdrant (one layered collection)        DuckDB (CC0 metadata)
        abstract cards ×12.5k                       ▲
        section chunks (~2k-paper tier)             │
                ▲                                   │
                └────────── Prefect flow ───────────┘
                 fetch → normalize → load → tier-select → parse → chunk → embed → index
                 (mode: snapshot | daily delta)

 every turn ─┬─► Langfuse trace (self-hosted: spans, prompts, evidence, cost)
             └─► Postgres row (ts, route, latency, tokens, cost, feedback, error)
                      └─► Grafana (dashboard-as-code, ≥6 charts)
```

## 4. Corpus & ingestion

*(Decisions: [02](.scratch/arxiv-assistant/issues/02-arxiv-data-access.md),
[04](.scratch/arxiv-assistant/issues/04-corpus-and-ingestion.md).)*

- **Boundary:** the verified 8-phrase union (RAG + LLM-agent + LLM-eval + LLMOps
  variants) over abstracts, submitted 2020→now — **~12,526 papers** (verified against
  arXiv search 2026-07-31). Query definitions are committed to the repo as the corpus's
  source of truth.
- **Tiering:** abstracts + CC0 metadata for **all** papers, shipped in-repo as JSONL.
  Full text for a **hybrid ~2k tier**: top ~1,000 by Semantic Scholar citation count +
  everything from the trailing ~6 months; the tier budget is a config parameter so a
  reviewer can reproduce with a tiny tier in minutes (full tier ≈100 min at the polite
  rate).
- **Reproducibility:** a **pinned snapshot** (committed ID list + metadata JSONL at a
  snapshot date) is what evals and reviewers build against. The live instance runs a
  **daily delta refresh** (`submittedDate:[lastRun TO now]`), flagging withdrawn
  versions.
- **Licensing & politeness:** metadata/abstracts are CC0 and redistributable; full text
  is fetched at ingest (HTML-first: `arxiv.org/html/{id}` post-Dec-2023, ar5iv older)
  and never redistributed. arXiv API: 1 request / 3 s, single connection.
- **Orchestration:** one parameterized **Prefect** flow, two modes (snapshot ingest /
  daily delta): fetch metadata → normalize & dedupe (flag withdrawals) → load DuckDB →
  select full-text tier → fetch & parse full text → chunk → embed → index →
  validate/report. Prefect satisfies the rubric's dedicated-ingestion-tool requirement.

## 5. Retrieval & agent design

*(Decision: [05](.scratch/arxiv-assistant/issues/05-retrieval-agent-architecture.md).)*

- **Agent:** LangGraph `StateGraph` (agent node + `ToolNode`, conditional edge). Stop
  when the model returns no tool calls, guarded by a max-turns cap. Exactly two tools:
  - `semantic_search(query, scope=abstracts|fulltext|all)` — hybrid retrieval over one
    layered Qdrant collection: *abstract cards* (title + abstract + venue/date; one per
    paper) and *section chunks* (~512 tokens, split on HTML section structure, title +
    heading prepended) discriminated by a `layer` payload field. Dense = local
    sentence-transformers (bge-small class); sparse = fastembed BM25/SPLADE; native
    fusion; cross-encoder re-rank (bge-reranker class) rescores fused top-30 → top-k;
    dedup to max 2–3 chunks per paper.
  - `metadata_query(filters, group_by, aggregate, sort, limit)` — typed parameters; the
    tool builds SQL against DuckDB. No LLM-generated SQL in v1.
- **Query rewriting** is the agent's explicit, logged query-formulation step (a
  best-practice rubric point, claimed honestly).
- **LLM:** Claude by default — Haiku for dev/cheap eval runs, Sonnet for demo and final
  eval numbers — via LangChain `init_chat_model`; README documents one-env-change swaps
  to OpenAI/Groq/Ollama. Embeddings and re-ranker are local: the chat LLM is the only
  paid API.

## 6. Evaluation

*(Decision: [06](.scratch/arxiv-assistant/issues/06-evaluation-design.md).)*

- **Ground truth:** ~200 LLM-generated, hand-checked questions pinned to the snapshot,
  in four JSONL files under `eval/ground_truth/` — retrieval ×140 (`q, source_arxiv_id,
  layer`), synthesis ×25 (multi-paper), analytical ×25 (`expected_tool_args,
  expected_rows`), freshness ×10. Every record carries an `expected_tool` label (the
  routing-accuracy set).
- **Retrieval eval:** the 4-way ladder — sparse-only → dense-only → hybrid → hybrid +
  re-rank — on hit-rate@k and MRR; winner ships as default. Evidences the hybrid and
  re-ranking rubric points.
- **LLM eval:** 2 prompts (citation-strict vs. baseline) × 2 models (Haiku, Sonnet),
  LLM-as-judge on faithfulness / citation correctness / completeness (1–5), judge bias
  caveat documented, ~20 judgments hand spot-checked; best cell ships. Analytical and
  freshness paths score **execution accuracy** against expected rows.
- **Agent metrics:** routing accuracy, tool-arg exact match, execution accuracy.
- **Harness:** plain-Python runners in `eval/`; results committed as JSON + a generated
  `report.md` the README links to. Full runs manual (paid API); **CI runs a free smoke
  slice** (~30 retrieval questions, local models + tool-arg exact-match) on every push
  and fails on regression. Platform-agnostic; Langfuse mirroring is a bonus layer, never
  a dependency.

## 7. Interface & demo

*(Decision: [07](.scratch/arxiv-assistant/issues/07-interface-and-demo.md).)*

- **API:** FastAPI owns the agent. `POST /chat` streams the LangGraph event stream over
  SSE (rewritten queries, tool calls + args, evidence, tokens); `POST /feedback`;
  `GET /healthz`. Rubric: UI **and** API.
- **UI:** Next.js chat. The trace renders **inline, ChatGPT/Claude-style**: agent steps
  stream as collapsible activity above the forming answer, folding into a per-message
  Trace block. Citations deep-link to arXiv; thumbs + comment per answer (dual-written
  per §8); suggested-question chips.
- **Live instance:** seeded from the pinned snapshot; free chat with per-session rate
  limit and daily spend cap; chips serve cached answers.
- **Demo script (2 min):** four questions, each showing a different loop behavior —
  multi-step synthesis, analytical, freshness, full-text deep-dive.

## 8. Observability & monitoring

*(Decision: [08](.scratch/arxiv-assistant/issues/08-observability-and-monitoring.md).)*

- **Langfuse, self-hosted** (v3 stack via its official compose file as an
  include/profile): traces, token/cost tracking, feedback scores. LangGraph callback
  integration.
- **Postgres + Grafana** for the rubric's monitoring: every turn dual-writes a Langfuse
  trace and a flat Postgres row (`ts, route, latency_ms, tokens, cost, feedback,
  error`); feedback is deliberately written to both. Grafana ships dashboard-as-code
  with ≥6 charts: query volume, latency p50/p95, route split, feedback rate, cost/day,
  tool-error rate — visible without any login.

## 9. Deployment & CI/CD

*(Decision: [09](.scratch/arxiv-assistant/issues/09-cloud-deploy-and-cicd.md).)*

- **Fly.io, fully self-hosted** (~11 apps, including the Langfuse stack). Principle:
  **stack parity** — the exact compose stack a user runs locally is what runs in
  production; no managed-SaaS dependency. Cloud bonus: 2 pts.
- **Estate-as-code:** committed `fly.toml` per app under `deploy/fly/` + idempotent
  `bootstrap.sh` (apps, volumes, secrets, private networking). Fly's Terraform provider
  is unmaintained — that, documented, is why there is no Terraform.
- **CI/CD (GitHub Actions):** PRs → ruff, mypy, unit tests, eval smoke slice. Merge to
  main → build images, `flyctl deploy` changed apps, concurrency-guarded.
- **Cost guardrails:** $2/day LLM cap tallied in Postgres with a friendly hard-stop;
  per-session rate limiting; cached chip answers. Infra baseline ~$40–80/mo accepted.
- **Secrets:** `fly secrets` in prod; git-ignored `.env` locally. Never committed.

## 10. Requirements conformance

Dataset fit: arXiv papers are the brief's sanctioned **"Articles: index and answer
questions from one or multiple articles"** category; the course FAQ (prohibited) is not
used. The app is end-to-end: ingestion → knowledge base → agent → UI → monitoring.

| Criterion (points) | Where it's met |
|---|---|
| Problem description (2) | §1, README |
| Retrieval flow (2) | Knowledge base (Qdrant + DuckDB) + LLM agent, §3/§5 |
| Retrieval evaluation (2) | 4-way ladder, hit-rate/MRR, best used — §6, `eval/` |
| LLM evaluation (2) | 2×2 prompt/model grid + judge + execution accuracy — §6 |
| Interface (2) | Next.js UI **and** FastAPI API — §7 |
| Ingestion pipeline (2) | Prefect flow (dedicated tool) — §4 |
| Monitoring (2) | Feedback collected + Grafana ≥6 charts — §8 |
| Containerization (2) | Everything in docker-compose (Langfuse via include) |
| Reproducibility (2) | Pinned snapshot, committed queries/IDs, uv-pinned deps, one-command up |
| Hybrid search (+1) | Dense+sparse fusion in Qdrant — §5, evidenced §6 |
| Re-ranking (+1) | Cross-encoder rescoring — §5, evidenced §6 |
| Query rewriting (+1) | Explicit, logged agent step — §5 |
| Cloud (+2) | Fly.io deployment, estate-as-code — §9 |
| Exceptional work (+3, case) | The shipped eval story (ladder + judge grid + agent metrics, smoke-gated in CI), the inline agent trace as a product surface, and a fully self-hosted LLMOps stack with laptop→cloud parity |

## 11. Repo layout

```
.
├── SPEC.md · README.md · CONTEXT.md
├── docker-compose.yml            # app, qdrant, postgres, grafana, prefect
│                                 # + langfuse compose include (profile)
├── pyproject.toml                # uv-managed, pinned
├── data/                         # pinned snapshot: queries.yaml, id list, metadata JSONL
├── ingest/                       # Prefect flow (snapshot | daily-delta modes)
├── core/                         # LangGraph agent, tools, retrieval, config
├── api/                          # FastAPI (chat SSE, feedback, health)
├── web/                          # Next.js UI (chat, inline trace, feedback)
├── eval/                         # ground_truth/, runners, results/, smoke
├── monitoring/                   # postgres schema, grafana dashboards-as-code
├── deploy/fly/                   # fly.toml per app + bootstrap.sh
└── .github/workflows/            # ci.yml, deploy.yml
```

## 12. Build order

1. Skeleton: uv env, compose stub, CI lint/test wiring.
2. Ingestion: Prefect flow → snapshot corpus in DuckDB + Qdrant.
3. Retrieval core: layered collection, hybrid + re-rank, `semantic_search`.
4. Metadata tool + agent loop (LangGraph) with Langfuse tracing.
5. API (SSE) + Next.js UI with inline trace + feedback.
6. Eval harness: ground truth, ladder, judge grid, agent metrics, CI smoke.
7. Monitoring: dual-write, Grafana dashboards.
8. Deploy: Fly bootstrap, auto-deploy pipeline, guardrails, demo polish.

## 13. Data & privacy

Public arXiv data only — CC0 metadata/abstracts in-repo; full text fetched per-deploy,
never redistributed. No IES or customer data anywhere in this project. Secrets live in
a git-ignored `.env` locally and `fly secrets` in production.
