"""Build the pinned corpus snapshot from the committed query definitions (SPEC §4).

Harvests CC0 metadata + abstracts for every paper matching data/queries.toml from the
arXiv API, politely: one connection, >=3s between requests (API ToU; bursting earns a
sticky HTTP 429). Writes the snapshot artifacts that evals and reviewers build against.

Usage:
    uv run python -m ingest.snapshot            # full snapshot (a few minutes)
    uv run python -m ingest.snapshot --limit 50 # smoke run, 50 papers per topic
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "PaperTrace-snapshot/0.1 (+https://github.com/mr-j90/PaperTrace)"
REQUEST_DELAY_S = 3.1  # API ToU: no more than one request every 3 seconds
PAGE_SIZE = 1000  # API allows slices of at most 2000
MAX_RETRIES = 5
RETRY_BACKOFF_S = 30.0  # a 429 block persists for minutes; back off hard

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}


@dataclass
class Window:
    start: str  # YYYY-MM-DD, inclusive
    end: str  # YYYY-MM-DD, exclusive cutoff


@dataclass
class Topic:
    name: str
    field: str  # arXiv query field prefix: "abs", "ti", "all", ...
    phrases: list[str]


@dataclass
class Paper:
    arxiv_id: str  # versionless, e.g. "2005.11401"
    title: str
    abstract: str
    authors: list[str]
    primary_category: str
    categories: list[str]
    submitted: str  # ISO date of v1 (Atom <published>)
    updated: str  # ISO date of latest version seen
    doi: str | None
    topics: list[str]  # which query topics matched this paper


def load_queries(path: Path) -> tuple[Window, list[Topic]]:
    raw = tomllib.loads(path.read_text())
    window = Window(**raw["window"])
    topics = [Topic(**t) for t in raw["topics"]]
    return window, topics


def _compact(date: str) -> str:
    return date.replace("-", "") + "0000"


def build_search_query(topic: Topic, window: Window) -> str:
    phrases = " OR ".join(f'{topic.field}:"{p}"' for p in topic.phrases)
    dates = f"submittedDate:[{_compact(window.start)} TO {_compact(window.end)}]"
    return f"({phrases}) AND {dates}"


def _text(entry: ET.Element, tag: str) -> str:
    value = entry.findtext(tag, default="", namespaces=NS)
    return " ".join(value.split())


def parse_page(xml_text: str) -> tuple[int, list[Paper]]:
    """Parse one Atom page into (totalResults, papers). Topics are filled by the caller."""
    root = ET.fromstring(xml_text)
    total = int(root.findtext("opensearch:totalResults", default="0", namespaces=NS))
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", NS):
        raw_id = _text(entry, "atom:id")  # http://arxiv.org/abs/2005.11401v4
        versioned = raw_id.rsplit("/abs/", 1)[-1]
        arxiv_id = versioned.rsplit("v", 1)[0] if "v" in versioned.split("/")[-1] else versioned
        primary = entry.find("arxiv:primary_category", NS)
        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=_text(entry, "atom:title"),
                abstract=_text(entry, "atom:summary"),
                authors=[
                    " ".join((a.findtext("atom:name", default="", namespaces=NS)).split())
                    for a in entry.findall("atom:author", NS)
                ],
                primary_category=primary.get("term", "") if primary is not None else "",
                categories=[c.get("term", "") for c in entry.findall("atom:category", NS)],
                submitted=_text(entry, "atom:published"),
                updated=_text(entry, "atom:updated"),
                doi=_text(entry, "arxiv:doi") or None,
                topics=[],
            )
        )
    return total, papers


def _get_page(
    client: httpx.Client, params: dict[str, str | int], start: int
) -> tuple[int, list[Paper]]:
    """Fetch and parse one page, retrying flakes.

    An empty 200 while `start < totalResults` is arXiv's known transient flake
    mid-pagination — retried, never accepted, so a topic can't truncate silently.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY_S)
        reason = ""
        try:
            response = client.get(API_URL, params=params)
            if response.status_code == 200:
                total, page = parse_page(response.text)
                if page or start >= total:
                    return total, page
                reason = f"empty page at start={start} (total={total})"
            else:
                reason = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            reason = f"network error: {exc}"
        wait = RETRY_BACKOFF_S * attempt
        print(f"    retry {attempt}/{MAX_RETRIES} after {reason}; sleeping {wait:.0f}s")
        time.sleep(wait)
    raise RuntimeError(f"arXiv API failed after {MAX_RETRIES} retries: {params}")


def fetch_topic(
    client: httpx.Client, topic: Topic, window: Window, limit: int | None
) -> tuple[int, list[Paper]]:
    """Fetch a topic's full result set, deduplicated, over stable pagination.

    sortBy=submittedDate pins a deterministic order; the API's default relevance
    sort shifts between paged requests, yielding duplicates and silent misses.
    """
    query = build_search_query(topic, window)
    by_id: dict[str, Paper] = {}
    total = 0
    start = 0
    while True:
        page_size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(by_id))
        if page_size <= 0:
            break
        total, page = _get_page(
            client,
            {
                "search_query": query,
                "start": start,
                "max_results": page_size,
                "sortBy": "submittedDate",
                "sortOrder": "ascending",
            },
            start,
        )
        if not page:
            break
        for paper in page:
            paper.topics = [topic.name]
            by_id.setdefault(paper.arxiv_id, paper)
        start += len(page)
        print(f"    {topic.name}: {len(by_id)}/{total if limit is None else limit}")
        if start >= total:
            break
    return total, list(by_id.values())


def merge(per_topic: dict[str, list[Paper]]) -> list[Paper]:
    by_id: dict[str, Paper] = {}
    for papers in per_topic.values():
        for paper in papers:
            held = by_id.get(paper.arxiv_id)
            if held is None:
                by_id[paper.arxiv_id] = paper
            else:
                held.topics = sorted(set(held.topics) | set(paper.topics))
    return sorted(by_id.values(), key=lambda p: p.arxiv_id)


def write_snapshot(
    out_dir: Path,
    corpus: list[Paper],
    window: Window,
    api_totals: dict[str, int],
    queries: dict[str, str],
    limit: int | None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_dir / "metadata.jsonl.gz", "wt", encoding="utf-8") as fh:
        for paper in corpus:
            fh.write(json.dumps(asdict(paper), ensure_ascii=False) + "\n")
    (out_dir / "arxiv_ids.txt").write_text("".join(p.arxiv_id + "\n" for p in corpus))
    per_topic = {
        name: {
            "query": queries[name],
            "api_total": api_totals[name],
            "in_corpus": sum(1 for p in corpus if name in p.topics),
        }
        for name in queries
    }
    if limit is None:
        short = {n: t for n, t in per_topic.items() if t["in_corpus"] != t["api_total"]}
        if short:
            raise RuntimeError(f"fetched != api_total for topics {sorted(short)}: {short}")
    manifest = {
        "snapshot_date": datetime.now(UTC).date().isoformat(),
        "window": asdict(window),
        "smoke_limit": limit,
        "topics": per_topic,
        "total_unique": len(corpus),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="max papers per topic (smoke)")
    parser.add_argument("--out", type=Path, default=Path("data/snapshot"))
    parser.add_argument("--queries", type=Path, default=Path("data/queries.toml"))
    args = parser.parse_args()

    window, topics = load_queries(args.queries)
    queries = {t.name: build_search_query(t, window) for t in topics}
    api_totals: dict[str, int] = {}
    per_topic: dict[str, list[Paper]] = {}

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        for topic in topics:
            print(f"fetching topic '{topic.name}': {queries[topic.name]}")
            api_totals[topic.name], per_topic[topic.name] = fetch_topic(
                client, topic, window, args.limit
            )

    corpus = merge(per_topic)
    write_snapshot(args.out, corpus, window, api_totals, queries, args.limit)

    print(f"\nsnapshot written to {args.out}/")
    for name, total in api_totals.items():
        print(f"  {name}: api_total={total} fetched={len(per_topic[name])}")
    print(f"  total unique papers: {len(corpus)}")
    if args.limit is not None:
        print("  NOTE: smoke run (--limit) — do not commit these artifacts")


if __name__ == "__main__":
    main()
