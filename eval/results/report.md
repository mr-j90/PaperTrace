# PaperTrace eval report

Generated 2026-08-09.

Ground truth: {'retrieval': 140, 'synthesis': 25, 'analytical': 25, 'freshness': 10} · generated 2026-08-09 against the snapshot ending 2026-08-01 · hand-check: {'status': 'passed', 'by': 'Jordan Taylor', 'date': '2026-08-09', 'sample': '6 retrieval + 3 synthesis reviewed in-session'}.

## Retrieval ladder (n=140, k=8)

| mode | hit-rate@8 | MRR |
|---|---|---|
| sparse | 0.8643 | 0.7395 |
| dense | 0.7214 | 0.5518 |
| hybrid | 0.8571 | 0.7538 |
| hybrid_rerank **(shipped)** | 0.8929 | 0.7491 |

## Agent metrics (anthropic:claude-haiku-4-5)

- routing accuracy: **0.995** (retrieval 0.9929, synthesis 1.0, analytical 1.0, freshness 1.0)
- tool-arg exact match: **0.7429**
- execution accuracy: **0.8**

## LLM grid (judge: anthropic:claude-sonnet-5)

| cell | faithfulness | citations | completeness | mean |
|---|---|---|---|---|
| citation_strict/haiku | 2.8 | 2.767 | 3.533 | 3.033 |
| citation_strict/sonnet **(shipped)** | 2.933 | 2.9 | 3.567 | 3.133 |
| baseline/haiku | 2.3 | 2.3 | 3.333 | 2.644 |
| baseline/sonnet | 2.8 | 2.867 | 3.633 | 3.1 |

> judge shares a model family with graded answers; spot-check judgments.jsonl

