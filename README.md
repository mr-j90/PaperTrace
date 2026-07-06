# llm-zoomcamp-project-capstone

## HR Data Q&A  -- A Hybrid RAG System for Tabular HR Data

A retrieval-augmented question-answering system over tabular HR data (ADP-style
employee/roster exports). Roster-RAG accepts a CSV through a guided **workflow**,
cleans and indexes it into a durable knowledge base, then lets you **chat** with
the data — routing each question to the right engine: semantic search for fuzzy,
descriptive questions and structured SQL for counts, filters, and aggregates.

This is my LLM Zoomcamp capstone: an end-to-end RAG application built and owned by me.

---

## The problem

Most questions you actually ask of HR data are **analytical, not semantic** —
*"How many engineers are in the Houston office?"*, *"What's average tenure by
department?"*, *"Who reports to Jane Smith?"*. These are `GROUP BY` / `WHERE` /
join questions, and naive RAG (chunk rows → embed → cosine similarity) is genuinely
bad at counting and exact-match filtering. Ask "how many engineers" of a vector
store and top-k retrieval hands you a vibe, not a number.

But some HR questions *are* fuzzy and descriptive — *"Tell me about our senior
ICs"*, *"Who has machine-learning experience?"* — and those are where semantic
retrieval shines.

**HR Data Q&A treats this as a routing problem.** A lightweight router classifies
intent and dispatches to one of two tools: a structured-query tool over DuckDB for
analytical questions, and a semantic-search tool over a vector index for descriptive
ones. Both return grounded context that the LLM uses to answer — no ungrounded
guessing, full provenance.

---

## How it works

```
                ┌──────────────── Streamlit UI ────────────────┐
                │   Workflows tab            Chat tab           │
                │   pick profile + upload    ask questions      │
                └──────┬─────────────────────────┬──────────────┘
                       │ ingest()                 │ orch.answer(q)
                       ▼                           ▼
            ┌─────────────────┐         ┌────────────────────────┐
            │ Ingestion       │         │ Orchestrator           │
            │ clean → load    │         │  router → tool calls   │
            │ → index         │         │  → grounded synthesis  │
            └────────┬────────┘         └───────┬────────────────┘
                     │ writes                    │ reads
                     ▼                           ▼
          ┌──────────────────────┐     ┌──────────────────┐
          │ Knowledge base       │     │ Tools            │
          │ (per dataset_id)     │◄────│  structured_query│ → DuckDB
          │  DuckDB + vector idx │     │  semantic_search │ → vector index
          └──────────────────────┘     └──────────────────┘

          every turn → Postgres (route, SQL/chunks, latency, feedback) → dashboard
```

### 1. Workflows (ingestion)
A **workflow** is a named ingestion profile — expected schema, cleaning rules,
which columns become semantic "cards" vs. structured fields, and sample questions.
The user picks a workflow (v1 ships with **ADP HR Roster**), uploads a CSV, and
ingestion cleans it, loads it into a DuckDB table, builds a vector index over the
narrative cards, and writes the whole thing to disk under a `dataset_id`. The UI
holds only that id in session state — chat never re-ingests.

### 2. Chat (retrieval flow)
The orchestrator rewrites the query if needed, lets the LLM choose a tool (this
*is* the router), executes the tool call against the active knowledge base, and
synthesizes a grounded answer with citations. Every answer ships with a
**"How I answered"** trace: route taken, generated SQL or retrieved chunks, and
latency.

### 3. Evaluation
- **Retrieval:** a ground-truth Q&A set scored with hit-rate / MRR, comparing
  keyword (BM25), vector, and hybrid retrieval — the best performer is used.
- **LLM output:** multiple prompt variants scored via LLM-as-a-Judge; SQL path
  also checked with execution accuracy against expected results.

### 4. Monitoring
Every turn and every thumbs up/down is logged to Postgres. A dashboard surfaces
query volume over time, latency (p50/p95), route distribution (SQL vs. semantic),
feedback rate, and retrieval-hit / SQL-error rate.

---

## Tech stack

| Layer            | Choice                                              |
|------------------|-----------------------------------------------------|
| Interface        | Streamlit (Workflows + Chat pages)                  |
| Orchestration    | Python orchestrator with a framework-agnostic tool contract |
| Structured store | DuckDB (read-only query connection)                 |
| Vector store     | DuckDB VSS extension *(or a standalone index)*      |
| LLM              | *(pluggable — OpenAI / Ollama / Groq)*              |
| Monitoring       | Postgres for logs + dashboard                       |
| Packaging        | Docker Compose                                       |
| Data             | Synthetic ADP-style HR data (generator included)    |

---

## Data

The dataset is **synthetic** — generated to mimic the shape of an ADP HR roster
export, with deliberate edge cases baked in (null sentinels, stripped leading
zeros on IDs, currency/percent strings, mixed date formats). This sidesteps any
PII concern and makes the project fully reproducible: run the generator and you
have the exact dataset. See [`data/generate.py`](data/generate.py).

---

## Quickstart

```bash
git clone https://github.com/<you>/roster-rag.git
cd roster-rag
cp .env.example .env          # set your LLM key / endpoint
docker compose up             # brings up app + Postgres + dashboard
# open http://localhost:8501
```

1. Generate the sample data: `python data/generate.py` *(or it ships in `data/`)*
2. **Workflows** tab → pick *ADP HR Roster* → upload the CSV → **Ingest**
3. **Chat** tab → ask away (try the sample questions)

Full setup, including running the evaluation harness and viewing the dashboard,
is in [`docs/setup.md`](docs/setup.md).

---

## Evaluation criteria mapping

*(For reviewers — where each rubric item lives.)*

| Criterion              | Where it's met                                                        |
|------------------------|-----------------------------------------------------------------------|
| Problem description    | This README, "The problem"                                            |
| Retrieval flow         | Knowledge base (DuckDB + vector) + LLM in the orchestrator            |
| Retrieval evaluation   | BM25 vs. vector vs. hybrid, hit-rate / MRR — best used  ·  `eval/`     |
| LLM evaluation         | Multiple prompt variants, LLM-as-Judge + SQL execution accuracy  ·  `eval/` |
| Interface              | Streamlit UI (Workflows + Chat)                                       |
| Ingestion pipeline     | Automated `ingest()` writing a durable per-dataset KB                 |
| Monitoring             | Feedback collected + dashboard with 5 charts                          |
| Containerization       | Everything in `docker-compose.yml`                                    |
| Reproducibility        | Synthetic data generator, pinned versions, step-by-step setup         |
| Best practices         | Hybrid search; (re-ranking; query rewriting)                          |
| Bonus                  | Structured-query (text-to-SQL) tool alongside semantic RAG            |

---

## Roadmap (post-course v2)

The orchestrator depends only on a stable tool contract, so v1 is built to grow:

- **Deepen the structured-query tool:** v1 uses scoped text-to-SQL / templates;
  v2 adds multi-table joins across monthly exports, SQL self-correction on errors,
  and multi-step tool calls.
- **Expose tools as an MCP server** (FastMCP) so the query layer is reusable by
  any MCP client, not welded to this app.
- **Migrate the front end to Nuxt + FastAPI** with streaming responses and live
  tool-call status.
- **Add more workflows** — each is just a new entry in the workflow registry.

---

## Repo layout

```
roster-rag/
├── app/                  # Streamlit UI (workflows + chat pages)
├── core/
│   ├── orchestrator.py   # router + tool loop (framework-agnostic)
│   ├── tools/            # semantic_search, structured_query
│   └── ingest.py         # clean → load → index
├── data/
│   └── generate.py       # synthetic ADP-style data generator
├── eval/                 # retrieval + LLM evaluation harnesses
├── monitoring/           # dashboard + logging
├── docs/                 # setup.md, usage.md
├── docker-compose.yml
└── README.md
```

---

## License

MIT *(or your choice)*
