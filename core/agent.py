"""The evidence loop (SPEC §5): a LangGraph agent that searches, gathers, and synthesizes.

Current scope: one semantic_search tool (hybrid + reranked, per #5), JSON in/out.
The visible trace (SSE streaming) arrives with #7; metadata_query with #6.
"""

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

SYSTEM_PROMPT = """\
You are PaperTrace, a research assistant over arXiv papers on RAG, LLM agents,
LLM evaluation, and LLMOps. The corpus starts at 2020; freshness is bounded by
the latest ingest. Today's date: {today}. Use it to turn relative dates
("this week", "last month") into absolute YYYY-MM-DD filters.

Tools:
- semantic_search — meaning-level search over paper abstracts and full text.
  Use for conceptual questions ("how do X approaches differ?").
- metadata_query — exact counts, groupings, listings, and date-filtered
  queries over paper metadata. Always use it for "how many", "per month",
  "latest", "papers by <author>", and "what's new since <date>" questions —
  never estimate numbers from search results.

Rules:
- Always ground answers in tool results; call a tool before answering and
  rewrite your query if the first results don't cover the question.
- Cite papers inline as [arxiv:<arxiv_id>], e.g. [arxiv:2005.11401]. Counts
  from metadata_query are exact — report them as such.
- If the evidence doesn't answer the question, say so plainly — never invent
  papers, citations, or numbers.
"""

CITATION_PATTERN = re.compile(r"\[arxiv:([^\]\s]+)\]")


@dataclass
class Citation:
    arxiv_id: str
    title: str
    url: str


@dataclass
class ChatResult:
    answer: str
    citations: list[Citation]


class MaxTurnsExceeded(Exception):
    """The evidence loop hit its max-turns cap without producing an answer."""


def build_agent(
    model: BaseChatModel, tools: list[BaseTool], today: str | None = None
) -> CompiledStateGraph[Any]:
    prompt = SYSTEM_PROMPT.format(today=today or date.today().isoformat())
    return create_agent(model, tools, system_prompt=prompt)


def _evidence_titles(messages: list[Any]) -> dict[str, str]:
    """arxiv_id -> title for every paper the tools actually returned this run.

    semantic_search returns a list of evidence items; metadata_query returns a
    dict whose `rows` may be paper listings. Both ground citations.
    """
    titles: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(str(message.content))
        except (json.JSONDecodeError, TypeError):
            continue
        items = payload.get("rows", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and "arxiv_id" in item:
                titles[str(item["arxiv_id"])] = str(item.get("title", ""))
    return titles


def _ground_citations(answer: str, evidence: dict[str, str]) -> list[Citation]:
    cited_ids = list(dict.fromkeys(CITATION_PATTERN.findall(answer)))
    return [
        Citation(arxiv_id=cid, title=evidence[cid], url=f"https://arxiv.org/abs/{cid}")
        for cid in cited_ids
        if cid in evidence  # only citations grounded in evidence actually returned
    ]


async def stream_chat(
    graph: CompiledStateGraph[Any],
    question: str,
    max_turns: int,
    callbacks: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """The Trace as data (SPEC §7): tool calls, evidence, tokens, then the grounded answer.

    Event shapes: {type: tool_call, name, args} · {type: tool_result, name, summary}
    · {type: token, text} · {type: done, answer, citations} · {type: error, detail}.
    """
    tool_payloads: list[str] = []
    answer_parts: list[str] = []
    tool_started: dict[str, float] = {}  # run_id -> monotonic start, for Trace latency
    usage = {"input_tokens": 0, "output_tokens": 0}
    try:
        config: RunnableConfig = {"recursion_limit": 2 * max_turns + 1}
        if callbacks:
            config["callbacks"] = callbacks
        if metadata:
            config["metadata"] = metadata
        async for event in graph.astream_events(
            {"messages": [("user", question)]},
            config=config,
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                text = event["data"]["chunk"].text
                if text:
                    answer_parts.append(text)
                    yield {"type": "token", "text": text}
            elif kind == "on_tool_start":
                answer_parts.clear()  # tokens so far were pre-tool reasoning, not the answer
                tool_started[event["run_id"]] = time.monotonic()
                yield {
                    "type": "tool_call",
                    "name": event["name"],
                    "args": event["data"].get("input", {}),
                }
            elif kind == "on_tool_end":
                output = event["data"].get("output")
                content = output.content if isinstance(output, ToolMessage) else str(output)
                tool_payloads.append(str(content))
                started = tool_started.pop(event["run_id"], None)
                yield {
                    "type": "tool_result",
                    "name": event["name"],
                    "summary": _summarize_tool_payload(str(content)),
                    "ms": round((time.monotonic() - started) * 1000) if started else None,
                }
            elif kind == "on_chat_model_end":
                turn_usage = getattr(event["data"].get("output"), "usage_metadata", None) or {}
                usage["input_tokens"] += int(turn_usage.get("input_tokens", 0))
                usage["output_tokens"] += int(turn_usage.get("output_tokens", 0))
    except GraphRecursionError:
        yield {"type": "error", "detail": f"no answer within {max_turns} turns"}
        return
    except Exception:  # surface mid-stream failures as an event, not a dropped connection
        logging.getLogger(__name__).exception("evidence loop failed mid-stream")
        yield {"type": "error", "detail": "the evidence loop failed — try again"}
        return
    answer = "".join(answer_parts)
    evidence = _evidence_titles([ToolMessage(content=p, tool_call_id="t") for p in tool_payloads])
    citations = _ground_citations(answer, evidence)
    yield {
        "type": "done",
        "answer": answer,
        "citations": [asdict(c) for c in citations],
        "usage": usage,
    }


def _summarize_tool_payload(content: str) -> dict[str, Any]:
    """Compact view of a tool result for the Trace: counts and ids, not full text."""
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"raw": content[:200]}
    if isinstance(payload, list):  # semantic_search evidence
        return {
            "evidence": [
                {"arxiv_id": item.get("arxiv_id"), "title": item.get("title")}
                for item in payload
                if isinstance(item, dict)
            ]
        }
    if isinstance(payload, dict):  # metadata_query result
        summary: dict[str, Any] = {"total": payload.get("total")}
        if payload.get("sql"):
            summary["sql"] = payload["sql"]
        rows = payload.get("rows", [])
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            if "arxiv_id" in rows[0]:
                summary["evidence"] = [
                    {"arxiv_id": r.get("arxiv_id"), "title": r.get("title")} for r in rows
                ]
            else:
                summary["groups"] = rows[:24]
        if payload.get("note") or payload.get("error"):
            summary["note"] = payload.get("note") or payload.get("error")
        return summary
    return {"raw": content[:200]}


def run_chat(graph: CompiledStateGraph[Any], question: str, max_turns: int) -> ChatResult:
    try:
        state = graph.invoke(
            {"messages": [("user", question)]},
            # one model turn = model superstep + tool superstep; +1 for the final answer
            config={"recursion_limit": 2 * max_turns + 1},
        )
    except GraphRecursionError as exc:
        raise MaxTurnsExceeded(f"no answer within {max_turns} turns") from exc

    messages = state["messages"]
    answer = messages[-1].text  # joins multi-block content (e.g. thinking + text) correctly
    return ChatResult(
        answer=answer, citations=_ground_citations(answer, _evidence_titles(messages))
    )
