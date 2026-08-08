"""Retrieval final form: hybrid fusion, re-ranking, scope, per-paper dedup (issue #5)."""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from core.retrieval import ABSTRACT_LAYER, FULLTEXT_LAYER, SemanticIndex
from tests.conftest import DIM, LEWIS, OTHER, fake_embedder, fake_reranker, fake_sparse, make_index


def test_hybrid_finds_lexical_match_dense_misses() -> None:
    """Discriminative fusion test: the target is dense-FAR from the query while 31
    decoys are dense-near, so the dense prefetch (limit 30) can never contain it.
    Only its rare token 'zorblex' — via the sparse leg — can surface it. Deleting
    the sparse Prefetch makes this fail."""
    from qdrant_client import QdrantClient

    from tests.conftest import fake_reranker, fake_sparse

    def dense(texts: list[str]) -> list[list[float]]:
        # query 'zorblex ...' and decoys share a corner; the target sits opposite
        return [
            [0.0] * (DIM - 1) + [1.0] if "TARGET" in t else [1.0] + [0.0] * (DIM - 1) for t in texts
        ]

    index = SemanticIndex(
        client=QdrantClient(":memory:"),
        collection="papers",
        embed=dense,
        dim=DIM,
        sparse=fake_sparse(),
        rerank=fake_reranker(),
    )
    index.ensure_collection()
    decoys = [
        {**OTHER, "arxiv_id": f"2400.{i:05d}", "abstract": f"decoy paper number {i}"}
        for i in range(31)
    ]
    target = {**OTHER, "arxiv_id": "2401.99999", "abstract": "TARGET zorblex calibration."}
    index.index_abstracts([*decoys, target])

    hits = index.search("zorblex calibration", k=5)
    assert "2401.99999" in [e.arxiv_id for e in hits]


def test_reranker_orders_final_evidence() -> None:
    """Fusion order and rerank order disagree; the reranker must win. Skipping the
    rerank step returns fusion order and fails this test."""
    marker_reranker = lambda query, texts: [  # noqa: E731
        1.0 if "marker" in text.lower() else 0.0 for text in texts
    ]
    index = make_index(rerank=marker_reranker)
    fusion_favorite = {**LEWIS, "abstract": "alpha beta gamma delta overlap heavy."}
    rerank_favorite = {**OTHER, "abstract": "alpha MARKER."}
    index.index_abstracts([fusion_favorite, rerank_favorite])

    hits = index.search("alpha beta gamma delta", k=2)
    assert hits[0].arxiv_id == str(OTHER["arxiv_id"])  # reranker overruled fusion
    assert hits[0].score > hits[1].score


def test_scope_filters_layers() -> None:
    index = make_index()
    index.index_abstracts([LEWIS])
    index.index_chunks("2005.11401", str(LEWIS["title"]), [("Methods", "retrieval methods text")])

    abstracts = index.search("retrieval", k=10, scope="abstracts")
    fulltext = index.search("retrieval", k=10, scope="fulltext")
    both = index.search("retrieval", k=10, scope="all")

    assert len(abstracts) == 1 and len(fulltext) == 1
    assert len(both) == 2
    assert index.count(layer=ABSTRACT_LAYER) == 1
    assert index.count(layer=FULLTEXT_LAYER) == 1


def test_per_paper_dedup_caps_chunks() -> None:
    index = make_index(max_per_paper=2)
    index.index_abstracts([LEWIS, OTHER])
    index.index_chunks(
        "2005.11401",
        str(LEWIS["title"]),
        [(f"S{i}", f"retrieval retrieval passage {i}") for i in range(6)],
    )

    hits = index.search("retrieval", k=10)
    lewis_hits = [e for e in hits if e.arxiv_id == "2005.11401"]
    assert len(lewis_hits) == 2  # capped, despite 7 matching points for the paper


def test_legacy_dense_only_collection_is_recreated() -> None:
    client = QdrantClient(":memory:")
    client.create_collection(  # the pre-#5 unnamed dense-only shape
        "papers", vectors_config=VectorParams(size=DIM, distance=Distance.COSINE)
    )
    index = SemanticIndex(
        client=client,
        collection="papers",
        embed=fake_embedder(),
        dim=DIM,
        sparse=fake_sparse(),
        rerank=fake_reranker(),
    )
    index.ensure_collection()  # must drop + recreate, not crash on upsert later
    index.index_abstracts([LEWIS])
    assert index.count() == 1
