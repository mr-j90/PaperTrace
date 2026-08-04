# 05 — Retrieval & agent architecture

Type: grilling
Status: resolved
Assignee: Jordan Taylor (claimed 2026-08-01, resolved 2026-08-03)
Blocked by: 01, 04 (both closed)

## Question

How does a question become a grounded answer?

- **Retrieval:** chunking strategy for papers — the corpus is tiered per
  [04](04-corpus-and-ingestion.md) (abstracts+metadata for all ~12.5k, full-text for a
  hybrid ~2k tier), so decide how the two layers chunk and whether they share one index;
  embedding model (local sentence-transformers vs. hosted), vector store (Qdrant?
  DuckDB VSS? other), hybrid search / re-ranking / query rewriting (each is a rubric
  best-practice point — decide which ship in v1). Choices must slot into the Prefect
  flow's chunk → embed → index stages fixed by 04.
- **Agent/orchestration:** locked by [01](01-v1-capability-scope.md): a PaperQA2-style
  evidence loop is the demo lead, and metadata queries ship as one tool inside it via
  LLM tool-choice (no separate router/classifier). Still open here: the loop's concrete
  design (tool set, stopping criteria, evidence rescoring) and the framework —
  hand-rolled framework-agnostic tool loop (the Roster-RAG stance) vs. LangChain/LangGraph
  vs. an agent SDK — weigh portfolio signal vs. build cost vs. observability integration.
- **Metadata tool backend:** what the structured store is (SQLite? DuckDB?) and whether
  the tool interface is text-to-SQL or parameterized filters — must keep tool-choice and
  query execution cheaply evaluable (ticket [06](06-evaluation-design.md)).
- **LLM provider & tiering:** which provider/models for dev vs. demo, and what the
  pluggability story is.

## Answer

Resolved 2026-08-03 by grilling; every decision below was put to Jordan and confirmed.

**Framework — LangGraph** (Jordan's call over the recommended hand-rolled loop). A
`StateGraph` agent node + `ToolNode` with a conditional edge implements the evidence
loop; stopping = the model returns no tool calls, guarded by a max-turns cap. Two
welcome side effects recorded: LangGraph event streaming makes the visible trace
([07](07-interface-and-demo.md)) nearly free, and LangSmith auto-instrumentation becomes
the low-friction observability path — [08](08-observability-and-monitoring.md) still
decides, but the tilt is noted there.

**Vector store & embeddings — Qdrant + local models.** Qdrant in docker-compose;
dense = local sentence-transformers (bge-small-en-v1.5 class), sparse = fastembed
BM25/SPLADE, hybrid fusion native to Qdrant. Embeddings stay local so the chat LLM is
the only paid API; reviewers reproduce free.

**Index shape — one layered collection.** Two point kinds in a single Qdrant
collection: an *abstract card* per paper (title + abstract + venue/date as text, all
~12.5k) and *section chunks* (~512 tokens, split on the HTML-first parse's section
structure per [02](02-arxiv-data-access.md), title + section heading prepended) for the
~2k full-text tier. A `layer` payload field discriminates. One tool —
`semantic_search(query, scope=abstracts|fulltext|all, default all)` — searches hybrid,
fuses, dedups to max 2–3 chunks per paper.

**Best practices — all three ship** (hybrid search; cross-encoder re-ranking with a
local bge-reranker-class model rescoring the fused top-30 to top-k, doubling as
PaperQA2-style evidence rescoring; query rewriting as the agent's explicit, logged,
evaluable query-formulation step). Note: the multi-select answer also included the
contradictory "none beyond hybrid" option; discarded as a stray tick and flagged to
Jordan in-session with no objection.

**Metadata tool — DuckDB + parameterized filters.** Prefect's load stage produces a
DuckDB file from the CC0 metadata JSONL; the agent calls a typed
`metadata_query(filters, group_by, aggregate, sort, limit)` and the tool builds the SQL.
Eval = exact-match on tool args + execution accuracy ([06](06-evaluation-design.md)).
Text-to-SQL is explicitly the v2 deepening, not v1.

**LLM — Claude default, pluggable.** Haiku for dev/cheap eval runs, Sonnet for the demo
and final eval numbers; provider+model set via LangChain `init_chat_model` config, with
the README documenting one-env-change swaps to OpenAI/Groq/Ollama so reviewers without
an Anthropic key aren't blocked.

**Agent tool set (fixed by the above):** `semantic_search` + `metadata_query` — nothing
else in v1.
