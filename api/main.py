"""PaperTrace API (SPEC §7): SSE chat streaming the Trace, feedback capture, health."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from core.agent import build_agent, stream_chat
from core.config import Settings, load_settings
from core.metadata import MetadataStore
from core.retrieval import SemanticIndex
from core.tools import make_metadata_query, make_semantic_search

# UI-selectable models; anything else falls back to the env-configured default.
CHAT_MODELS = {
    "claude-haiku-4-5": "anthropic:claude-haiku-4-5",
    "claude-sonnet-5": "anthropic:claude-sonnet-5",
    "claude-opus-5": "anthropic:claude-opus-5",
}


class ChatRequest(BaseModel):
    question: str
    model: str | None = None


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    thumbs: Literal["up", "down"]
    comment: str | None = None


def build_tools(settings: Settings) -> list[Any]:
    index = SemanticIndex.from_settings(settings)
    store = MetadataStore(Path(settings.duckdb_path))
    return [make_semantic_search(index, settings.search_k), make_metadata_query(store)]


def resolve_graph(app: FastAPI, model_id: str | None) -> Any:
    """One compiled agent graph per chat model, built on first use; tools are shared."""
    settings: Settings = app.state.settings
    spec = CHAT_MODELS.get(model_id or "", settings.chat_model)
    graphs: dict[str, Any] = app.state.graphs
    if spec not in graphs:
        graphs[spec] = build_agent(init_chat_model(spec), app.state.tools)
    return graphs[spec]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Provider SDKs read credentials from the process env; pydantic-settings only
    # loads its own PAPERTRACE_* fields, so surface .env for local runs too.
    load_dotenv()
    # NOTE (#11): building the tools loads local models synchronously — first boot
    # downloads ~1.2GB (reranker) before /healthz serves. Deploy health checks
    # need generous start periods or a warmed model cache volume.
    settings = load_settings()
    app.state.settings = settings
    app.state.tools = build_tools(settings)
    app.state.graphs = {}
    yield


app = FastAPI(title="PaperTrace", lifespan=lifespan)

FEEDBACK_PATH = Path("data/feedback.jsonl")  # interim sink; #8 dual-writes Postgres+Langfuse


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Stream the evidence loop as Server-Sent Events; final event carries the
    grounded answer + citations. Event types: tool_call, tool_result, token,
    done, error."""
    settings: Settings = app.state.settings
    graph = resolve_graph(app, request.model)

    async def events() -> AsyncIterator[str]:
        async for event in stream_chat(graph, request.question, settings.max_turns):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/feedback", status_code=204)
def feedback(request: FeedbackRequest) -> None:
    record = {
        "ts": datetime.now(UTC).isoformat(),
        **request.model_dump(),
    }
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
