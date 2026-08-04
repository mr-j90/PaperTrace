# 06 — Evaluation design

Type: grilling
Status: resolved
Assignee: Jordan Taylor (claimed 2026-08-03, resolved 2026-08-03)
Blocked by: 01, 04

## Question

How is the system judged, with what ground truth?

- **Ground-truth set:** how is the Q&A set built over papers (LLM-generated from
  abstracts/sections then hand-checked? how many questions? question types matching the
  v1 capabilities locked in [01](01-v1-capability-scope.md) — cited Q&A, multi-step
  synthesis, analytical/metadata questions, and "what's new since X" freshness queries)?
- **Retrieval eval:** which ≥2 approaches are compared (BM25 vs. vector vs. hybrid vs.
  +rerank), on hit-rate / MRR — and the best one demonstrably used (rubric wording).
- **LLM eval:** which ≥2 prompt/model variants, judged how (LLM-as-judge rubric; execution
  accuracy for any structured-query path)?
- **Agent-level eval:** agentic features ship per [01](01-v1-capability-scope.md), so
  this layer is committed: tool-choice correctness (metadata tool vs. semantic search)
  and execution accuracy on the structured-query path — the portfolio-differentiating
  layer of the eval story.
- **Where it lives:** eval harness layout, dataset versioning, and how results land in the
  README/spec. Per [04](04-corpus-and-ingestion.md), evals run against the pinned corpus
  snapshot (committed ID list + metadata JSONL), so the ground-truth set can pin to the
  snapshot date.

## Answer

Resolved 2026-08-03 by grilling; every decision confirmed by Jordan.

**Ground truth — LLM-generated from the pinned snapshot, hand-checked, ~200 questions**
in four JSONL files under `eval/ground_truth/`: retrieval ×140 (`q, source_arxiv_id,
layer`), synthesis ×25 (multi-paper, `expected_paper_ids`), analytical ×25
(`expected_tool_args, expected_rows`), freshness ×10 (`date_window,
expected_tool_args`). Every record carries an `expected_tool` label, which doubles as
the routing-accuracy set.

**Retrieval eval — the 4-way ladder** on the 140-question set, hit-rate@k + MRR:
sparse-only (BM25) → dense-only (bge) → hybrid fusion → hybrid + cross-encoder re-rank.
Each rung isolates one design decision; the winner ships as the default config. The
table evidences the hybrid-search and re-ranking best-practice points. (A 5th
rewriting-off ablation was declined — the query-rewriting point is claimed via the
agent's explicit, logged rewrite step, not an ablation.)

**LLM eval — 2 prompts × 2 models, LLM-as-judge.** Citation-strict prompt (every claim
must cite evidence) vs. looser baseline, across Haiku and Sonnet, on the cited-Q&A +
synthesis sets. Judge scores faithfulness-to-evidence, citation correctness, and
completeness on a 1–5 rubric using the strongest available model; the same-family-judge
bias caveat is documented and ~20 judgments are hand spot-checked. The best cell ships;
the grid also evidences the Haiku/Sonnet tiering from
[05](05-retrieval-agent-architecture.md). Analytical/freshness paths additionally score
**execution accuracy** (exact expected rows).

**Agent-level metrics** (run by `eval/run_agent.py`): routing accuracy from
`expected_tool` labels, tool-arg exact match, execution accuracy.

**Harness — plain Python, platform-agnostic, CI smoke.** `eval/` package: runners
(`run_retrieval.py`, `run_llm.py`, `run_agent.py`), `results/` with committed JSON + a
generated `report.md` the README links to as the eval story. Full runs are manual
(paid API); CI runs a free smoke slice on every push (~30 retrieval questions with
local models + tool-arg exact-match) and fails on regression — feeds
[09](09-cloud-deploy-and-cicd.md)'s CI design. If
[08](08-observability-and-monitoring.md) picks a tracing platform, harness results may
be mirrored there as a bonus layer, never a dependency.
