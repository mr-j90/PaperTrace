"""API plumbing with an injected fake graph — no LLM, no Qdrant server."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from qdrant_client import QdrantClient

import api.main as api_main
from core.agent import build_agent
from core.config import Settings
from core.retrieval import SemanticIndex
from core.tools import make_semantic_search
from tests.test_agent import DIM, LEWIS, fake_embedder, scripted_model


def fake_graph() -> object:
    client = QdrantClient(":memory:")
    index = SemanticIndex(client=client, collection="papers", embed=fake_embedder(), dim=DIM)
    index.ensure_collection()
    index.index_abstracts([LEWIS])
    model = scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "semantic_search", "args": {"query": "rag"}, "id": "c1"}],
            ),
            AIMessage(content="An answer [arxiv:2005.11401]."),
        ]
    )
    return build_agent(model, [make_semantic_search(index, k=1)])


def looping_graph() -> object:
    client = QdrantClient(":memory:")
    index = SemanticIndex(client=client, collection="papers", embed=fake_embedder(), dim=DIM)
    index.ensure_collection()
    index.index_abstracts([LEWIS])
    endless = [
        AIMessage(
            content="",
            tool_calls=[{"name": "semantic_search", "args": {"query": "x"}, "id": f"c{i}"}],
        )
        for i in range(100)
    ]
    return build_agent(scripted_model(endless), [make_semantic_search(index, k=1)])


def test_max_turns_maps_to_504(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "build_graph", lambda settings: looping_graph())
    monkeypatch.setattr(api_main, "load_settings", lambda: Settings())

    with TestClient(api_main.app) as client:
        response = client.post("/chat", json={"question": "never answers"})
        assert response.status_code == 504
        assert "turns" in response.json()["detail"]


def test_healthz_and_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "build_graph", lambda settings: fake_graph())
    monkeypatch.setattr(api_main, "load_settings", lambda: Settings())

    with TestClient(api_main.app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}

        response = client.post("/chat", json={"question": "what is RAG?"})
        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "An answer [arxiv:2005.11401]."
        assert body["citations"] == [
            {
                "arxiv_id": "2005.11401",
                "title": LEWIS["title"],
                "url": "https://arxiv.org/abs/2005.11401",
            }
        ]
