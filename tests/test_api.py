"""API contract: SSE trace events, grounded final answer, turn ledger, feedback dual-write."""

import json
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


class FakeTurnStore:
    def __init__(self) -> None:
        self.turns: list[Any] = []
        self.feedback: list[tuple[str, str, str | None]] = []

    def write_turn(self, turn: Any) -> None:  # noqa: ANN401
        self.turns.append(turn)

    def set_feedback(self, turn_id: str, thumbs: str, comment: str | None) -> bool:
        self.feedback.append((turn_id, thumbs, comment))
        return True


def wire_fakes(
    monkeypatch: pytest.MonkeyPatch, model_factory: Any = answering_model, **settings: Any
) -> FakeTurnStore:
    store = FakeTurnStore()
    monkeypatch.setattr(api_main, "build_tools", lambda s: fake_tools())
    monkeypatch.setattr(api_main, "init_chat_model", lambda spec: model_factory())
    monkeypatch.setattr(api_main, "build_turnstore", lambda s: store)
    monkeypatch.setattr(api_main, "build_langfuse", lambda: (None, None))
    monkeypatch.setattr(api_main, "load_settings", lambda: Settings(**settings))
    return store


def sse_events(text: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_chat_streams_trace_then_grounded_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    store = wire_fakes(monkeypatch)

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
    assert done["turn_id"]
    assert done["usage"] == {"input_tokens": 0, "output_tokens": 0}  # fake model: no usage

    [turn] = store.turns  # one Postgres row per turn
    assert turn.turn_id == done["turn_id"]
    assert turn.tools_used == ["semantic_search"]
    assert turn.latency_ms >= 0
    assert turn.error is None


def test_chat_stream_emits_error_on_max_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    store = wire_fakes(monkeypatch, looping_model, max_turns=3)

    with (
        TestClient(api_main.app) as client,
        client.stream("POST", "/chat", json={"question": "never answers"}) as response,
    ):
        events = sse_events(response.read().decode())

    assert events[-1]["type"] == "error"
    assert "turns" in events[-1]["detail"]
    [turn] = store.turns  # failed turns are logged too, with the error recorded
    assert turn.error is not None


def test_chat_model_override_selects_allowed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    specs: list[str] = []

    def tracking_init(spec: str) -> object:
        specs.append(spec)
        return answering_model()

    wire_fakes(monkeypatch)
    monkeypatch.setattr(api_main, "init_chat_model", tracking_init)

    with TestClient(api_main.app) as client:
        client.post("/chat", json={"question": "q", "model": "claude-sonnet-5"}).read()
        client.post("/chat", json={"question": "q", "model": "not-a-model"}).read()

    assert specs == ["anthropic:claude-sonnet-5", "anthropic:claude-haiku-4-5"]


def test_feedback_dual_write_updates_turn_row(monkeypatch: pytest.MonkeyPatch) -> None:
    store = wire_fakes(monkeypatch)

    with TestClient(api_main.app) as client:
        response = client.post(
            "/feedback",
            json={
                "question": "q",
                "answer": "a",
                "thumbs": "up",
                "comment": "nice",
                "turn_id": "t123",
            },
        )
        assert response.status_code == 204

    assert store.feedback == [("t123", "up", "nice")]
