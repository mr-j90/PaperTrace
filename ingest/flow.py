"""The ingestion flow (SPEC §4): one parameterized Prefect flow building the knowledge base.

Snapshot mode (this ticket): pinned snapshot -> normalize -> DuckDB -> tier select ->
full text (HTML-first) -> chunk -> embed -> index -> validate. Delta mode arrives with #10.

Usage:
    uv run python -m ingest.flow                          # full tier (~2k papers, ~2h polite)
    uv run python -m ingest.flow --fulltext-budget 25     # minutes, for reviewers
    PAPERTRACE_FULLTEXT_BUDGET=25 uv run python -m ingest.flow   # same, via env
Runs report to the Prefect server when PREFECT_API_URL is set (compose serves the UI
at http://localhost:4200); without it the flow runs ephemerally — same result.

Settings (and secrets like the optional S2 API key) are read from the environment
inside tasks, never passed as flow/task parameters the Prefect server would record.
"""

import argparse
import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from prefect import flow, task
from prefect.artifacts import create_markdown_artifact

from core.config import load_settings
from core.retrieval import ABSTRACT_LAYER, FULLTEXT_LAYER, SemanticIndex
from ingest.fulltext import USER_AGENT, chunk_sections, fetch_html, parse_sections
from ingest.normalize import normalize
from ingest.store import load_papers
from ingest.tier import fetch_citation_counts, select_tier, split_by_recency

BATCH = 256


def _live(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if not r["withdrawn"]]


def _open_index() -> SemanticIndex:
    index = SemanticIndex.from_settings(load_settings())
    index.ensure_collection()
    return index


@task
def load_snapshot(snapshot_dir: Path) -> tuple[list[dict[str, Any]], date]:
    with gzip.open(snapshot_dir / "metadata.jsonl.gz", "rt", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    manifest = json.loads((snapshot_dir / "manifest.json").read_text())
    return records, date.fromisoformat(manifest["window"]["end"])


@task
def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return normalize(records)


@task
def load_metadata_store(records: list[dict[str, Any]]) -> int:
    return load_papers(records, Path(load_settings().duckdb_path))


@task
def select_fulltext_tier(records: list[dict[str, Any]], budget: int, window_end: date) -> list[str]:
    recent_ids, rest_ids = split_by_recency(records, window_end)
    # citations only matter for the non-recent half — don't hammer S2 for the rest
    citations = fetch_citation_counts(rest_ids, api_key=load_settings().s2_api_key)
    return select_tier(recent_ids, rest_ids, budget, citations)


@task
def index_abstract_cards(records: list[dict[str, Any]]) -> int:
    index = _open_index()
    live = _live(records)
    indexed = 0
    for start in range(0, len(live), BATCH):
        indexed += index.index_abstracts(live[start : start + BATCH])
    return indexed


@task
def index_fulltext_tier(records: list[dict[str, Any]], tier_ids: list[str]) -> dict[str, int]:
    by_id = {str(r["arxiv_id"]): r for r in records}
    index = _open_index()
    index.prune_fulltext(keep_ids=tier_ids)  # shrinking re-runs leave no stale chunks
    stats = {"papers_with_fulltext": 0, "papers_without_html": 0, "chunks_indexed": 0}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        for position, arxiv_id in enumerate(tier_ids, start=1):
            title = str(by_id[arxiv_id]["title"])
            html = fetch_html(client, arxiv_id)
            if html is None:
                stats["papers_without_html"] += 1
                continue
            chunks = chunk_sections(title, parse_sections(html))
            written = index.index_chunks(arxiv_id, title, [(c.section, c.text) for c in chunks])
            stats["papers_with_fulltext"] += 1
            stats["chunks_indexed"] += written
            if position % 25 == 0:
                print(f"  fulltext {position}/{len(tier_ids)}")
    return stats


@task
def validate(
    total_records: int,
    db_count: int,
    cards: int,
    tier_size: int,
    fulltext_stats: dict[str, int],
) -> str:
    index = _open_index()
    qdrant_cards = index.count(layer=ABSTRACT_LAYER)
    qdrant_chunks = index.count(layer=FULLTEXT_LAYER)
    withdrawn = total_records - cards
    report = (
        f"# Ingest report\n\n"
        f"| stage | count |\n|---|---|\n"
        f"| snapshot records | {total_records} |\n"
        f"| papers in DuckDB | {db_count} |\n"
        f"| withdrawn (flagged in DuckDB, excluded from index) | {withdrawn} |\n"
        f"| abstract cards indexed | {cards} (in Qdrant: {qdrant_cards}) |\n"
        f"| full-text tier size | {tier_size} |\n"
        f"| papers with full text | {fulltext_stats['papers_with_fulltext']} |\n"
        f"| papers without HTML | {fulltext_stats['papers_without_html']} |\n"
        f"| section chunks indexed | {fulltext_stats['chunks_indexed']}"
        f" (in Qdrant: {qdrant_chunks}) |\n"
    )
    # publish the diagnostic table even when the checks below fail the run
    create_markdown_artifact(markdown=report, key="ingest-report")
    if db_count != total_records:
        raise RuntimeError(f"DuckDB holds {db_count} papers, snapshot has {total_records}")
    if qdrant_cards != cards:
        raise RuntimeError(f"Qdrant abstract cards {qdrant_cards} != indexed {cards}")
    if qdrant_chunks != fulltext_stats["chunks_indexed"]:
        raise RuntimeError(
            f"Qdrant chunks {qdrant_chunks} != indexed {fulltext_stats['chunks_indexed']}"
            " — stale points survived pruning"
        )
    return report


@flow(name="papertrace-ingest")
def ingest_snapshot(
    snapshot_dir: Path = Path("data/snapshot"),
    fulltext_budget: int | None = None,
) -> None:
    budget = load_settings().fulltext_budget if fulltext_budget is None else fulltext_budget

    records, window_end = load_snapshot(snapshot_dir)
    records = normalize_records(records)
    db_count = load_metadata_store(records)
    tier_ids = select_fulltext_tier(records, budget, window_end)
    cards = index_abstract_cards(records)
    fulltext_stats = index_fulltext_tier(records, tier_ids)
    report = validate(len(records), db_count, cards, len(tier_ids), fulltext_stats)
    print("\n" + report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/snapshot"))
    parser.add_argument("--fulltext-budget", type=int, default=None)
    args = parser.parse_args()
    ingest_snapshot(snapshot_dir=args.snapshot, fulltext_budget=args.fulltext_budget)


if __name__ == "__main__":
    main()
