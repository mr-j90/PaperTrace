# PaperTrace

An agentic RAG assistant (formerly "arXiv Assistant") that answers questions over the
RAG / agents / evaluation / LLMOps slice of arXiv, with citations. This glossary is the project's ubiquitous
language; decisions live in `.scratch/arxiv-assistant/` and (eventually) SPEC.md.

## Language

### Corpus

**Corpus**:
The set of papers matched by the pinned topical queries (RAG, LLM agents, LLM
evaluation, LLMOps phrases; 2020→now, ~12.5k papers).
_Avoid_: dataset, knowledge base

**Full-text tier**:
The curated subset of the corpus (top-cited plus recent, ~2k papers) whose full text is
fetched and indexed; all other papers are represented by abstract and metadata only.

**Pinned snapshot**:
The corpus frozen at a recorded date — the committed paper-ID list and metadata.
Evaluations and reviewer reproduction run against it.

**Delta refresh**:
The scheduled re-run of the pinned queries that adds papers submitted since the last
run to the live instance's corpus.
_Avoid_: re-ingest, sync

### Retrieval units

**Abstract card**:
The per-paper searchable unit: title, abstract, and key metadata as one text. Every
corpus paper has exactly one.

**Section chunk**:
A section-level passage of a full-text-tier paper, carrying its paper title and section
heading. Only full-text-tier papers have them.
_Avoid_: document, fragment

**Evidence**:
The reranked set of abstract cards and section chunks an answer is grounded in and
cites.
_Avoid_: context, sources (in code and UI copy)

### Agent

**Evidence loop**:
The agent's cycle of formulating searches, gathering evidence, and synthesizing a cited
answer — the demo's centerpiece.
_Avoid_: pipeline, chain

**Semantic search**:
The agent tool that retrieves evidence by meaning across abstract cards and section
chunks (optionally scoped to one kind).

**Metadata query**:
The agent tool that answers analytical questions (counts, filters, groupings, "what's
new since X") over paper metadata via typed parameters.
_Avoid_: structured query, SQL tool, text-to-SQL (that's the deferred v2 deepening)

**Freshness query**:
A question about recent papers ("what's new in RAG eval this week?"), answered as a
date-filtered metadata query plus synthesis.

**Trace**:
The user-visible record of one evidence loop run: tool calls, evidence, and latency.
_Avoid_: "How I answered" panel, log
