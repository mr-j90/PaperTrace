"""Ingestion units: normalize, tier selection, HTML parsing, chunking, DuckDB store."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from ingest.fulltext import CHUNK_CHARS, chunk_sections, parse_sections
from ingest.normalize import is_withdrawn, normalize
from ingest.store import load_papers, paper_count
from ingest.tier import select_tier, split_by_recency


def record(arxiv_id: str, submitted: str, withdrawn: bool = False, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "arxiv_id": arxiv_id,
        "title": f"Paper {arxiv_id}",
        "abstract": "This paper has been withdrawn by the authors."
        if withdrawn
        else "A real abstract about retrieval.",
        "authors": ["A. Author"],
        "primary_category": "cs.CL",
        "categories": ["cs.CL"],
        "submitted": submitted,
        "updated": submitted,
        "doi": None,
        "topics": ["rag"],
    }
    base.update(extra)
    return base


def test_normalize_flags_withdrawals_and_dedupes() -> None:
    records = [
        record("2005.11401", "2020-05-22T21:17:29Z"),
        record("2005.11401", "2020-05-22T21:17:29Z"),  # duplicate
        record("2401.00001", "2024-01-01T00:00:00Z", withdrawn=True),
    ]
    normalized = normalize(records)
    assert [r["arxiv_id"] for r in normalized] == ["2005.11401", "2401.00001"]
    assert [r["withdrawn"] for r in normalized] == [False, True]


def test_normalize_rejects_incomplete_records() -> None:
    broken = record("2401.00002", "2024-01-01T00:00:00Z")
    broken["title"] = ""
    with pytest.raises(ValueError, match="2401.00002"):
        normalize([broken])


def test_is_withdrawn_only_matches_notice_position() -> None:
    assert is_withdrawn("This paper has been withdrawn due to an error in Lemma 2.")
    assert not is_withdrawn("We study papers that were withdrawn from conferences." + "x" * 400)


def test_tier_stays_hybrid_and_excludes_withdrawn() -> None:
    window_end = date(2026, 8, 1)
    records = normalize(
        [
            record("2606.00001", "2026-06-01T00:00:00Z"),  # recent
            record("2603.00001", "2026-03-01T00:00:00Z"),  # recent
            record("2602.00001", "2026-02-15T00:00:00Z"),  # recent
            record("2005.11401", "2020-05-22T00:00:00Z"),  # old, highly cited
            record("2101.00001", "2021-01-01T00:00:00Z"),  # old, few citations
            record("2604.00009", "2026-04-09T00:00:00Z", withdrawn=True),  # never tiered
        ]
    )
    citations = {"2005.11401": 9000, "2101.00001": 3}
    recent_ids, rest_ids = split_by_recency(records, window_end)
    assert recent_ids == ["2606.00001", "2603.00001", "2602.00001"]  # newest first
    assert "2604.00009" not in recent_ids + rest_ids  # withdrawn never a candidate

    # budget 4 with 3 recents: half recency, half citations — hybrid survives overflow
    tier = select_tier(recent_ids, rest_ids, budget=4, citations=citations)
    assert tier == ["2606.00001", "2603.00001", "2005.11401", "2101.00001"]

    # one side short: the other absorbs the slack
    assert select_tier(recent_ids, [], budget=4, citations={}) == recent_ids[:3]
    assert select_tier([], rest_ids, budget=4, citations=citations) == [
        "2005.11401",
        "2101.00001",
    ]


def test_s2_malformed_payload_degrades_to_zeros(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ingest.tier.time.sleep", lambda s: None)

    class BadResponse:
        status_code = 200

        @staticmethod
        def json() -> list[Any]:
            return [{"citationCount": 1}]  # wrong length for a 2-id batch

    class StubClient:
        def post(self, *args: Any, **kwargs: Any) -> BadResponse:
            return BadResponse()

    from ingest.tier import fetch_citation_counts

    counts = fetch_citation_counts(["a", "b"], client=StubClient())  # type: ignore[arg-type]
    assert counts == {"a": 0, "b": 0}


LATEXML_HTML = """
<html><body>
<section class="ltx_section"><h2 class="ltx_title">1 Introduction</h2>
<div class="ltx_para"><p>{intro}</p></div></section>
<section class="ltx_section"><h2 class="ltx_title">2 Methods</h2>
<div class="ltx_para"><p>{methods}</p></div>
<math>ignored math</math></section>
<section class="ltx_section"><h2 class="ltx_title">Acknowledgments</h2>
<div class="ltx_para"><p>Thanks.</p></div></section>
</body></html>
""".format(intro="Retrieval matters. " * 20, methods="We embed sections. " * 30)


def test_parse_sections_extracts_headings_and_drops_stubs() -> None:
    sections = parse_sections(LATEXML_HTML)
    assert [h for h, _ in sections] == ["1 Introduction", "2 Methods"]
    assert "ignored math" not in sections[1][1]
    assert "Thanks." not in str(sections)  # sub-MIN_SECTION_CHARS stub dropped


def test_parse_sections_falls_back_to_whole_body() -> None:
    sections = parse_sections(f"<html><body><p>{'Plain page text. ' * 20}</p></body></html>")
    assert len(sections) == 1
    assert sections[0][0] == "Full text"


def test_chunk_sections_sizes_and_prefixes() -> None:
    long_text = "word " * 1500  # ~7500 chars -> several chunks
    chunks = chunk_sections("My Title", [("Methods", long_text.strip())])
    assert len(chunks) >= 3
    assert all(c.text.startswith("My Title — Methods\n\n") for c in chunks)
    assert all(len(c.text) <= CHUNK_CHARS + 40 for c in chunks)  # prefix overhead only


def test_fulltext_reindex_and_prune_leave_no_orphans() -> None:
    from qdrant_client import QdrantClient

    from core.retrieval import FULLTEXT_LAYER, SemanticIndex
    from tests.test_agent import DIM, fake_embedder

    index = SemanticIndex(
        client=QdrantClient(":memory:"), collection="papers", embed=fake_embedder(), dim=DIM
    )
    index.ensure_collection()
    index.index_chunks("paperA", "A", [("S1", "text one"), ("S2", "text two"), ("S3", "three")])
    index.index_chunks("paperB", "B", [("S1", "b text")])
    assert index.count(layer=FULLTEXT_LAYER) == 4

    # re-parse yielding fewer chunks: old points for the paper must vanish
    index.index_chunks("paperA", "A", [("S1", "only chunk now")])
    assert index.count(layer=FULLTEXT_LAYER) == 2

    # tier shrink: pruning drops papers no longer kept
    index.prune_fulltext(keep_ids=["paperA"])
    assert index.count(layer=FULLTEXT_LAYER) == 1


def test_duckdb_roundtrip(tmp_path: Path) -> None:
    records = normalize(
        [record("2005.11401", "2020-05-22T21:17:29Z"), record("2401.00001", "2024-01-01T00:00:00Z")]
    )
    db = tmp_path / "papers.duckdb"
    assert load_papers(records, db) == 2
    assert paper_count(db) == 2
    assert load_papers(records, db) == 2  # idempotent re-run
