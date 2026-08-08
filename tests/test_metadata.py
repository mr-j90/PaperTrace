"""metadata_query: SQL building, execution accuracy, grounding, graceful misses (issue #6)."""

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest
from langchain_core.messages import AIMessage

from core.agent import build_agent, run_chat
from core.metadata import MetadataStore
from core.tools import make_metadata_query
from ingest.normalize import normalize
from ingest.store import load_papers
from tests.conftest import scripted_model


def record(arxiv_id: str, submitted: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "arxiv_id": arxiv_id,
        "title": f"Paper {arxiv_id}",
        "abstract": "An abstract about retrieval.",
        "authors": ["Patrick Lewis", "B. Author"],
        "primary_category": "cs.CL",
        "categories": ["cs.CL"],
        "submitted": submitted,
        "updated": submitted,
        "doi": None,
        "topics": ["rag"],
    }
    base.update(extra)
    return base


@pytest.fixture
def store(tmp_path: Path) -> MetadataStore:
    records = normalize(
        [
            record("2001.00001", "2020-01-05T00:00:00Z", topics=["rag"]),
            record("2601.00001", "2026-01-10T00:00:00Z", topics=["rag", "eval"]),
            record("2601.00002", "2026-01-20T00:00:00Z", topics=["eval"], authors=["C. Chen"]),
            record(
                "2602.00001",
                "2026-02-01T00:00:00Z",
                topics=["agents"],
                categories=["cs.MA"],
                primary_category="cs.MA",
            ),
            record(
                "2603.00001",
                "2026-03-01T00:00:00Z",
                topics=["rag"],
                abstract="This paper has been withdrawn by the authors.",
            ),
        ]
    )
    db = tmp_path / "papers.duckdb"
    load_papers(records, db)
    return MetadataStore(db)


def test_counts_match_direct_sql(store: MetadataStore, tmp_path: Path) -> None:
    result = store.query(topic="rag")
    with duckdb.connect(str(tmp_path / "papers.duckdb"), read_only=True) as con:
        row = con.execute(
            "SELECT count(*) FROM papers WHERE list_contains(topics, 'rag') AND NOT withdrawn"
        ).fetchone()
        assert row is not None
    assert result["total"] == row[0] == 2  # withdrawn rag paper excluded


def test_group_by_month_and_topic(store: MetadataStore) -> None:
    by_month = store.query(submitted_from="2026-01-01", group_by="month")
    assert {r["grp"]: r["n"] for r in by_month["rows"]} == {"2026-01": 2, "2026-02": 1}

    by_topic = store.query(group_by="topic")
    assert {r["grp"]: r["n"] for r in by_topic["rows"]} == {"rag": 2, "eval": 2, "agents": 1}


def test_freshness_window_uses_date_filter(store: MetadataStore) -> None:
    result = store.query(submitted_from="2026-01-15", submitted_to="2026-02-01")
    assert result["total"] == 2
    assert [r["arxiv_id"] for r in result["rows"]] == ["2602.00001", "2601.00002"]  # newest first
    assert "submitted >= CAST(? AS TIMESTAMP)" in result["sql"]


def test_author_and_category_filters(store: MetadataStore) -> None:
    assert store.query(author="lewis")["total"] == 3  # ILIKE, withdrawn excluded
    assert store.query(category="cs.MA")["total"] == 1


def test_unknown_arxiv_id_is_graceful(store: MetadataStore) -> None:
    result = store.query(arxiv_id="9999.99999")
    assert result["total"] == 0
    assert result["rows"] == []
    assert "not in the corpus" in result["note"]


def test_withdrawn_visible_only_on_request(store: MetadataStore) -> None:
    assert store.query(topic="rag")["total"] == 2
    assert store.query(topic="rag", include_withdrawn=True)["total"] == 3


def test_injection_attempts_are_inert(store: MetadataStore) -> None:
    result = store.query(title_contains="'; DROP TABLE papers; --")
    assert result["total"] == 0
    assert store.query()["total"] == 4  # table intact


def test_sort_variants_and_group_by_category(store: MetadataStore) -> None:
    oldest = store.query(sort="oldest")
    assert oldest["rows"][0]["arxiv_id"] == "2001.00001"
    by_title = store.query(sort="title")
    titles = [r["title"] for r in by_title["rows"]]
    assert titles == sorted(titles)
    by_cat = store.query(group_by="category")
    assert {r["grp"]: r["n"] for r in by_cat["rows"]} == {"cs.CL": 3, "cs.MA": 1}

    with pytest.raises(ValueError, match="group_by"):
        store.query(group_by="week")  # type: ignore[arg-type]


def test_missing_store_degrades_gracefully(tmp_path: Path) -> None:
    result = MetadataStore(tmp_path / "nope.duckdb").query(topic="rag")
    assert result["total"] == 0 and result["rows"] == []
    assert "unavailable" in result["error"]


def test_tool_args_ride_the_agent_state(store: MetadataStore) -> None:
    """AC3 at the data layer: the args the model passed are present as tool_calls in
    the graph's message state — exactly what #7 streams as the visible trace."""
    tool = make_metadata_query(store)
    args = {"topic": "eval", "submitted_from": "2026-01-01"}
    model = scripted_model(
        [
            AIMessage(content="", tool_calls=[{"name": "metadata_query", "args": args, "id": "c"}]),
            AIMessage(content="done"),
        ]
    )
    graph = build_agent(model, [tool])
    state = graph.invoke({"messages": [("user", "q")]}, config={"recursion_limit": 8})
    calls = [tc for m in state["messages"] for tc in getattr(m, "tool_calls", [])]
    assert calls and calls[0]["args"] == args


def test_limit_clamped(store: MetadataStore) -> None:
    assert len(store.query(limit=999)["rows"]) <= 50
    assert len(store.query(limit=-5)["rows"]) >= 1


def test_metadata_rows_ground_citations(store: MetadataStore) -> None:
    """Papers listed by metadata_query are citable evidence, and tool args ride the trace."""
    tool = make_metadata_query(store)
    model = scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "metadata_query",
                        "args": {"topic": "eval", "submitted_from": "2026-01-01"},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Two eval papers, e.g. [arxiv:2601.00002]."),
        ]
    )
    graph = build_agent(model, [tool])
    result = run_chat(graph, "what's new in eval since January?", max_turns=6)

    assert [c.arxiv_id for c in result.citations] == ["2601.00002"]
    assert result.citations[0].title == "Paper 2601.00002"


def test_tool_returns_sql_for_the_trace(store: MetadataStore) -> None:
    tool = make_metadata_query(store)
    payload = json.loads(tool.invoke({"topic": "rag", "group_by": "year"}))
    assert payload["sql"].startswith("SELECT")
    assert {r["grp"]: r["n"] for r in payload["rows"]} == {"2020": 1, "2026": 1}
