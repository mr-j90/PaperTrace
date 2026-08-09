"""PaperTrace API (SPEC §7/§8): SSE chat streaming the Trace, dual-write monitoring, health."""

import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import Any, Literal

import anyio
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain.chat_models import init_chat_model
from pydantic import BaseModel
from starlette.background import BackgroundTask

from core.agent import build_agent, stream_chat
from core.config import Settings, load_settings
from core.metadata import MetadataStore
from core.retrieval import SemanticIndex
from core.tools import make_metadata_query, make_semantic_search
from core.turnlog import Turn, TurnStore

logger = logging.getLogger(__name__)

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
    turn_id: str | None = None


def build_tools(settings: Settings) -> list[Any]:
    index = SemanticIndex.from_settings(settings)
    store = MetadataStore(Path(settings.duckdb_path))
    return [make_semantic_search(index, settings.search_k), make_metadata_query(store)]


def resolve_graph(app: FastAPI, model_id: str | None) -> tuple[Any, str]:
    """One compiled agent graph per chat model, built on first use; tools are shared."""
    settings: Settings = app.state.settings
    spec = CHAT_MODELS.get(model_id or "", settings.chat_model)
    graphs: dict[str, Any] = app.state.graphs
    if spec not in graphs:
        graphs[spec] = build_agent(init_chat_model(spec), app.state.tools)
    return graphs[spec], spec


def build_turnstore(settings: Settings) -> TurnStore:
    store = TurnStore(settings.postgres_dsn)
    store.ensure_schema()
    return store


def build_langfuse() -> tuple[Any | None, Any | None]:
    """(callback_handler, client) when LANGFUSE_* env is configured; (None, None) otherwise."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return None, None
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(), get_client()
    except Exception:  # tracing must never take the chat path down
        logger.exception("langfuse configured but unusable — tracing disabled")
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
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
    app.state.turnstore = build_turnstore(settings)
    app.state.langfuse_handler, app.state.langfuse = build_langfuse()
    yield


app = FastAPI(title="PaperTrace", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Stream the evidence loop as Server-Sent Events; the final `done` event carries
    the grounded answer, citations, usage, and the turn_id feedback refers to."""
    settings: Settings = app.state.settings
    graph, model_spec = resolve_graph(app, request.model)
    turn_id = uuid.uuid4().hex
    started = time.monotonic()
    # shared with finalize(): the turn row is written by a BackgroundTask so it
    # lands even when the client disconnects mid-stream (generator cancelled)
    state: dict[str, Any] = {
        "tools": [],
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "error": None,
        "completed": False,
    }

    async def events() -> AsyncIterator[str]:
        callbacks = [app.state.langfuse_handler] if app.state.langfuse_handler else []
        metadata = {"langfuse_tags": ["papertrace"]}

        # An enclosing span pins the Langfuse trace id to our turn_id, so feedback
        # scores attach to the same trace the LangGraph run lands in.
        span = (
            app.state.langfuse.start_as_current_observation(
                name="papertrace-turn", trace_context={"trace_id": turn_id}
            )
            if callbacks and app.state.langfuse
            else nullcontext()
        )
        with span:
            async for event in stream_chat(
                graph, request.question, settings.max_turns, callbacks=callbacks, metadata=metadata
            ):
                if event["type"] == "tool_call":
                    state["tools"].append(str(event["name"]))
                elif event["type"] == "error":
                    state["error"] = str(event["detail"])
                elif event["type"] == "done":
                    state["usage"] = event.get("usage", state["usage"])
                    state["completed"] = True
                    event = {**event, "turn_id": turn_id}
                yield f"data: {json.dumps(event)}\n\n"

    def finalize() -> None:  # sync: Starlette runs it in the threadpool
        error = state["error"]
        if error is None and not state["completed"]:
            error = "client disconnected"
        app.state.turnstore.write_turn(
            Turn(
                turn_id=turn_id,
                question=request.question,
                model=model_spec,
                tools_used=sorted(set(state["tools"])),
                latency_ms=round((time.monotonic() - started) * 1000),
                input_tokens=int(state["usage"].get("input_tokens", 0)),
                output_tokens=int(state["usage"].get("output_tokens", 0)),
                error=error,
            )
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(finalize),
    )


@app.post("/feedback", status_code=204)
async def feedback(request: FeedbackRequest) -> None:
    """Dual-write (SPEC §8): Postgres row update + Langfuse score, keyed by turn_id."""
    if not request.turn_id:
        logger.warning("feedback without turn_id — dropped (client predates turn ledger?)")
        return
    store: TurnStore = app.state.turnstore
    matched = await anyio.to_thread.run_sync(
        store.set_feedback, request.turn_id, request.thumbs, request.comment
    )
    if not matched:
        logger.warning("feedback for unknown turn %s — skipping Langfuse score", request.turn_id)
        return
    if app.state.langfuse:
        try:
            app.state.langfuse.create_score(
                name="user-feedback",
                trace_id=request.turn_id,
                value=1 if request.thumbs == "up" else 0,
                comment=request.comment,
            )
            await anyio.to_thread.run_sync(app.state.langfuse.flush)
        except Exception:  # scores are best-effort; the Postgres row is the record
            logger.exception("langfuse score failed for turn %s", request.turn_id)
