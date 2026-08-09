"""Agent-level eval (SPEC §6): routing accuracy, tool-arg match, execution accuracy.

Runs the real agent over every ground-truth question and scores:
- routing: first tool called == expected_tool
- tool args (analytical/freshness): expected keys exactly match the called args
- execution accuracy: the metadata tool's returned total == expected_total

Usage:
    uv run python -m eval.run_agent            # all sets, default model (~$0.50)
    uv run python -m eval.run_agent --limit 5  # per set
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from api.main import build_tools
from core.agent import build_agent, stream_chat
from core.config import load_settings

SETS = ["retrieval", "synthesis", "analytical", "freshness"]


async def run_question(
    graph: Any, q: str, max_turns: int
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """(tool_names_in_order, tool_calls, tool_results) for one question."""
    names: list[str] = []
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    async for event in stream_chat(graph, q, max_turns):
        if event["type"] == "tool_call":
            names.append(str(event["name"]))
            calls.append(event)
        elif event["type"] == "tool_result":
            results.append(event)
    return names, calls, results


def args_match(expected: dict[str, Any], calls: list[dict[str, Any]]) -> bool:
    """Expected keys must appear with exactly these values in some metadata_query call."""
    for call in calls:
        if call["name"] != "metadata_query":
            continue
        actual = call.get("args", {})
        if all(actual.get(key) == value for key, value in expected.items()):
            return True
    return False


def execution_match(expected_total: int, results: list[dict[str, Any]]) -> bool:
    return any(
        r["name"] == "metadata_query" and r.get("summary", {}).get("total") == expected_total
        for r in results
    )


async def main_async() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="questions per set")
    parser.add_argument("--out", type=Path, default=Path("eval/results/agent.json"))
    args = parser.parse_args()

    settings = load_settings()
    graph = build_agent(init_chat_model(settings.chat_model), build_tools(settings))

    per_set: dict[str, Any] = {}
    routing_ok = routing_total = 0
    arg_ok = arg_total = exec_ok = exec_total = 0

    for name in SETS:
        rows = [
            json.loads(line)
            for line in Path(f"eval/ground_truth/{name}.jsonl").read_text().splitlines()
        ]
        if args.limit:
            rows = rows[: args.limit]
        set_routing = 0
        for i, item in enumerate(rows, 1):
            tools, calls, results = await run_question(graph, item["q"], settings.max_turns)
            routed = bool(tools) and tools[0] == item["expected_tool"]
            set_routing += routed
            routing_ok += routed
            routing_total += 1
            if "expected_tool_args" in item:
                arg_total += 1
                arg_ok += args_match(item["expected_tool_args"], calls)
            if item.get("expected_total") is not None:
                exec_total += 1
                exec_ok += execution_match(item["expected_total"], results)
            if i % 20 == 0:
                print(f"    {name}: {i}/{len(rows)}")
        per_set[name] = {"n": len(rows), "routing_accuracy": round(set_routing / len(rows), 4)}
        print(f"  {name}: routing {per_set[name]['routing_accuracy']}")

    payload = {
        "ran": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": settings.chat_model,
        "per_set": per_set,
        "routing_accuracy": round(routing_ok / routing_total, 4),
        "tool_arg_match": round(arg_ok / arg_total, 4) if arg_total else None,
        "execution_accuracy": round(exec_ok / exec_total, 4) if exec_total else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
