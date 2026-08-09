"""Delta-mode units: watermark, upsert semantics, withdrawal removal (issue #10)."""

from pathlib import Path

from core.retrieval import ABSTRACT_LAYER, FULLTEXT_LAYER
from ingest.normalize import normalize
from ingest.store import latest_submitted, load_papers, paper_count, upsert_papers
from tests.conftest import LEWIS, make_index
from tests.test_ingest import record


def test_watermark_and_upsert(tmp_path: Path) -> None:
    db = tmp_path / "papers.duckdb"
    load_papers(
        normalize(
            [
                record("2001.00001", "2020-01-05T00:00:00Z"),
                record("2606.00001", "2026-06-01T00:00:00Z"),
            ]
        ),
        db,
    )
    assert latest_submitted(db) == "2026-06-01"

    # delta upsert: one new paper, one revision of an existing paper
    upsert_papers(
        normalize(
            [
                record("2607.00001", "2026-07-01T00:00:00Z"),  # new
                record(
                    "2606.00001",
                    "2026-06-01T00:00:00Z",  # revised: now withdrawn
                    abstract="This paper has been withdrawn by the authors.",
                ),
            ]
        ),
        db,
    )
    assert paper_count(db) == 3  # 2 original + 1 new; revision replaced in place
    assert latest_submitted(db) == "2026-07-01"

    import duckdb

    with duckdb.connect(str(db), read_only=True) as con:
        row = con.execute("SELECT withdrawn FROM papers WHERE arxiv_id = '2606.00001'").fetchone()
        assert row is not None and row[0] is True  # flagged, still queryable


def test_upsert_unions_topics_with_stored(tmp_path: Path) -> None:
    """A paper resurfacing via one topic's sweep must not lose its other labels."""
    db = tmp_path / "papers.duckdb"
    load_papers(
        normalize([record("2601.00001", "2026-01-10T00:00:00Z", topics=["rag", "eval"])]), db
    )
    upsert_papers(normalize([record("2601.00001", "2026-01-10T00:00:00Z", topics=["eval"])]), db)

    import duckdb

    with duckdb.connect(str(db), read_only=True) as con:
        row = con.execute("SELECT topics FROM papers WHERE arxiv_id = '2601.00001'").fetchone()
        assert row is not None and sorted(row[0]) == ["eval", "rag"]


def test_withdrawal_detected_from_comment_field() -> None:
    from ingest.normalize import is_withdrawn

    assert is_withdrawn("A normal abstract.", "This submission has been withdrawn due to an error")
    assert not is_withdrawn("A normal abstract.", "12 pages, 3 figures")
    assert not is_withdrawn("A normal abstract.", None)


def test_withdrawal_removed_from_all_layers() -> None:
    index = make_index()
    index.index_abstracts([LEWIS])
    index.index_chunks("2005.11401", str(LEWIS["title"]), [("S1", "some retrieval text")])
    assert index.count() == 2

    index.remove_paper("2005.11401")
    assert index.count(layer=ABSTRACT_LAYER) == 0
    assert index.count(layer=FULLTEXT_LAYER) == 0


def test_snapshot_artifacts_untouched_by_delta_paths(tmp_path: Path) -> None:
    """Nothing in the delta module references the snapshot artifacts directory."""
    import inspect

    import ingest.delta as delta

    source = inspect.getsource(delta)
    assert "data/snapshot" not in source  # delta must never write the pinned snapshot
