# Wayfinder map: arXiv Assistant (LLM Zoomcamp capstone)

Label: wayfinder:map
**Status: CLOSED 2026-08-03 — destination reached.** SPEC.md v1 + README are locked;
all 10 tickets resolved; no fog remains. Next step is off-map: `/to-tickets` on SPEC.md.
*(Post-close 2026-08-03: project named **PaperTrace**.)*

## Destination

A locked **SPEC.md v1** (+ rewritten README) for an arXiv literature assistant scoped to
RAG / agents / evaluation / LLMOps papers — every build-blocking decision made
(capabilities, corpus & ingestion, retrieval/agent architecture, evaluation, interface,
monitoring, cloud), mapped to the rubric, ready to hand to `/to-tickets` and start coding
without another decision.

## Notes

- **Why this exists:** LLM Zoomcamp capstone that doubles as a portfolio piece speaking
  directly to Forward-Deployed-Engineer / AI-engineering roles.
- **Time box (locked 2026-07-31):** self-paced, quality first — ambition bounded by taste,
  not calendar.
- **Portfolio weights (locked 2026-07-31, all four):** agentic depth · eval & LLMOps rigor ·
  demo-ability (live instance + demo script) · cloud & infra story.
- **Rubric** (fetched 2026-07-31 from
  [DataTalksClub/llm-zoomcamp/project.md](https://github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md)):
  10 core criteria × 2 pts — problem description, retrieval flow, retrieval eval, LLM eval,
  interface, ingestion pipeline, monitoring (feedback **and** dashboard with 5+ charts),
  containerization (everything in docker-compose), reproducibility — plus best practices
  (hybrid search, re-ranking, query rewriting; 1 pt each) and bonuses (cloud deploy 2 pts,
  exceptional work up to 3 pts).
  ⚠️ **Ingestion needs a dedicated orchestration tool (Kestra / dlt / Airflow / Prefect) for
  2 pts — a plain script scores 1.** Course FAQ data is prohibited; arXiv is fine.
- **Project-requirements conformance (added 2026-08-01):** match the whole
  [project.md](https://github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md) page as
  closely as possible, not just the scoring rubric. In particular the
  [Datasets section](https://github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md#datasets):
  the corpus should be a sanctioned kind — arXiv papers fit "Articles: index and answer
  questions from one or multiple articles" (datasets need not be Q&A-form; course FAQ
  prohibited, as above) — and the problem statement wants an end-to-end LLM app that is
  "a RAG application, an agent application, or a combination of both" (this project is
  the combination, per [01 — V1 capability scope](issues/01-v1-capability-scope.md)).
  Every spec decision should be checkable against this page;
  [10 — Assemble the locked spec](issues/10-assemble-locked-spec.md) maps spec sections
  to it explicitly.
- **Skills:** resolve grilling tickets with `/grilling` + `/domain-modeling`; research
  tickets via `/research` subagents. One ticket per session (research tickets excepted).
- **Data/privacy standing rule:** public arXiv data only; no IES or customer data; secrets
  in a git-ignored `.env` (org policy).
- **Prior artifacts:** `SPEC.md` (generic docs-RAG draft v0.1) and `README.md` (Roster-RAG
  HR concept) predate this map; both are superseded and get rewritten by the final ticket.
  The Roster-RAG two-tool router idea carried over in reshaped form — metadata queries
  ship as a tool inside the agent loop, per
  [01 — V1 capability scope](issues/01-v1-capability-scope.md).

## Decisions so far

<!-- one line per closed ticket: gist + link -->

- [02 — Research: arXiv data access & corpus feasibility](issues/02-arxiv-data-access.md) —
  corpus is laptop-scale (~12.5k papers for the topical union, 2020→now, verified);
  acquire via the arXiv API with pinned queries (fetch script + ID list + metadata JSONL
  in repo); metadata/abstracts are CC0-redistributable, full text is fetch-at-ingest only;
  1 req/3 s rate limit. Full findings on branch `research/arxiv-data-access`.
- [03 — Research: prior-art survey of paper assistants](issues/03-prior-art.md) — niche is
  open (no one serves RAG/agents/eval/LLMOps literature specifically); differentiate on
  topical depth + a shipped eval story + freshness-with-ops; steal PaperQA2's
  evidence-gathering loop, GROBID chunking, Semantic Scholar enrichment. Full findings on
  branch `research/prior-art`.
- [01 — V1 capability scope](issues/01-v1-capability-scope.md) — demo leads with the
  agentic evidence loop + visible trace; v1 = cited Q&A + agent loop + metadata queries
  as an agent tool (incl. free "what's new" queries); no live fetch, upload, deep-dive
  surface, or digests (all v2); eval story is the README-level differentiator.
- [04 — Corpus boundary & ingestion pipeline](issues/04-corpus-and-ingestion.md) — tiered
  corpus: abstracts+metadata for all ~12.5k (8-phrase union, 2020→now, in-repo JSONL) +
  full text for a hybrid ~2k tier (top-cited + trailing 6 months, budget configurable);
  pinned snapshot for evals/reviewers + daily delta refresh on the live instance; one
  parameterized **Prefect** flow in docker-compose runs both modes.
- [05 — Retrieval & agent architecture](issues/05-retrieval-agent-architecture.md) —
  **LangGraph** evidence loop with exactly two tools: `semantic_search` over one layered
  Qdrant collection (abstract cards ×12.5k + section chunks for the ~2k tier; local
  bge-small dense + fastembed sparse, hybrid fusion) and `metadata_query` (typed
  parameterized filters over DuckDB; text-to-SQL is v2). All three best practices ship
  (hybrid, cross-encoder re-rank, explicit query rewriting). LLM: Claude default
  (Haiku dev / Sonnet demo), pluggable via `init_chat_model`.
- [06 — Evaluation design](issues/06-evaluation-design.md) — ~200 LLM-generated,
  hand-checked ground-truth questions (4 JSONL files, every record tool-labeled) pinned
  to the snapshot; 4-way retrieval ladder (BM25→dense→hybrid→+rerank, hit-rate/MRR);
  2 prompts × 2 models LLM-judge grid + execution accuracy; agent metrics (routing,
  tool-arg match); plain-Python `eval/` harness, committed results + report.md, free CI
  smoke slice on push.
- [08 — Observability & monitoring stack](issues/08-observability-and-monitoring.md) —
  **Langfuse self-hosted** for traces/cost (v3 compose stack accepted, run as an
  include/profile) + **Postgres + Grafana** for the rubric's monitoring: every turn
  dual-writes a Langfuse trace and a flat Postgres row; feedback written to both;
  Grafana dashboard-as-code with ≥6 charts.
- [07 — Interface & demo plan](issues/07-interface-and-demo.md) — **FastAPI + Next.js**:
  FastAPI owns the agent (`POST /chat` SSE-streams the LangGraph events, `/feedback`,
  `/healthz`); Next.js chat UI with **inline ChatGPT/Claude-style trace** (streamed
  steps collapsing into a per-message Trace block); live instance = free chat +
  suggested-question chips + rate limit + daily spend cap; 4-question demo script
  (synthesis / analytical / freshness / full-text deep-dive).
- [09 — Cloud deployment & CI/CD](issues/09-cloud-deploy-and-cicd.md) — **Fly.io, fully
  self-hosted** (~11 apps incl. the Langfuse stack; stack parity with local compose was
  the deciding principle); estate-as-code via committed fly.tomls + idempotent
  bootstrap.sh (Fly's Terraform provider is unmaintained — documented); GitHub Actions
  with auto-deploy on green main; **$2/day LLM cap** + rate limit + cached chip answers;
  ~$40–80/mo infra accepted.
- [10 — Assemble the locked spec](issues/10-assemble-locked-spec.md) — **SPEC.md v1 +
  README rewritten** from all nine resolutions; full project.md conformance table with
  the exceptional-work case named; exit check passed — implementation can start without
  reopening a decision. The destination.

## Not yet specified

*(empty — all fog has graduated or been ruled out of scope)*

<!-- graduated 2026-08-03 after 05: best-practices lift → implementation fixed by 05,
     eval delta demonstrated via 06's comparisons; cost controls → provider locked by 05,
     guardrails/caching/tiering live in 09 (live-instance hygiene) + 08 (cost logging).
     graduated 2026-08-03 after 09: "exceptional work" bonus angle → named explicitly in
     10's rubric-mapping duty; portfolio packaging → ruled out of scope (post-build). -->


## Out of scope

- **Portfolio packaging beyond the app** (demo video, blog write-up, repo presentation
  polish) — ruled out 2026-08-03: it's post-build work beyond this map's destination
  (the locked spec); returns as its own effort once the assistant exists.
- **Roster-RAG (HR Data Q&A) as the capstone** — superseded by this effort; the router
  concept may be reused inside the assistant, but the HR project itself is off this route
  (its README lives in git history).
- **Post-course v2 features** from the old README — MCP server exposure, Nuxt + FastAPI
  migration — explicitly deferred beyond the capstone.
- **DataTalksClub course FAQ as knowledge base** — prohibited by the rubric.
