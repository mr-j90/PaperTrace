"""Semantic retrieval over the layered papers collection (tracer: abstract cards, dense-only)."""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from core.embeddings import Embedder

if TYPE_CHECKING:
    from core.config import Settings

ABSTRACT_LAYER = "abstract"


@dataclass
class Evidence:
    arxiv_id: str
    title: str
    snippet: str
    score: float


def point_id(arxiv_id: str, layer: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"papertrace:{arxiv_id}:{layer}"))


def card_text(title: str, abstract: str, submitted: str, categories: list[str]) -> str:
    """An abstract card: the per-paper searchable unit (CONTEXT.md)."""
    return f"{title}\n\n{abstract}\n\n({submitted[:10]}; {', '.join(categories)})"


class SemanticIndex:
    """Owns the Qdrant collection: indexing (used by ingest) and search (used by the agent)."""

    def __init__(self, client: QdrantClient, collection: str, embed: Embedder, dim: int) -> None:
        self._client = client
        self._collection = collection
        self._embed = embed
        self._dim = dim

    @classmethod
    def from_settings(cls, settings: "Settings") -> "SemanticIndex":
        from core.embeddings import load_embedder

        return cls(
            client=QdrantClient(url=settings.qdrant_url),
            collection=settings.collection,
            embed=load_embedder(settings.embedding_model),
            dim=settings.embedding_dim,
        )

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )

    def index_abstracts(self, records: list[dict[str, Any]]) -> int:
        texts = [
            card_text(str(r["title"]), str(r["abstract"]), str(r["submitted"]), r["categories"])
            for r in records
        ]
        vectors = self._embed(texts)
        points = [
            PointStruct(
                id=point_id(str(r["arxiv_id"]), ABSTRACT_LAYER),
                vector=vector,
                payload={
                    "arxiv_id": r["arxiv_id"],
                    "title": r["title"],
                    "text": text,
                    "layer": ABSTRACT_LAYER,
                    "submitted": r["submitted"],
                    "topics": r["topics"],
                },
            )
            for r, text, vector in zip(records, texts, vectors, strict=True)
        ]
        self._client.upsert(self._collection, points=points)
        return len(points)

    def count(self) -> int:
        return self._client.count(self._collection).count

    def search(self, query: str, k: int) -> list[Evidence]:
        [vector] = self._embed([query])
        hits = self._client.query_points(self._collection, query=vector, limit=k).points
        results: list[Evidence] = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                Evidence(
                    arxiv_id=str(payload.get("arxiv_id", "")),
                    title=str(payload.get("title", "")),
                    snippet=str(payload.get("text", ""))[:500],
                    score=hit.score,
                )
            )
        return results
