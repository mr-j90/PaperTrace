# 01 — V1 capability scope

Type: grilling
Status: resolved
Assignee: Jordan Taylor (resolved 2026-08-01)

## Question

What does the assistant actually *do* in v1? Chat Q&A with citations over the corpus is
the rubric floor. Candidates beyond it:

- **Structured/analytical queries over paper metadata** — the Roster-RAG two-tool router
  carried over: "how many RAG-eval papers were published in 2025?", "list agent papers
  from DeepMind this year" (structured store + text-to-SQL/filters alongside semantic
  search).
- **Multi-step agentic retrieval** — search → pick papers → fetch/read → synthesize across
  papers.
- **Fetch-on-demand** — answer about a paper outside the indexed corpus by pulling it live.
- **Per-paper deep-dive mode** — summarize/explain one paper (upload or arXiv id).
- **Digest / recommendations** — "what's new in RAG eval this week?"

Resolve: the v1 capability list, the explicit v2 deferrals, and the one differentiator the
demo leads with. Portfolio weights say agentic depth matters — but every capability must
still be evaluable (ticket 06) and demoable (ticket 07).

Consult findings from [02](02-arxiv-data-access.md) and [03](03-prior-art.md) if resolved.

## Answer

Resolved 2026-08-01 by grilling; every decision below was put to Jordan and confirmed.

**Demo differentiator (locked):** the agent visibly thinking — a PaperQA2-style
**evidence loop** (search → gather evidence → synthesize) over the topical corpus, with
the tool-use **trace** on screen. The shipped eval story remains the *portfolio*
differentiator, carried by the README/CI rather than the live demo.

**V1 capability list:**

1. **Chat Q&A with citations** over the RAG/agents/eval/LLMOps corpus — rubric floor.
2. **Multi-step agentic retrieval** — the evidence loop above, with a visible trace in
   the UI (route, tool calls, retrieved evidence). This is the demo lead.
3. **Analytical/metadata queries** — the Roster-RAG carryover ships, reshaped: the
   structured metadata store (CC0 JSONL from [02](02-arxiv-data-access.md)) is exposed
   as **one tool inside the agent loop** (LLM tool-choice), not a separate top-level
   router. Tool-choice correctness becomes an eval metric (feeds
   [06](06-evaluation-design.md)).
4. **On-demand freshness queries** — "what's new in RAG eval this week?" answered as
   date-filtered metadata queries + synthesis; comes free with capability 3 and is
   listed as supported.
5. **In-corpus single-paper questions** ("explain paper X") ride the normal chat flow —
   no dedicated deep-dive mode or surface.

**Explicit v2 deferrals:**

- Live fetch of out-of-corpus papers (v1 gives a graceful "not indexed" answer; the
  metadata tool can recognize an unindexed ID).
- Paper upload.
- A dedicated per-paper deep-dive surface (structured per-paper summaries).
- Scheduled digests and personalized recommendations.
- (Pre-existing, from the map) MCP server exposure; Nuxt + FastAPI migration.

**Rationale trail:** fetch-on-demand was cut because arXiv's 1 req/3 s limit makes a
live fetch-parse-answer cycle slow and flaky in a 2-minute demo, and an unbounded corpus
has no eval ground truth; deep-dive and digest were cut as *features* because their
useful cores (in-corpus paper questions, "what's new" queries) come free from
capabilities 2–3; the router became an agent tool to keep one architecture and make
routing measurable.
