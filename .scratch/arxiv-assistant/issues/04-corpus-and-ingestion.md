# 04 — Corpus boundary & ingestion pipeline

Type: grilling
Status: resolved
Assignee: Jordan Taylor (resolved 2026-08-01)
Blocked by: 01, 02 (both closed)

## Question

Where exactly does the knowledge base start and stop, and how does it get built?

- **Granularity:** abstracts-only, full text, or tiered (abstracts for all + full text for
  a curated subset)?
- **Size & range:** how many papers, what date range, which categories/keywords (informed
  by ticket 02's feasibility numbers)?
- **Snapshot vs. live:** frozen snapshot for reproducibility, scheduled refresh, or both
  (pinned snapshot + optional update job)? How does a reviewer reproduce the exact corpus?
- **Orchestration tool:** the rubric awards 2 pts only for ingestion automated with a
  dedicated tool — dlt, Prefect, Airflow, or Kestra. Which one, and what does the pipeline
  DAG look like (fetch → clean → chunk → embed → index)?

## Answer

Resolved 2026-08-01 by grilling; every decision confirmed by Jordan.

**Granularity — tiered.** Abstracts + CC0 metadata for **all** papers, shipped in the
repo as JSONL (the metadata tool and freshness queries from
[01](01-v1-capability-scope.md) run over the full set). Full text is fetched at ingest
(never redistributed, per [02](02-arxiv-data-access.md)'s licensing verdict) for a
curated subset only.

**Full-text tier — hybrid, ~2,000 papers.** Top ~1,000 by Semantic Scholar citation
count + everything from the trailing ~6 months. The budget is a config parameter
(`FULLTEXT_BUDGET` or similar) so a reviewer can reproduce with a tiny tier in minutes;
the full tier is ≈100 min at the 1 req/3 s polite rate. New papers enter the tier
automatically via the recency rule; Semantic Scholar enrichment was already a steal
recommendation from [03](03-prior-art.md).

**Boundary — the verified 8-phrase union, 2020→now, ~12,526 papers.** RAG + LLM-agent +
LLM-eval + LLMOps phrase queries over abstracts, exactly as verified in
[02](02-arxiv-data-access.md); query definitions committed to the repo as the corpus's
source of truth. 2020 start keeps the founding papers (Lewis et al. RAG is 2020).
Rejected: trimming to 2022+ (loses seminal targets) and the ~70k broad-LLM superset
(dilutes topical depth).

**Freshness — both snapshot and refresh.** A pinned snapshot (committed ID list +
metadata JSONL at a snapshot date) is the reproducible corpus that evals and reviewers
build against. The live instance runs a **daily** delta refresh re-running the pinned
queries over `submittedDate:[lastRun TO now]`, flagging withdrawn versions. Daily beats
weekly for the ops story at trivial cost (tens of papers/day).

**Orchestrator — Prefect** (Jordan's call over the recommended Airflow; Python-native,
light in docker-compose — server + worker — and satisfies the rubric's
dedicated-tool requirement). **One parameterized flow, two modes** (snapshot ingest /
daily delta):

`fetch metadata → normalize & dedupe (flag withdrawals) → load metadata store →
select full-text tier → fetch & parse full text (HTML-first) → chunk → embed → index →
validate/report`

Chunking and embedding *choices* are explicitly [05](05-retrieval-agent-architecture.md)'s;
this ticket fixes the stages and the tool, not their internals.
