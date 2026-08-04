# 07 — Interface & demo plan

Type: grilling
Status: resolved
Assignee: Jordan Taylor (claimed 2026-08-03, resolved 2026-08-03)
Blocked by: 01

## Question

What does a user (and a hiring manager) actually touch?

- **Interface:** Streamlit-only vs. FastAPI backend + lightweight frontend vs. both —
  rubric needs UI *or* API for 2 pts; portfolio weights say demo-ability matters.
- **Answer UX:** citations back to arXiv, feedback capture (thumbs + comment) feeding
  monitoring — and the visible agent trace, which [01](01-v1-capability-scope.md)
  promoted from nice-to-have to the demo lead: the UI must show the evidence loop's
  tool calls, retrieved evidence, and latency as it runs. Decide how (streamed steps?
  expandable panel?).
- **Demo script:** the 2-minute walkthrough — which 3–4 questions best show the agent
  visibly thinking (per [01](01-v1-capability-scope.md), mix a multi-step synthesis
  question with an analytical/metadata one and a "what's new this week"); does a live
  hosted instance need seeded data and rate limiting?

## Answer

Resolved 2026-08-03 by grilling; every decision confirmed by Jordan.

**Architecture — FastAPI + custom frontend** (Jordan's call over the recommended
FastAPI+Streamlit): FastAPI owns the agent and exposes `POST /chat` (SSE-streaming the
LangGraph event stream: rewritten queries, tool calls + args, evidence, tokens),
`POST /feedback`, `GET /healthz`. Both rubric boxes (UI *and* API) tick, and the
documented streaming API is the integration-ready FDE surface.

**Frontend — Next.js** (Jordan's pick via write-in; supersedes the old roadmap's Nuxt
pointer, which dies when ticket 10 rewrites the README). Ships as a node container in
compose.

**Trace UX — inline, ChatGPT/Claude-style** (Jordan clarified against the recommended
split-view console): the agent's steps stream inline in the chat column as collapsible
activity above the forming answer, then fold into an expandable per-message Trace
block. Citations link to `arxiv.org/abs/{id}`; thumbs + comment per answer dual-write
per [08](08-observability-and-monitoring.md).

**Demo posture — free chat + caps + samples.** Live instance seeded from the pinned
snapshot; suggested-question chips seed the good paths; per-session rate limit + daily
spend cap with hard kill-switch (mechanics in [09](09-cloud-deploy-and-cicd.md)).
Demo script = 4 questions, each showing a different loop behavior in the Trace:
multi-step synthesis ("how do the main RAG faithfulness-eval approaches differ?"),
analytical ("papers per month on agent evaluation in 2026?"), freshness ("what's new in
RAG eval this week?"), and a full-text deep-dive.
