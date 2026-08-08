"""The evidence loop (SPEC §5): a LangGraph agent that searches, gathers, and synthesizes.

Current scope: one semantic_search tool (hybrid + reranked, per #5), JSON in/out.
The visible trace (SSE streaming) arrives with #7; metadata_query with #6.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage
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
