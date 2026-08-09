"""Retrieval eval (SPEC §6): the 4-way ladder on the pinned ground truth.

sparse -> dense -> hybrid -> hybrid+rerank, scored by hit-rate@k and MRR against
each question's source paper. Local models only — no paid API.

Usage:
    uv run python -m eval.run_retrieval               # full 140-question set
    uv run python -m eval.run_retrieval --limit 30
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.config import load_settings
from core.retrieval import SemanticIndex

MODES = ["sparse", "dense", "hybrid", "hybrid_rerank"]
K = 8


def evaluate(index: SemanticIndex, questions: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    hits = 0
    reciprocal_ranks: list[float] = []
    for i, item in enumerate(questions, 1):
        results = index.search(item["q"], K, scope="abstracts", mode=mode)  # type: ignore[arg-type]
        ids = [e.arxiv_id for e in results]
        if item["source_arxiv_id"] in ids:
            hits += 1
            reciprocal_ranks.append(1 / (ids.index(item["source_arxiv_id"]) + 1))
        else:
            reciprocal_ranks.append(0.0)
        if i % 35 == 0:
            print(f"    {mode}: {i}/{len(questions)}")
    n = len(questions)
    return {
        "mode": mode,
        "n": n,
        f"hit_rate@{K}": round(hits / n, 4),
        "mrr": round(sum(reciprocal_ranks) / n, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("eval/results/retrieval.json"))
    args = parser.parse_args()

    questions = [
        json.loads(line)
        for line in Path("eval/ground_truth/retrieval.jsonl").read_text().splitlines()
    ]
    if args.limit:
        questions = questions[: args.limit]

    index = SemanticIndex.from_settings(load_settings())
    ladder = []
    for mode in MODES:
        print(f"  running {mode}...")
        ladder.append(evaluate(index, questions, mode))

    # hit-rate leads: all top-k evidence reaches the agent, so recall is binding; MRR breaks ties
    best = max(ladder, key=lambda r: (r[f"hit_rate@{K}"], r["mrr"]))
    payload = {
        "ran": datetime.now(UTC).isoformat(timespec="seconds"),
        "k": K,
        "ladder": ladder,
        "best_mode": best["mode"],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
