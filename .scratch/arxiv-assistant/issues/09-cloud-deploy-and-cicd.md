# 09 — Cloud deployment & CI/CD

Type: grilling
Status: resolved
Assignee: Jordan Taylor (claimed 2026-08-03, resolved 2026-08-03)
Blocked by: 05, 07

## Question

Where does the live instance run, and how does it ship?

- **Target:** small VM (docker-compose as-is) vs. managed container service vs. PaaS —
  weigh the cloud-bonus 2 pts, the FDE infra story, and monthly cost ceiling. Note the
  footprint fixed by [08](08-observability-and-monitoring.md): app + Qdrant + Prefect +
  Postgres + Grafana + the Langfuse v3 stack (~5 services) — instance sizing must
  accommodate ClickHouse/Redis/MinIO, or the deploy profile trims Langfuse to
  dev/local-only (that choice belongs here).
- **IaC:** Terraform (or similar) worth the lift, or documented manual setup?
- **CI/CD:** what runs on push — lint, tests, image build, deploy are open; the eval
  smoke slice is already fixed by [06](06-evaluation-design.md) (free ~30-question
  retrieval subset + tool-arg exact-match, fails on regression).
- **Live-instance hygiene:** secrets handling, API-cost guardrails (budget caps, response
  caching, model tiering — provider locked to Claude-default/pluggable by
  [05](05-retrieval-agent-architecture.md)), seeded corpus for visitors.

## Answer

Resolved 2026-08-03 by grilling; every decision confirmed by Jordan.

**Deploy target — Fly.io, fully self-hosted** (Jordan's call, chosen over the
recommended Fly+Langfuse-Cloud hybrid and the single-VM path). Rationale: stack parity —
the exact stack a user brings up locally with docker-compose is what runs in
production, with no managed-SaaS dependency; ticket
[08](08-observability-and-monitoring.md)'s self-hosted story holds end-to-end. Accepted
price, on the record: ~11 Fly apps, five of them the Langfuse v3 stack with
stateful-on-volumes fiddliness (ClickHouse, MinIO, Redis). Cloud bonus: 2 pts.

**Estate-as-code + CI/CD — fly.tomls, bootstrap, auto-deploy.** Committed `fly.toml`
per app under `deploy/fly/` plus an idempotent `bootstrap.sh` (flyctl: apps, volumes,
secrets, private networking) — the whole estate re-creatable from the repo; that is the
IaC story, and the unmaintained Fly Terraform provider is the documented reason there's
no Terraform. GitHub Actions: PRs run ruff + mypy + unit tests + the free eval smoke
slice (per [06](06-evaluation-design.md)); merge to main builds images and
flyctl-deploys changed apps automatically, concurrency-guarded. Secrets: `fly secrets`
in prod, git-ignored `.env` locally.

**Cost guardrails — $2/day LLM cap.** Per-turn cost tallied in Postgres; hard-stop with
a friendly "demo budget spent" message at the cap; per-session rate limiting;
suggested-question chips serve cached answers (repeat clicks cost $0). Fly infra
baseline ~$40–80/mo accepted, with scale-to-zero on stateless apps pulling it down.
