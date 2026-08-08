"""Tracer indexer: pinned snapshot -> abstract cards in Qdrant (dense-only).

Superseded by the Prefect flow in #4; kept minimal on purpose.

Usage:
    uv run python -m ingest.index_abstracts               # index the full snapshot
    uv run python -m ingest.index_abstracts --limit 1500  # a slice, for quick starts
"""

import argparse
import gzip
import json
from pathlib import Path

from core.config import load_settings
from core.retrieval import SemanticIndex

BATCH = 256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--snapshot", type=Path, default=Path("data/snapshot/metadata.jsonl.gz"))
    args = parser.parse_args()

    settings = load_settings()
    index = SemanticIndex.from_settings(settings)
    index.ensure_collection()

    with gzip.open(args.snapshot, "rt", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    if args.limit is not None:
        records = records[: args.limit]

    indexed = 0
    for i in range(0, len(records), BATCH):
        indexed += index.index_abstracts(records[i : i + BATCH])
        print(f"  indexed {indexed}/{len(records)}", end="\r")
    print(f"\nabstract cards in collection '{settings.collection}': {index.count()}")


if __name__ == "__main__":
    main()
