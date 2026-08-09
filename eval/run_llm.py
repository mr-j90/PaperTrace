"""LLM-output eval (SPEC §6): 2 prompts x 2 models, LLM-as-judge.

Cells: {citation-strict, baseline} x {haiku, sonnet} on a sample of the cited-Q&A +
synthesis sets. Judge (strongest model) scores faithfulness-to-evidence, citation
correctness, and completeness on 1-5; same-family-judge caveat documented in the
report; spot-check the judgments file by hand.

Usage:
    uv run python -m eval.run_llm                 # 20 retrieval + 10 synthesis (~$5)
    uv run python -m eval.run_llm --sample 4      # tiny smoke of the grid
"""

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from api.main import build_tools
from core.agent import SYSTEM_PROMPT, build_agent, stream_chat
from core.config import load_settings

MODELS = {"haiku": "anthropic:claude-haiku-4-5", "sonnet": "anthropic:claude-sonnet-5"}
JUDGE_MODEL = "anthropic:claude-sonnet-5"

BASELINE_PROMPT = """\
You are PaperTrace, a research assistant over arXiv papers on RAG, LLM agents,
LLM evaluation, and LLMOps. Today's date: {today}.
Use your tools to find relevant papers, then answer the question helpfully.
"""

PROMPTS = {"citation_strict": SYSTEM_PROMPT, "baseline": BASELINE_PROMPT}

JUDGE_PROMPT = """\
You are grading an AI research assistant's answer. Score each dimension 1-5
(5 = excellent). Respond with ONLY a JSON object like
{{"faithfulness": n, "citation_correctness": n, "completeness": n}}.

- faithfulness: is every claim supported by the evidence below?
- citation_correctness: are inline [arxiv:id] citations present and pointing at
  evidence that actually supports the adjacent claim?
- completeness: does the answer address the whole question?

Question: {question}

Evidence the assistant retrieved:
{evidence}

Assistant's answer:
{answer}"""


async def answer(graph: Any, q: str, max_turns: int) -> tuple[str, str]:
    """(answer, evidence_digest) for one question."""
    evidence_bits: list[str] = []
    final = ""
    async for event in stream_chat(graph, q, max_turns):
        if event["type"] == "tool_result":
            for e in event.get("summary", {}).get("evidence", []) or []:
                evidence_bits.append(f"[arxiv:{e.get('arxiv_id')}] {e.get('title')}")
        elif event["type"] == "done":
            final = str(event.get("answer", ""))
    return final, "\n".join(dict.fromkeys(evidence_bits)) or "(none)"


def judge_scores(judge: Any, question: str, evidence: str, ans: str) -> dict[str, int] | None:
    raw = judge.invoke(
        JUDGE_PROMPT.format(question=question, evidence=evidence[:4000], answer=ans[:4000])
    ).text
    match = re.search(r"\{[^}]+\}", raw)
    if not match:
        return None
    try:
        parsed = json.loads(match.group())
        return {k: int(parsed[k]) for k in ("faithfulness", "citation_correctness", "completeness")}
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


async def main_async() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=None, help="total questions (default 30)")
    parser.add_argument("--out", type=Path, default=Path("eval/results/llm.json"))
    args = parser.parse_args()

    retrieval = [
        json.loads(line)
        for line in Path("eval/ground_truth/retrieval.jsonl").read_text().splitlines()
    ]
    synthesis = [
        json.loads(line)
        for line in Path("eval/ground_truth/synthesis.jsonl").read_text().splitlines()
    ]
    questions = [r["q"] for r in retrieval[:20]] + [s["q"] for s in synthesis[:10]]
    if args.sample:
        questions = questions[: args.sample]

    settings = load_settings()
    tools = build_tools(settings)
    judge = init_chat_model(JUDGE_MODEL)

    cells: dict[str, Any] = {}
    judgments: list[dict[str, Any]] = []
    for prompt_name, prompt in PROMPTS.items():
        for model_name, spec in MODELS.items():
            cell = f"{prompt_name}/{model_name}"
            print(f"  cell {cell} ({len(questions)} questions)...")
            graph = build_agent(init_chat_model(spec), tools, system_prompt=prompt)
            scores: list[dict[str, int]] = []
            for i, q in enumerate(questions, 1):
                ans, evidence = await answer(graph, q, settings.max_turns)
                graded = judge_scores(judge, q, evidence, ans)
                if graded:
                    scores.append(graded)
                    judgments.append({"cell": cell, "q": q, "answer": ans[:600], "scores": graded})
                if i % 10 == 0:
                    print(f"    {i}/{len(questions)}")
            n = max(len(scores), 1)
            cells[cell] = {
                "n": len(scores),
                "faithfulness": round(sum(s["faithfulness"] for s in scores) / n, 3),
                "citation_correctness": round(
                    sum(s["citation_correctness"] for s in scores) / n, 3
                ),
                "completeness": round(sum(s["completeness"] for s in scores) / n, 3),
            }
            cells[cell]["mean"] = round(
                (
                    cells[cell]["faithfulness"]
                    + cells[cell]["citation_correctness"]
                    + cells[cell]["completeness"]
                )
                / 3,
                3,
            )
            print(f"    -> {cells[cell]}")

    best = max(cells, key=lambda c: cells[c]["mean"])
    payload = {
        "ran": datetime.now(UTC).isoformat(timespec="seconds"),
        "judge": JUDGE_MODEL,
        "judge_caveat": "judge shares a model family with graded answers;"
        " spot-check judgments.jsonl",
        "cells": cells,
        "best_cell": best,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    with (args.out.parent / "judgments.jsonl").open("w", encoding="utf-8") as fh:
        for row in judgments:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"cells": cells, "best_cell": best}, indent=2))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
