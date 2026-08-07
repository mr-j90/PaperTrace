"""Snapshot builder units + consistency validation of the committed snapshot artifacts."""

import gzip
import json
from pathlib import Path

import pytest

from ingest.snapshot import Topic, Window, build_search_query, load_queries, merge, parse_page

REPO = Path(__file__).parent.parent
SNAPSHOT = REPO / "data" / "snapshot"

ATOM_PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2005.11401v4</id>
    <title>Retrieval-Augmented Generation for
      Knowledge-Intensive NLP Tasks</title>
    <summary>Large pre-trained language models...</summary>
    <published>2020-05-22T21:17:29Z</published>
    <updated>2021-04-12T17:27:44Z</updated>
    <author><name>Patrick Lewis</name></author>
    <author><name>Ethan Perez</name></author>
    <arxiv:primary_category term="cs.CL"/>
    <category term="cs.CL"/>
    <category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Some Agent Paper</title>
    <summary>An agent.</summary>
    <published>2024-01-01T00:00:00Z</published>
    <updated>2024-01-01T00:00:00Z</updated>
    <author><name>A. Author</name></author>
    <arxiv:doi>10.1000/xyz</arxiv:doi>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
  </entry>
</feed>
"""


def test_build_search_query() -> None:
    topic = Topic(name="rag", field="abs", phrases=["retrieval augmented generation", "rag"])
    window = Window(start="2020-01-01", end="2026-08-01")
    assert build_search_query(topic, window) == (
        '(abs:"retrieval augmented generation" OR abs:"rag")'
        " AND submittedDate:[202001010000 TO 202608010000]"
    )


def test_parse_page() -> None:
    total, papers = parse_page(ATOM_PAGE)
    assert total == 2
    assert [p.arxiv_id for p in papers] == ["2005.11401", "2401.00001"]
    lewis = papers[0]
    assert lewis.title == "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
    assert lewis.authors == ["Patrick Lewis", "Ethan Perez"]
    assert lewis.primary_category == "cs.CL"
    assert lewis.categories == ["cs.CL", "cs.LG"]
    assert lewis.doi is None
    assert papers[1].doi == "10.1000/xyz"


def test_merge_unions_topics() -> None:
    _, [lewis, agent_paper] = parse_page(ATOM_PAGE)
    lewis.topics = ["rag"]
    agent_paper.topics = ["agents"]
    _, [lewis_again, _] = parse_page(ATOM_PAGE)
    lewis_again.topics = ["agents"]
    merged = merge({"rag": [lewis], "agents": [lewis_again, agent_paper]})
    assert [p.arxiv_id for p in merged] == ["2005.11401", "2401.00001"]
    assert merged[0].topics == ["agents", "rag"]


def test_queries_toml_loads() -> None:
    window, topics = load_queries(REPO / "data" / "queries.toml")
    assert window.start == "2020-01-01"
    assert {t.name for t in topics} == {"rag", "agents", "eval", "llmops"}


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="snapshot not built yet")
def test_committed_snapshot_is_consistent() -> None:
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    ids = (SNAPSHOT / "arxiv_ids.txt").read_text().splitlines()
    with gzip.open(SNAPSHOT / "metadata.jsonl.gz", "rt", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]

    assert manifest["smoke_limit"] is None, "committed snapshot must not be a smoke run"
    assert manifest["total_unique"] == len(ids) == len(records)
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    assert [r["arxiv_id"] for r in records] == ids
    for name, topic in manifest["topics"].items():
        assert topic["in_corpus"] == topic["api_total"], f"topic '{name}' fetched short"

    window = manifest["window"]
    for record in records:
        # window end is a 00:00 cutoff the API treats inclusively — allow the boundary day
        assert window["start"] <= record["submitted"][:10] <= window["end"]
        assert record["title"] and record["abstract"]
        assert record["topics"]
