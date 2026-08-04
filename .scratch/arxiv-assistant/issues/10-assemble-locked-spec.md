# 10 — Assemble the locked spec (SPEC.md v1 + README rewrite)

Type: task
Status: resolved
Assignee: Jordan Taylor (claimed 2026-08-03, resolved 2026-08-03)
Blocked by: 04, 05, 06, 07, 08, 09

## Question

Fold every resolved decision into a locked **SPEC.md v1** and a rewritten **README.md**
for the arXiv assistant — this is the destination.

- SPEC.md: problem, capabilities, architecture diagram, corpus & ingestion, eval design,
  monitoring, deployment, rubric-mapping table, explicit v2 deferrals. The mapping table
  covers the full [project.md](https://github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md)
  requirements (incl. the Datasets-section fit and the end-to-end RAG+agent framing),
  not just the scored rubric rows — see the conformance note on the map. Name the
  **"exceptional work" (+3) case** explicitly in that table (graduated from the map's
  fog): the candidates the map built are the shipped eval story (4-way ladder + judge
  grid + agent metrics in CI), the inline agent trace as product surface, and the
  fully self-hosted LLMOps stack with parity from laptop to Fly.
- README.md: replaces the Roster-RAG concept (which stays in git history); portfolio-grade
  framing for FDE / AI-engineering readers.
- Exit check: could implementation start tomorrow without making a single new decision?
  If yes, close the map and hand off to `/to-tickets`.

## Answer

Resolved 2026-08-03. **SPEC.md v1** and the **README rewrite** are committed to the
working tree, assembled from all nine resolved tickets; every spec section links its
decision ticket, and the conformance table covers the full project.md requirements
(Datasets fit, RAG+agent framing, scored rubric, best practices, cloud, and a named
"exceptional work" case: the shipped CI-gated eval story, the inline trace as product
surface, and laptop→Fly stack parity).

**Exit check — passed.** Corpus, capabilities, framework, stores, models, index shape,
eval design, interface, observability, deployment, and budget are all decided;
remaining unknowns (chunk overlap %, judge prompt text, exact Grafana queries) are
implementation details, not decisions. Implementation can start without reopening
anything.

The old Roster-RAG README is superseded (lives in git history). Hand-off: run
`/to-tickets` against SPEC.md to slice the build (suggested order in SPEC §12).
