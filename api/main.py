"""PaperTrace API (SPEC §7). Tracer scope: JSON POST /chat + healthz; SSE arrives with #7."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from core.agent import MaxTurnsExceeded, build_agent, run_chat
from core.config import Settings, load_settings
from core.retrieval import SemanticIndex
from core.tools import make_semantic_search


class ChatRequest(BaseModel):
    question: str


class CitationOut(BaseModel):
    arxiv_id: str
    title: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationOut]


def build_graph(settings: Settings) -> Any:
    model = init_chat_model(settings.chat_model)
    index = SemanticIndex.from_settings(settings)
    return build_agent(model, [make_semantic_search(index, settings.search_k)])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Provider SDKs read credentials from the process env; pydantic-settings only
    # loads its own PAPERTRACE_* fields, so surface .env for local runs too.
    load_dotenv()
    settings = load_settings()
    app.state.settings = settings
    app.state.graph = build_graph(settings)
    yield


app = FastAPI(title="PaperTrace", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    settings: Settings = app.state.settings
    try:
        result = run_chat(app.state.graph, request.question, settings.max_turns)
    except MaxTurnsExceeded as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    return ChatResponse(
        answer=result.answer, citations=[CitationOut(**asdict(c)) for c in result.citations]
    )
