"""API contract: SSE trace events, grounded final answer, feedback capture."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import api.main as api_main
from core.config import Settings
from core.tools import make_semantic_search
from tests.conftest import LEWIS, make_index, scripted_model


def fake_tools() -> list[object]:
    index = make_index()
    index.index_abstracts([LEWIS])
    return [make_semantic_search(index, k=1)]


def answering_model() -> object:
    return scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "semantic_search", "args": {"query": "rag"}, "id": "c1"}],
            ),
            AIMessage(content="An answer [arxiv:2005.11401]."),
        ]
    )


def looping_model() -> object:
    endless = [
        AIMessage(
            content="",
            tool_calls=[{"name": "semantic_search", "args": {"query": "x"}, "id": f"c{i}"}],
        )
        for i in range(100)
    ]
    return scripted_model(endless)


def sse_events(text: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_chat_streams_trace_then_grounded_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "build_tools", lambda settings: fake_tools())
    monkeypatch.setattr(api_main, "init_chat_model", lambda spec: answering_model())
    monkeypatch.setattr(api_main, "load_settings", lambda: Settings())

    with TestClient(api_main.app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}

        with client.stream("POST", "/chat", json={"question": "what is RAG?"}) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = sse_events(response.read().decode())

    kinds = [e["type"] for e in events]
    call = next(e for e in events if e["type"] == "tool_call")
    result = next(e for e in events if e["type"] == "tool_result")
    done = events[-1]

    assert kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("done")
    assert "token" in kinds  # answer streamed incrementally
    assert call["name"] == "semantic_search" and call["args"] == {"query": "rag"}
    assert result["summary"]["evidence"][0]["arxiv_id"] == "2005.11401"
    assert done["type"] == "done"
    assert done["answer"] == "An answer [arxiv:2005.11401]."
    assert done["citations"] == [
        {
            "arxiv_id": "2005.11401",
            "title": LEWIS["title"],
            "url": "https://arxiv.org/abs/2005.11401",
        }
    ]


def test_chat_stream_emits_error_on_max_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "build_tools", lambda settings: fake_tools())
    monkeypatch.setattr(api_main, "init_chat_model", lambda spec: looping_model())
    monkeypatch.setattr(api_main, "load_settings", lambda: Settings(max_turns=3))

    with (
        TestClient(api_main.app) as client,
        client.stream("POST", "/chat", json={"question": "never answers"}) as response,
    ):
        events = sse_events(response.read().decode())

    assert events[-1]["type"] == "error"
    assert "turns" in events[-1]["detail"]


def test_chat_model_override_selects_allowed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    specs: list[str] = []

    def tracking_init(spec: str) -> object:
        specs.append(spec)
        return answering_model()

    monkeypatch.setattr(api_main, "build_tools", lambda settings: fake_tools())
    monkeypatch.setattr(api_main, "init_chat_model", tracking_init)
    monkeypatch.setattr(api_main, "load_settings", lambda: Settings())

    with TestClient(api_main.app) as client:
        client.post("/chat", json={"question": "q", "model": "claude-sonnet-5"}).read()
        client.post("/chat", json={"question": "q", "model": "not-a-model"}).read()

    assert specs == ["anthropic:claude-sonnet-5", "anthropic:claude-haiku-4-5"]


def test_feedback_appends_jsonl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api_main, "build_tools", lambda settings: fake_tools())
    monkeypatch.setattr(api_main, "init_chat_model", lambda spec: answering_model())
    monkeypatch.setattr(api_main, "load_settings", lambda: Settings())
    monkeypatch.setattr(api_main, "FEEDBACK_PATH", tmp_path / "feedback.jsonl")

    with TestClient(api_main.app) as client:
        response = client.post(
            "/feedback",
            json={"question": "q", "answer": "a", "thumbs": "up", "comment": "nice"},
        )
        assert response.status_code == 204

    [line] = (tmp_path / "feedback.jsonl").read_text().splitlines()
    record = json.loads(line)
    assert record["thumbs"] == "up" and record["comment"] == "nice" and record["ts"]
