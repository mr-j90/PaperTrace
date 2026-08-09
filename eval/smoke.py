"""CI smoke slice (SPEC §6): free, fast, fails on regression. No paid API.

- Retrieval: 30 ground-truth questions against an in-memory Qdrant holding the
  source papers + distractors, real local embedders (bge dense + BM25 sparse),
  dense/sparse/hybrid rungs (the reranker download is too heavy for CI).
- Execution accuracy: every analytical/freshness expectation re-checked against a
  DuckDB store rebuilt from the committed snapshot.

Thresholds are deliberately below observed values — they gate regressions, not noise.
"""

import gzip
import json
import random
import sys
from pathlib import Path

from core.embeddings import load_embedder, load_sparse_embedder
from core.metadata import MetadataStore
from core.retrieval import SemanticIndex
from ingest.normalize import normalize
from ingest.store import load_papers

N_QUESTIONS = 30
N_DISTRACTORS = 300
THRESHOLDS = {"hybrid_hit": 0.8, "hybrid_beats_or_ties_worst": True, "execution": 1.0}


def retrieval_smoke() -> bool:
    from qdrant_client import QdrantClient

    questions = [
        json.loads(line)
        for line in Path("eval/ground_truth/retrieval.jsonl").read_text().splitlines()
    ][:N_QUESTIONS]
    with gzip.open("data/snapshot/metadata.jsonl.gz", "rt", encoding="utf-8") as fh:
        records = {r["arxiv_id"]: r for r in (json.loads(line) for line in fh)}

    keep_ids = {q["source_arxiv_id"] for q in questions}
    rng = random.Random(7)
    distractors = rng.sample([r for i, r in records.items() if i not in keep_ids], N_DISTRACTORS)
    corpus = [records[i] for i in keep_ids if i in records] + distractors

    index = SemanticIndex(
        client=QdrantClient(":memory:"),
        collection="papers",
        embed=load_embedder("BAAI/bge-small-en-v1.5"),
        dim=384,
        sparse=load_sparse_embedder("Qdrant/bm25"),
        rerank=lambda q, texts: [0.0] * len(texts),  # rerank rung not exercised in CI
    )
    index.ensure_collection()
    for start in range(0, len(corpus), 128):
        index.index_abstracts(corpus[start : start + 128])

    rates: dict[str, float] = {}
    for mode in ("sparse", "dense", "hybrid"):
        hits = sum(
            1
            for q in questions
            if q["source_arxiv_id"]
            in [e.arxiv_id for e in index.search(q["q"], 8, scope="abstracts", mode=mode)]
        )
        rates[mode] = hits / len(questions)
    print(f"retrieval smoke (n={len(questions)}, distractors={N_DISTRACTORS}): {rates}")

    ok = rates["hybrid"] >= THRESHOLDS["hybrid_hit"]
    if not ok:
        print(f"FAIL: hybrid hit-rate {rates['hybrid']} < {THRESHOLDS['hybrid_hit']}")
    if THRESHOLDS["hybrid_beats_or_ties_worst"] and rates["hybrid"] < min(rates.values()):
        print("FAIL: hybrid ranks below a single-vector mode — fusion regressed")
        ok = False
    return ok


def execution_smoke() -> bool:
    with gzip.open("data/snapshot/metadata.jsonl.gz", "rt", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    db = Path("eval/results/.smoke.duckdb")
    db.unlink(missing_ok=True)
    load_papers(normalize(records), db)
    store = MetadataStore(db)

    checked = passed = 0
    for name in ("analytical", "freshness"):
        for line in Path(f"eval/ground_truth/{name}.jsonl").read_text().splitlines():
            item = json.loads(line)
            checked += 1
            result = store.query(**item["expected_tool_args"])
            passed += result["total"] == item["expected_total"]
    rate = passed / checked
    print(f"execution smoke: {passed}/{checked}")
    if rate < THRESHOLDS["execution"]:
        print(f"FAIL: execution accuracy {rate} < {THRESHOLDS['execution']}")
    db.unlink(missing_ok=True)
    return rate >= THRESHOLDS["execution"]


def main() -> None:
    ok = execution_smoke() & retrieval_smoke()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
