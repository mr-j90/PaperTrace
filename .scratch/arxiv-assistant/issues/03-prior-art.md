# 03 — Research: prior-art survey of paper assistants

Type: research
Status: resolved

## Question

What arXiv / research-paper assistants already exist, what do they do well, and where is
the differentiation room for a portfolio-grade capstone scoped to RAG / agents / eval /
LLMOps literature?

Survey (primary sources — their repos, sites, docs): arxiv-sanity(-lite), talk2arxiv,
paper-qa (FutureHouse), Elicit, Emergent Mind, alphaXiv, Semantic Scholar's AI features /
API, Zeta Alpha, Hugging Face Daily Papers, Ai2 ScholarQA — plus anything comparable found
along the way.

For each: what it does, its retrieval/agent approach where public, and its gaps. Conclude
with (a) differentiation opportunities for this capstone and (b) design ideas worth
stealing, with attribution.

## Answer

Full findings (16 tools, per-claim citations): `.scratch/arxiv-assistant/research/03-prior-art.md`
on branch **`research/prior-art`** (commit `279a158`).

Executive summary from the research agent:

The paper-assistant landscape splits into three layers that almost never coexist in one
open tool: discovery/curation ([arxiv-sanity-lite](https://github.com/karpathy/arxiv-sanity-lite),
[Scholar Inbox](https://arxiv.org/abs/2504.08385), [HF Daily Papers](https://huggingface.co/papers),
[gpt_paper_assistant](https://github.com/tatsu-lab/gpt_paper_assistant)), agentic search
([Ai2 Paper Finder](https://allenai.org/blog/paper-finder), [Undermind](https://www.undermind.ai/),
[Semantic Scholar](https://www.semanticscholar.org/product/api)), and cited QA/synthesis
([PaperQA2](https://github.com/Future-House/paper-qa), [Ai2 ScholarQA](https://allenai.org/blog/ai2-scholarqa),
[OpenScholar](https://github.com/AkariAsai/OpenScholar), [Elicit](https://elicit.com/)).
The products that combine them ([Emergent Mind](https://www.emergentmind.com/about),
[alphaXiv](https://www.alphaxiv.org/)) are proprietary and opaque about internals.

**Strongest differentiation angles:**
1. **Topical depth** — nobody serves RAG/agents/evals/LLMOps literature specifically;
   Zeta Alpha proved the "focused AI-research navigator" thesis in 2020 then
   [pivoted to enterprise](https://www.zeta-alpha.com/), vacating the niche; a small
   corpus affords full-text parsing and rich per-paper metadata giants can't do
   per-document.
2. **A shipped eval story** — no OSS demo surveyed includes retrieval/answer evals; a
   golden QA set + retrieval metrics + LLM-judge grading in CI (miniature ScholarQABench,
   Elicit-style public eval report) is a near-empty field.
3. **Freshness fused with QA plus real ops** — daily ingestion feeding the same index the
   agent answers from, with cost/latency/feedback monitoring none of the open peers have.

**Top mechanics to steal:** PaperQA2's agentic search→gather-evidence→answer loop with
LLM-rescored contextual summaries; ScholarQA's quote-extraction-first generation and
schema-then-values comparison tables; OpenScholar's ship-the-benchmark discipline;
gpt_paper_assistant's LLM interest-scoring on a GitHub Actions cron with published daily
cost; talk2arxiv's GROBID section-aware chunking; free Semantic Scholar API enrichment
(citations, SPECTER2, TLDRs); alphaXiv's MCP-server exposure.
