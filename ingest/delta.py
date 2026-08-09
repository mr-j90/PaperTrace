"""The ingestion flow's delta mode (SPEC §4): keep the live corpus fresh, daily.

Watermark = the newest submission date already in the store (minus an overlap
margin — re-fetched papers upsert idempotently, so overlap is free). Two sweeps
per topic: new submissions in [watermark → tomorrow], plus one page of recently
*updated* papers to catch revisions — withdrawals are detected from the arXiv
comment field (where withdrawal notices live) and the abstract heuristic, then
flagged and removed from retrieval. Known limit: the sweep only sees papers still
matching the topic phrases; full-coverage revision tracking (id_list rotation over
held ids) is future work. The pinned snapshot artifacts are never touched.

Usage:
    uv run python -m ingest.delta            # one delta run
    uv run python -m ingest.serve            # register + run the daily schedule
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from prefect import flow, task
from prefect.artifacts import create_markdown_artifact

from core.config import load_settings
from core.retrieval import SemanticIndex
from ingest.fulltext import USER_AGENT, chunk_sections, fetch_html, parse_sections
from ingest.normalize import normalize
from ingest.snapshot import Window, fetch_topic, load_queries, merge
from ingest.store import latest_submitted, upsert_papers

OVERLAP_DAYS = 2  # re-fetch a margin behind the watermark; upserts make it free
REVISION_PAGE = 100  # recently-updated sweep per topic, catches withdrawals


def _open_index() -> SemanticIndex:
    index = SemanticIndex.from_settings(load_settings())
    index.ensure_collection()
    return index


@task
def fetch_delta(queries_path: Path, db_path: Path) -> list[dict[str, Any]]:
    watermark = latest_submitted(db_path)
    if watermark is None:
        raise RuntimeError("empty store — run the snapshot ingest before delta mode")
    start = (datetime.fromisoformat(watermark) - timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d")
    end = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    window = Window(start=start, end=end)
    print(f"delta window: {start} -> {end}")

    _, topics = load_queries(queries_path)
    per_topic: dict[str, list[Any]] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        for topic in topics:
            _, new_papers = fetch_topic(client, topic, window, limit=None)
            # one recently-updated page over the full corpus window: revision sweep
            _, revised = fetch_topic(
                client,
                topic,
                Window(start="2020-01-01", end=end),
                limit=REVISION_PAGE,
                sort_by="lastUpdatedDate",
                sort_order="descending",
            )
            per_topic[topic.name] = new_papers + revised
            print(f"  {topic.name}: {len(new_papers)} new, {len(revised)} revision-swept")
    from dataclasses import asdict

    return [asdict(p) for p in merge(per_topic)]


@task
def upsert_records(records: list[dict[str, Any]], db_path: Path) -> dict[str, int]:
    normalized = normalize(records)
    upsert_papers(normalized, db_path)
    withdrawn = [r for r in normalized if r["withdrawn"]]
    return {"upserted": len(normalized), "withdrawn": len(withdrawn)}


@task
def reindex(
    records: list[dict[str, Any]], window_days: int = 183, fulltext_cap: int = 50
) -> dict[str, int]:
    """Index live papers' cards; full text for the recent ones (newest first, capped
    per run — daily volume fits; any backlog trickles over subsequent days); remove
    withdrawn."""
    normalized = normalize(records)
    index = _open_index()
    live = [r for r in normalized if not r["withdrawn"]]
    for start in range(0, len(live), 128):
        index.index_abstracts(live[start : start + 128])
    for r in normalized:
        if r["withdrawn"]:
            index.remove_paper(str(r["arxiv_id"]))

    cutoff = (datetime.now(UTC) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    recent = sorted(
        (r for r in live if str(r["submitted"])[:10] >= cutoff),
        key=lambda r: str(r["submitted"]),
        reverse=True,
    )[:fulltext_cap]
    chunks_indexed = papers_with_fulltext = skipped = 0
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        for r in recent:
            if index.has_fulltext(str(r["arxiv_id"])):  # don't re-fetch daily
                skipped += 1
                continue
            html = fetch_html(client, str(r["arxiv_id"]))
            if html is None:
                continue
            chunks = chunk_sections(str(r["title"]), parse_sections(html))
            written = index.index_chunks(
                str(r["arxiv_id"]), str(r["title"]), [(c.section, c.text) for c in chunks]
            )
            papers_with_fulltext += 1
            chunks_indexed += written
    return {
        "cards": len(live),
        "removed": sum(1 for r in normalized if r["withdrawn"]),
        "fulltext_papers": papers_with_fulltext,
        "chunks": chunks_indexed,
    }


@flow(name="papertrace-delta")
def ingest_delta(queries_path: Path = Path("data/queries.toml"), fulltext_cap: int = 50) -> None:
    settings = load_settings()
    db_path = Path(settings.duckdb_path)
    records = fetch_delta(queries_path, db_path)
    store_stats = upsert_records(records, db_path)
    index_stats = reindex(records, fulltext_cap=fulltext_cap)
    report = (
        f"# Delta report\n\n| stage | count |\n|---|---|\n"
        f"| papers fetched (new + revision sweep) | {len(records)} |\n"
        f"| upserted into DuckDB | {store_stats['upserted']} |\n"
        f"| withdrawn (flagged + removed from retrieval) | {store_stats['withdrawn']} |\n"
        f"| abstract cards indexed | {index_stats['cards']} |\n"
        f"| recent papers with full text | {index_stats['fulltext_papers']} |\n"
        f"| section chunks indexed | {index_stats['chunks']} |\n"
    )
    create_markdown_artifact(markdown=report, key="delta-report")
    print("\n" + report)


if __name__ == "__main__":
    ingest_delta()
