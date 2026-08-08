"""Tracer-bullet plumbing: tool call -> evidence -> cited answer, no network, no models."""

from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from qdrant_client import QdrantClient

from core.agent import MaxTurnsExceeded, build_agent, run_chat
from core.embeddings import Embedder
from core.retrieval import SemanticIndex
from core.tools import make_semantic_search

DIM = 8

LEWIS: dict[str, Any] = {
    "arxiv_id": "2005.11401",
    "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
    "abstract": "We explore RAG models which combine parametric and non-parametric memory.",
    "submitted": "2020-05-22T21:17:29Z",
    "categories": ["cs.CL"],
    "topics": ["rag"],
}
OTHER: dict[str, Any] = {
    "arxiv_id": "2401.99999",
    "title": "An Unrelated Paper",
    "abstract": "Something else entirely.",
    "submitted": "2024-01-05T00:00:00Z",
    "categories": ["cs.AI"],
    "topics": ["agents"],
}


def fake_embedder() -> Embedder:
    """Deterministic vectors: texts mentioning RAG cluster at one corner."""

    def embed(texts: list[str]) -> list[list[float]]:
        return [
            [1.0] + [0.0] * (DIM - 1)
            if ("RAG" in text or "retrieval" in text.lower())
            else [0.0] * (DIM - 1) + [1.0]
            for text in texts
        ]

    return embed


class ToolCallingFakeModel(GenericFakeChatModel):
    """GenericFakeChatModel that accepts bind_tools (scripted responses ignore them)."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return self


def scripted_model(messages: list[AIMessage]) -> BaseChatModel:
    iterator: Iterator[AIMessage | str] = iter(messages)
    return ToolCallingFakeModel(messages=iterator)


@pytest.fixture
def search_tool() -> BaseTool:
    client = QdrantClient(":memory:")
    index = SemanticIndex(client=client, collection="papers", embed=fake_embedder(), dim=DIM)
    index.ensure_collection()
    index.index_abstracts([LEWIS, OTHER])
    return make_semantic_search(index, k=2)


def test_tool_call_to_cited_answer(search_tool: BaseTool) -> None:
    model = scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "semantic_search", "args": {"query": "RAG retrieval"}, "id": "c1"}
                ],
            ),
            AIMessage(
                content="RAG combines parametric and non-parametric memory [arxiv:2005.11401]."
            ),
        ]
    )
    graph = build_agent(model, [search_tool])
    result = run_chat(graph, "what is RAG?", max_turns=12)

    assert "[arxiv:2005.11401]" in result.answer
    assert [c.arxiv_id for c in result.citations] == ["2005.11401"]
    assert result.citations[0].url == "https://arxiv.org/abs/2005.11401"
    assert result.citations[0].title.startswith("Retrieval-Augmented Generation")


def test_ungrounded_citations_are_dropped(search_tool: BaseTool) -> None:
    model = scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "semantic_search", "args": {"query": "RAG retrieval"}, "id": "c1"}
                ],
            ),
            AIMessage(content="Real [arxiv:2005.11401] and invented [arxiv:9999.00001]."),
        ]
    )
    graph = build_agent(model, [search_tool])
    result = run_chat(graph, "what is RAG?", max_turns=12)

    assert [c.arxiv_id for c in result.citations] == ["2005.11401"]


def test_max_turns_cap(search_tool: BaseTool) -> None:
    endless_tool_calls = [
        AIMessage(
            content="",
            tool_calls=[{"name": "semantic_search", "args": {"query": "loop"}, "id": f"c{i}"}],
        )
        for i in range(50)
    ]
    model = scripted_model(endless_tool_calls)
    graph = build_agent(model, [search_tool])

    with pytest.raises(MaxTurnsExceeded):
        run_chat(graph, "never answers", max_turns=6)


def test_semantic_search_ranks_by_meaning(search_tool: BaseTool) -> None:
    import json

    hits = json.loads(search_tool.invoke({"query": "retrieval augmented generation"}))
    assert hits[0]["arxiv_id"] == "2005.11401"
