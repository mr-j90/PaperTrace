"""Evidence-loop plumbing: tool call -> evidence -> cited answer, no network, no models."""

import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from core.agent import MaxTurnsExceeded, build_agent, run_chat
from core.tools import make_semantic_search
from tests.conftest import LEWIS, OTHER, make_index, scripted_model


@pytest.fixture
def search_tool() -> BaseTool:
    index = make_index()
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


def test_semantic_search_scope_arg_via_tool(search_tool: BaseTool) -> None:
    hits = json.loads(search_tool.invoke({"query": "retrieval augmented generation"}))
    assert hits[0]["arxiv_id"] == "2005.11401"
    scoped = json.loads(
        search_tool.invoke({"query": "retrieval augmented generation", "scope": "fulltext"})
    )
    assert scoped == []  # no fulltext chunks indexed in this fixture
