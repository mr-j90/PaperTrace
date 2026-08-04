# 08 — Observability & monitoring stack

Type: grilling
Status: resolved
Assignee: Jordan Taylor (claimed 2026-08-03, resolved 2026-08-03)
Blocked by: 01

## Question

What is traced, logged, and dashboarded — and with what tools?

- **Tracing/LLM-eval platform:** LangSmith vs. self-hosted (Langfuse, Arize Phoenix) —
  weigh the LLMOps portfolio story, self-hostability inside docker-compose, and framework
  fit. [05](05-retrieval-agent-architecture.md) locked **LangGraph**, so LangSmith
  auto-instrumentation is the low-friction path — but Langfuse/Phoenix both ship
  LangGraph integrations and keep the stack self-hosted; still a live decision.
- **Per-turn logging schema:** route, retrieved context, tokens/cost, latency, feedback —
  stored where (Postgres?)?
- **Dashboard:** rubric wants feedback collected **and** a dashboard with 5+ charts —
  Grafana over Postgres vs. the tracing platform's built-ins (do built-ins count?); which
  5+ charts.

## Answer

Resolved 2026-08-03 by grilling; Langfuse was Jordan's proposal, confirmed with the
footprint trade-off made explicit.

**Tracing platform — Langfuse, self-hosted.** First-class LangGraph/LangChain callback
integration; traces, token/cost tracking, and feedback scores in one OSS platform;
"self-hosted the whole LLMOps stack" is the infra/portfolio signal. Acknowledged cost:
Langfuse v3's compose stack is ~5 services (web, worker, Postgres, ClickHouse, Redis,
MinIO) — run via Langfuse's official compose file as an include/profile so the core app
compose stays lean. (LangSmith and Phoenix were weighed and declined: hosted-login
traces and weaker cost/feedback features respectively.)

**Rubric monitoring — Postgres + Grafana beside Langfuse.** Every turn dual-writes:
a Langfuse trace (spans, prompts, evidence, cost — the deep-dive layer) and a flat
Postgres row (`ts, route, latency_ms, tokens, cost, feedback, error`). Feedback
(thumbs + comment) is deliberately written twice — Postgres row and Langfuse score —
documented as such. Grafana ships dashboard-as-code with ≥6 charts: query volume,
latency p50/p95, route split, feedback rate, cost/day, tool-error rate. This satisfies
the rubric's "feedback collected + dashboard with 5+ charts" in the form reviewers
expect, with no login required to see it.
