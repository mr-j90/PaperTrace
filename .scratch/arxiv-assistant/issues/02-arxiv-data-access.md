# 02 — Research: arXiv data access & corpus feasibility

Type: research
Status: resolved

## Question

What are the viable ways to acquire — and keep updated — the RAG / agents / eval / LLMOps
slice of arXiv, and what constraints do they impose?

1. **Acquisition options** for a topical slice: arXiv API search vs. OAI-PMH harvesting
   vs. the Kaggle arXiv metadata snapshot vs. S3 bulk data. Pros/cons for a reproducible
   capstone.
2. **Filtering strategy:** which categories (cs.CL, cs.AI, cs.LG, cs.IR, cs.SE, …) plus
   keyword/query filtering; can the API do keyword search well enough; rough corpus-size
   estimate for this scope (e.g. papers matching RAG/agents/eval/LLMOps themes, 2020→now).
3. **Full text:** PDF download etiquette, LaTeX source availability, arXiv's HTML/ar5iv
   rendering coverage; licensing — can a processed dataset ship in the repo, or must the
   repo ship the fetch script?
4. **Rate limits & ToS:** polite-use rules (request delay, bursts, bulk endpoints).
5. **Update mechanics:** reliably getting "new papers since X" (API `sortBy=submittedDate`,
   OAI-PMH `from`/`until`).

Cite primary sources (arXiv API docs, OAI-PMH docs, bulk-data docs, Kaggle dataset page,
arXiv ToS) for every claim.

## Answer

Full findings (per-claim citations): `.scratch/arxiv-assistant/research/02-arxiv-data-access.md`
on branch **`research/arxiv-data-access`** (commit `aad0ba7`).

Executive summary from the research agent:

- **Corpus size (verified 2026-07-31 against arXiv's own search):** the 8-phrase topical
  union (RAG variants + LLM-agent variants + LLM-eval variants + LLMOps), abstracts,
  submitted 2020→now = **12,526 papers**; per-topic slices: RAG 6,722, agents 4,740,
  eval 1,992; broad-LLM superset ("large language model", CS abstracts, 2020+) ≈ 70,555.
  So the capstone corpus is ~10⁴ — laptop-scale.
- **Recommended acquisition path:** the arXiv API (`export.arxiv.org/api/query`, no key
  needed) with category ∩ keyword-phrase queries over a pinned `submittedDate` window;
  commit the fetch script, query definitions, and resulting ID list + metadata JSONL to
  the repo. Kaggle's official snapshot (1.67 GB zip, weekly, CC0) is the fallback; S3 bulk
  (~9.2 TB, requester-pays) is disproportionate.
- **Licensing verdict:** all metadata + abstracts are **CC0 — freely redistributable in
  the repo**; full text is **not** (default arXiv license bars serving e-prints from your
  own servers), so ship the fetch script and pull PDFs/HTML per-reviewer at ingest time.
  HTML-first parsing works: native `arxiv.org/html/{id}` for post-Dec-2023 TeX
  submissions, ar5iv for older.
- **Rate limits:** 1 request / 3 s, single connection, across all machines (API ToU);
  empirically confirmed — bursting earns a sticky HTTP 429. API caps: 30,000
  results/query, ≤2,000 per call. No indiscriminate crawling of arxiv.org.
- **Updates:** re-run the same queries with `submittedDate:[lastRun TO now]` (+ `id_list`
  re-fetch for revisions); OAI-PMH (`from=` last harvest, day granularity,
  `deletedRecord=persistent`) only if the project outgrows keyword scoping — its
  datestamps track record changes, not submission dates. Withdrawals never delete a
  paper; they appear as a new "withdrawn" version to flag/drop.
