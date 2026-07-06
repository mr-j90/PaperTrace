# LLM Zoomcamp Capstone — Initial Spec

> **Status:** draft v0.1 — a starting point to iterate on, not a contract.
> Anything marked **TBD** or in _Open decisions_ is up for grabs.

## 1. Problem

A **Retrieval-Augmented Generation (RAG) assistant** that answers natural-language
questions over a focused knowledge base, with citations back to the source docs.

- **Domain (default, confirm):** Q&A assistant over a technical documentation corpus
  (e.g. a single open-source tool's docs). Chosen because the data is easy to ingest,
  the answers are verifiable, and it exercises every rubric criterion.
- **Why RAG:** the corpus changes and is too large / too specific to rely on the
  model's parametric memory; users want grounded, cited answers.

_See Open decisions #1 to lock the domain._

## 2. Rubric alignment

The DataTalksClub peer-review rubric drives the scope. Each criterion maps to a
concrete deliverable so we don't lose easy points:

| Rubric criterion        | How we satisfy it |
|-------------------------|-------------------|
| Problem description     | This doc + README |
| Retrieval flow          | Vector store + LLM, wired end-to-end |
| Retrieval evaluation    | Compare ≥2 retrieval approaches; report hit-rate / MRR |
| LLM evaluation          | Compare ≥2 prompts/models; LLM-as-judge via LangSmith |
| Interface               | Streamlit UI (+ optional FastAPI endpoint) |
| Ingestion pipeline      | Scripted, repeatable load into the vector store |
| Monitoring              | User feedback capture **+ Grafana dashboard (5+ charts)** |
| Containerization        | `docker-compose` for the full stack |
| Reproducibility         | Pinned deps, seeded data, documented run steps |
| Best practices (bonus)  | Hybrid search, re-ranking, query rewriting |
| Cloud deployment (bonus)| TBD |

> **Note on tooling:** LangSmith covers tracing + online/offline LLM eval, but the
> rubric's *Monitoring* criterion wants a feedback dashboard — so we still use
> **Postgres + Grafana** for that. LangSmith and Grafana are complementary here.

## 3. Architecture

```
              ┌────────────┐   feedback    ┌───────────┐
   user ───►  │ Streamlit  │ ────────────► │ Postgres  │ ──► Grafana (dashboard)
              │    UI      │               └───────────┘
              └─────┬──────┘
                    │ query
                    ▼
              ┌────────────┐   traces/eval  ┌────────────┐
              │ RAG core   │ ─────────────► │ LangSmith  │
              │ (LangChain)│                └────────────┘
              └─────┬──────┘
        retrieve    │        generate
      ┌─────────────┴───┐        │
      ▼                 ▼        ▼
 ┌─────────┐      ┌──────────┐  ┌──────────┐
 │ Qdrant  │      │ re-ranker│  │ LLM API  │
 │ (vectors)│     └──────────┘  │ (Claude) │
 └─────────┘                    └──────────┘
      ▲
      │ ingest (scripted)
 ┌──────────┐
 │ raw docs │
 └──────────┘
```

## 4. Tech stack (proposed)

| Layer          | Choice (default)              | Notes / alternatives |
|----------------|-------------------------------|----------------------|
| Language       | Python 3.12 + `uv`            | |
| RAG framework  | LangChain                     | so LangSmith auto-instruments traces |
| Observability  | **LangSmith**                 | tracing + eval datasets + LLM-as-judge |
| LLM            | Claude (Anthropic API)        | Haiku for dev, Sonnet for quality; local Ollama optional for free dev |
| Embeddings     | `sentence-transformers` (local, free) | swap to a hosted embedder if needed |
| Vector store   | Qdrant                        | supports hybrid (dense + sparse) search |
| Re-ranker      | cross-encoder (local)         | for the best-practices bonus |
| Interface      | Streamlit                     | + optional FastAPI for a clean API |
| Feedback store | Postgres                      | thumbs up/down + comments |
| Dashboard      | Grafana                       | ≥5 charts over Postgres |
| Packaging      | Docker + docker-compose       | one-command bring-up |

## 5. Proposed repo layout

```
.
├── SPEC.md                  # this file
├── README.md                # run instructions (reproducibility)
├── docker-compose.yml
├── pyproject.toml           # uv-managed deps
├── ingest/                  # load raw docs -> chunks -> Qdrant
├── rag/                     # retrieval + generation core (LangChain)
├── eval/                    # retrieval eval + LangSmith eval scripts
├── app/                     # Streamlit UI (+ optional FastAPI)
├── monitoring/              # Postgres schema + Grafana dashboards (as code)
└── data/                    # raw + processed corpus, ground-truth Q&A set
```

## 6. Milestones (iterate in this order)

1. **Skeleton** — repo layout, `uv` env, docker-compose stub, LangSmith project + API key wired.
2. **Ingestion** — chunk + embed the corpus into Qdrant; one script, re-runnable.
3. **RAG core** — retrieve → prompt → generate, with traces flowing to LangSmith.
4. **Interface** — Streamlit chat UI over the RAG core.
5. **Evaluation** — ground-truth Q&A set; retrieval metrics (hit-rate/MRR) + LangSmith LLM-as-judge; compare ≥2 approaches each.
6. **Monitoring** — feedback → Postgres; Grafana dashboard with 5+ charts.
7. **Best practices** — hybrid search, re-ranking, query rewriting; re-run eval to show the lift.
8. **Polish** — README, reproducibility check, (bonus) cloud deploy.

## 7. Data & privacy

- LangSmith and the Claude API are **third-party hosted services** — traces and
  prompts leave the machine. Keep this project to **public / synthetic data only**;
  no IES or customer data. (Any business use would need IT/procurement sign-off first.)
- Secrets (`LANGSMITH_API_KEY`, `ANTHROPIC_API_KEY`) go in a git-ignored `.env`,
  never committed.

## 8. Open decisions

1. **Knowledge-base domain** — confirm the docs corpus (default: one tool's docs).
   Alternatives: course FAQ, personal-finance/tax FAQ, a specific product manual.
2. **LLM provider** — Claude by default; switch to OpenAI/Ollama if preferred.
3. **UI vs API scope** — Streamlit only, or also expose FastAPI?
4. **Cloud deployment** — attempt the bonus, and if so, where?
