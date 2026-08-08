"""The evidence loop (SPEC §5): a LangGraph agent that searches, gathers, and synthesizes.

Tracer scope: one semantic_search tool, dense retrieval, JSON in/out. The visible
trace (SSE streaming) arrives with #7; metadata_query with #6.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph

SYSTEM_PROMPT = """\
You are PaperTrace, a research assistant over arXiv papers on RAG, LLM agents,
LLM evaluation, and LLMOps.

Rules:
- Always call semantic_search before answering; search again with a rewritten
  query if the first results don't cover the question.
- Ground every claim in the returned evidence and cite papers inline as
  [arxiv:<arxiv_id>], e.g. [arxiv:2005.11401].
- If the evidence doesn't answer the question, say so plainly — never invent
  papers or citations.
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


def build_agent(model: BaseChatModel, tools: list[BaseTool]) -> CompiledStateGraph[Any]:
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT)


def _evidence_titles(messages: list[Any]) -> dict[str, str]:
    """arxiv_id -> title for every paper the tools actually returned this run."""
    titles: dict[str, str] = {}
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                for item in json.loads(str(message.content)):
                    titles[str(item["arxiv_id"])] = str(item.get("title", ""))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
    return titles


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
    evidence = _evidence_titles(messages)
    cited_ids = list(dict.fromkeys(CITATION_PATTERN.findall(answer)))
    citations = [
        Citation(arxiv_id=cid, title=evidence[cid], url=f"https://arxiv.org/abs/{cid}")
        for cid in cited_ids
        if cid in evidence  # only citations grounded in evidence actually returned
    ]
    return ChatResult(answer=answer, citations=citations)
