"""Semantic retrieval over the layered papers collection (SPEC §5, final form).

Hybrid search: dense (bge-class) + sparse (BM25, IDF applied server-side) fused with
RRF in Qdrant, rescored by a local cross-encoder, deduped per paper, scoped by layer.
"""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    Modifier,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from core.embeddings import Embedder, SparseEmbedder
from core.rerank import Reranker

if TYPE_CHECKING:
    from core.config import Settings

ABSTRACT_LAYER = "abstract"
FULLTEXT_LAYER = "fulltext"

Scope = Literal["abstracts", "fulltext", "all"]
_SCOPE_LAYERS: dict[str, str] = {"abstracts": ABSTRACT_LAYER, "fulltext": FULLTEXT_LAYER}

DENSE = "dense"
SPARSE = "sparse"


@dataclass
class Evidence:
    arxiv_id: str
    title: str
    snippet: str
    score: float


def point_id(arxiv_id: str, layer: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"papertrace:{arxiv_id}:{layer}"))


def card_text(
    title: str, abstract: str, authors: list[str], submitted: str, categories: list[str]
) -> str:
    """An abstract card: the per-paper searchable unit (CONTEXT.md)."""
    names = ", ".join(authors[:5]) + (" et al." if len(authors) > 5 else "")
    return f"{title}\n{names}\n\n{abstract}\n\n({submitted[:10]}; {', '.join(categories)})"


def _scope_filter(scope: Scope) -> Filter | None:
    layer = _SCOPE_LAYERS.get(scope)
    if layer is None:
        return None
    return Filter(must=[FieldCondition(key="layer", match=MatchValue(value=layer))])


class SemanticIndex:
    """Owns the Qdrant collection: indexing (used by ingest) and search (used by the agent)."""

    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        embed: Embedder,
        dim: int,
        sparse: SparseEmbedder,
        rerank: Reranker,
        rerank_candidates: int = 30,
        max_per_paper: int = 3,
    ) -> None:
        self._client = client
        self._collection = collection
        self._embed = embed
        self._dim = dim
        self._sparse = sparse
        self._rerank = rerank
        self._rerank_candidates = rerank_candidates
        self._max_per_paper = max_per_paper

    @classmethod
    def from_settings(cls, settings: "Settings") -> "SemanticIndex":
        from core.embeddings import load_embedder, load_sparse_embedder
        from core.rerank import load_reranker

        return cls(
            client=QdrantClient(url=settings.qdrant_url),
            collection=settings.collection,
            embed=load_embedder(settings.embedding_model),
            dim=settings.embedding_dim,
            sparse=load_sparse_embedder(settings.sparse_model),
            rerank=load_reranker(settings.rerank_model),
            rerank_candidates=settings.rerank_candidates,
            max_per_paper=settings.max_per_paper,
        )

    def ensure_collection(self) -> None:
        """Create the named-vector collection; drop and recreate a legacy (dense-only) one."""
        if self._client.collection_exists(self._collection):
            params = self._client.get_collection(self._collection).config.params
            named = isinstance(params.vectors, dict) and DENSE in params.vectors
            if named and params.sparse_vectors and SPARSE in params.sparse_vectors:
                return
            print(
                f"recreating collection '{self._collection}': legacy schema detected "
                "(index shape changed — full reindex required)"
            )
            self._client.delete_collection(self._collection)
        self._client.create_collection(
            self._collection,
            vectors_config={DENSE: VectorParams(size=self._dim, distance=Distance.COSINE)},
            sparse_vectors_config={SPARSE: SparseVectorParams(modifier=Modifier.IDF)},
        )

    def _points(self, items: list[tuple[str, str, dict[str, Any]]]) -> list[PointStruct]:
        """items: (point_id, embedded_text, payload)."""
        dense_vecs = self._embed([text for _, text, _ in items])
        sparse_vecs = self._sparse.embed_docs([text for _, text, _ in items])
        return [
            PointStruct(
                id=pid,
                vector={
                    DENSE: dense,
                    SPARSE: SparseVector(indices=indices, values=values),
                },
                payload=payload,
            )
            for (pid, _, payload), dense, (indices, values) in zip(
                items, dense_vecs, sparse_vecs, strict=True
            )
        ]

    def index_abstracts(self, records: list[dict[str, Any]]) -> int:
        items: list[tuple[str, str, dict[str, Any]]] = []
        for r in records:
            text = card_text(
                str(r["title"]),
                str(r["abstract"]),
                r["authors"],
                str(r["submitted"]),
                r["categories"],
            )
            payload = {
                "arxiv_id": r["arxiv_id"],
                "title": r["title"],
                "text": text,
                "layer": ABSTRACT_LAYER,
                "submitted": r["submitted"],
                "topics": r["topics"],
            }
            items.append((point_id(str(r["arxiv_id"]), ABSTRACT_LAYER), text, payload))
        points = self._points(items)
        self._client.upsert(self._collection, points=points)
        return len(points)

    def index_chunks(self, arxiv_id: str, title: str, chunks: list[tuple[str, str]]) -> int:
        """Replace a paper's section chunks: (section_heading, embedded_text) pairs."""
        self._client.delete(
            self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(key="arxiv_id", match=MatchValue(value=arxiv_id)),
                    FieldCondition(key="layer", match=MatchValue(value=FULLTEXT_LAYER)),
                ]
            ),
        )
        if not chunks:
            return 0
        items = [
            (
                point_id(f"{arxiv_id}:{i}", FULLTEXT_LAYER),
                text,
                {
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "text": text,
                    "layer": FULLTEXT_LAYER,
                    "section": section,
                },
            )
            for i, (section, text) in enumerate(chunks)
        ]
        points = self._points(items)
        self._client.upsert(self._collection, points=points)
        return len(points)

    def prune_fulltext(self, keep_ids: list[str]) -> None:
        """Drop fulltext chunks for papers no longer in the tier (idempotent re-runs)."""
        self._client.delete(
            self._collection,
            points_selector=Filter(
                must=[FieldCondition(key="layer", match=MatchValue(value=FULLTEXT_LAYER))],
                must_not=[FieldCondition(key="arxiv_id", match=MatchAny(any=keep_ids))],
            ),
        )

    def count(self, layer: str | None = None) -> int:
        if layer is None:
            return self._client.count(self._collection).count
        return self._client.count(
            self._collection,
            count_filter=Filter(must=[FieldCondition(key="layer", match=MatchValue(value=layer))]),
        ).count

    def search(self, query: str, k: int, scope: Scope = "all") -> list[Evidence]:
        """Hybrid RRF fusion -> cross-encoder rescoring -> per-paper dedup -> top-k.

        The fused pool is capped at rerank_candidates; if it concentrates in few
        papers the dedup cap can underfill k — accepted (spec'd top-30 pool).
        """
        [dense] = self._embed([query])
        indices, values = self._sparse.embed_query(query)
        scope_filter = _scope_filter(scope)
        candidates = self._client.query_points(
            self._collection,
            prefetch=[
                Prefetch(
                    query=dense,
                    using=DENSE,
                    limit=self._rerank_candidates,
                    filter=scope_filter,
                ),
                Prefetch(
                    query=SparseVector(indices=indices, values=values),
                    using=SPARSE,
                    limit=self._rerank_candidates,
                    filter=scope_filter,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=self._rerank_candidates,
        ).points

        payloads = [hit.payload or {} for hit in candidates]
        texts = [str(p.get("text", "")) for p in payloads]
        scores = self._rerank(query, texts)
        ranked = sorted(zip(payloads, scores, strict=True), key=lambda pair: -pair[1])

        results: list[Evidence] = []
        per_paper: dict[str, int] = {}
        for payload, score in ranked:
            arxiv_id = str(payload.get("arxiv_id", ""))
            if per_paper.get(arxiv_id, 0) >= self._max_per_paper:
                continue
            per_paper[arxiv_id] = per_paper.get(arxiv_id, 0) + 1
            results.append(
                Evidence(
                    arxiv_id=arxiv_id,
                    title=str(payload.get("title", "")),
                    snippet=str(payload.get("text", ""))[:500],
                    score=score,
                )
            )
            if len(results) >= k:
                break
        return results
