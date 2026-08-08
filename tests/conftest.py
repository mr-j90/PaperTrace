"""Shared test fakes: deterministic embedders, reranker, scripted chat model, index factory.

Everything here is CI-safe — no network, no model downloads, in-memory Qdrant.
"""

import hashlib
from collections.abc import Iterator
from typing import Any

from langchain_core.language_models import GenericFakeChatModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from qdrant_client import QdrantClient

from core.embeddings import Embedder, SparseEmbedder, SparseVec
from core.rerank import Reranker
from core.retrieval import SemanticIndex

DIM = 8

LEWIS: dict[str, Any] = {
    "arxiv_id": "2005.11401",
    "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
    "abstract": "We explore RAG models which combine parametric and non-parametric memory.",
    "authors": ["Patrick Lewis", "Ethan Perez"],
    "submitted": "2020-05-22T21:17:29Z",
    "categories": ["cs.CL"],
    "topics": ["rag"],
}
OTHER: dict[str, Any] = {
    "arxiv_id": "2401.99999",
    "title": "An Unrelated Paper",
    "abstract": "Something else entirely.",
    "authors": ["A. Author"],
    "submitted": "2024-01-05T00:00:00Z",
    "categories": ["cs.AI"],
    "topics": ["agents"],
}


def fake_embedder() -> Embedder:
    """Deterministic dense vectors: texts mentioning RAG cluster at one corner."""

    def embed(texts: list[str]) -> list[list[float]]:
        return [
            [1.0] + [0.0] * (DIM - 1)
            if ("RAG" in text or "retrieval" in text.lower())
            else [0.0] * (DIM - 1) + [1.0]
            for text in texts
        ]

    return embed


def _bag_of_words(text: str) -> SparseVec:
    indices: dict[int, float] = {}
    for word in text.lower().split():
        token = int.from_bytes(hashlib.sha1(word.encode()).digest()[:4], "big")
        indices[token] = indices.get(token, 0.0) + 1.0
    return (list(indices.keys()), list(indices.values()))


def fake_sparse() -> SparseEmbedder:
    """Word-hash bag: exact-token overlap behaves like a tiny BM25.

    Known blind spot: doc and query sides are symmetric here, so swapping them in
    production code would not fail these tests (the real BM25 weights differ).
    """
    return SparseEmbedder(
        embed_docs=lambda texts: [_bag_of_words(t) for t in texts],
        embed_query=_bag_of_words,
    )


def fake_reranker() -> Reranker:
    """Scores by shared lowercase words with the query — order-changing and predictable."""

    def rerank(query: str, texts: list[str]) -> list[float]:
        query_words = set(query.lower().split())
        return [float(len(query_words & set(text.lower().split()))) for text in texts]

    return rerank


def make_index(
    max_per_paper: int = 3,
    rerank: Reranker | None = None,
) -> SemanticIndex:
    index = SemanticIndex(
        client=QdrantClient(":memory:"),
        collection="papers",
        embed=fake_embedder(),
        dim=DIM,
        sparse=fake_sparse(),
        rerank=rerank or fake_reranker(),
        rerank_candidates=30,
        max_per_paper=max_per_paper,
    )
    index.ensure_collection()
    return index


class ToolCallingFakeModel(GenericFakeChatModel):
    """GenericFakeChatModel that accepts bind_tools (scripted responses ignore them)."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return self


def scripted_model(messages: list[AIMessage]) -> BaseChatModel:
    iterator: Iterator[AIMessage | str] = iter(messages)
    return ToolCallingFakeModel(messages=iterator)
