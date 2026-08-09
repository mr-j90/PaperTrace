"""Generate the ground-truth sets (SPEC §6) from the pinned snapshot.

Four JSONL files under eval/ground_truth/, every record labeled with its expected
tool. Retrieval/synthesis questions are LLM-written from abstracts (then
hand-checked — the manifest records that pass); analytical/freshness questions are
templated with expected answers computed directly from the metadata store, so their
ground truth is exact by construction.

Usage:
    uv run python -m eval.generate_ground_truth            # full sets (~$0.20, minutes)
    uv run python -m eval.generate_ground_truth --retrieval 10 --synthesis 3
"""

import argparse
import gzip
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from core.config import load_settings
from core.metadata import MetadataStore

GENERATOR_MODEL = "anthropic:claude-haiku-4-5"
SEED = 20260809  # deterministic sampling; regeneration reproduces the same papers

RETRIEVAL_PROMPT = """\
Write one natural research question that this paper's abstract answers. The question
must be answerable from the abstract alone, must NOT quote distinctive phrases
verbatim (paraphrase!), and must not mention the paper or authors by name.
Return ONLY the question text.

Title: {title}
Abstract: {abstract}"""

SYNTHESIS_PROMPT = """\
Write one natural research question that would require BOTH of these papers to answer
well (compare/contrast or combine their contributions). Do not mention titles or
authors; do not quote verbatim. Return ONLY the question text.

Paper A: {title_a} — {abstract_a}

Paper B: {title_b} — {abstract_b}"""


def load_records() -> tuple[list[dict[str, Any]], str]:
    with gzip.open("data/snapshot/metadata.jsonl.gz", "rt", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    manifest = json.loads(Path("data/snapshot/manifest.json").read_text())
    return records, manifest["window"]["end"]


def llm_questions(
    records: list[dict[str, Any]], n_retrieval: int, n_synthesis: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from langchain.chat_models import init_chat_model

    model = init_chat_model(GENERATOR_MODEL)
    rng = random.Random(SEED)
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        for t in r["topics"]:
            by_topic.setdefault(t, []).append(r)

    # stratified sample proportional to topic size, newest-biased for readability
    weights = {t: len(v) for t, v in by_topic.items()}
    total = sum(weights.values())
    picks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for topic, papers in by_topic.items():
        quota = max(2, round(n_retrieval * weights[topic] / total))
        for r in rng.sample(papers, min(quota, len(papers))):
            if r["arxiv_id"] not in seen:
                seen.add(r["arxiv_id"])
                picks.append(r)
    picks = picks[:n_retrieval]

    retrieval = []
    for i, r in enumerate(picks, 1):
        q = model.invoke(
            RETRIEVAL_PROMPT.format(title=r["title"], abstract=r["abstract"][:1500])
        ).text.strip()
        retrieval.append(
            {
                "q": q,
                "source_arxiv_id": r["arxiv_id"],
                "layer": "abstract",
                "topics": r["topics"],
                "expected_tool": "semantic_search",
            }
        )
        if i % 20 == 0:
            print(f"  retrieval {i}/{len(picks)}")

    synthesis = []
    topics = [t for t in by_topic if len(by_topic[t]) >= 2]
    for i in range(n_synthesis):
        topic = topics[i % len(topics)]
        a, b = rng.sample(by_topic[topic], 2)
        q = model.invoke(
            SYNTHESIS_PROMPT.format(
                title_a=a["title"],
                abstract_a=a["abstract"][:900],
                title_b=b["title"],
                abstract_b=b["abstract"][:900],
            )
        ).text.strip()
        synthesis.append(
            {
                "q": q,
                "expected_paper_ids": [a["arxiv_id"], b["arxiv_id"]],
                "topic": topic,
                "expected_tool": "semantic_search",
            }
        )
    return retrieval, synthesis


def templated_questions(
    store: MetadataStore,
    records: list[dict[str, Any]],
    window_end: str,
    n_analytical: int,
    n_freshness: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(SEED)
    end = datetime.fromisoformat(window_end)
    topics = ["rag", "agents", "eval", "llmops"]
    analytical: list[dict[str, Any]] = []

    def add(q: str, args: dict[str, Any]) -> None:
        result = store.query(**args)
        analytical.append(
            {
                "q": q,
                "expected_tool": "metadata_query",
                "expected_tool_args": args,
                "expected_total": result["total"],
                "expected_rows": result["rows"] if args.get("group_by") else None,
            }
        )

    # count-in-month questions
    months = [(end - timedelta(days=30 * i)).strftime("%Y-%m") for i in range(1, 13)]
    while len(analytical) < n_analytical:
        kind = len(analytical) % 3
        topic = rng.choice(topics[:3])  # llmops is tiny; keep counts meaningful
        if kind == 0:
            month = rng.choice(months)
            first = f"{month}-01"
            # submitted_to is inclusive of the whole end day — use the month's last day
            next_first = datetime.fromisoformat(first) + timedelta(days=31)
            last_day = (next_first.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")
            add(
                f"How many {topic} papers were submitted in {month}?",
                {"topic": topic, "submitted_from": first, "submitted_to": last_day},
            )
        elif kind == 1:
            year = rng.choice(["2023", "2024", "2025"])
            add(
                f"How many papers about {topic} came out each month of {year}?",
                {
                    "topic": topic,
                    "submitted_from": f"{year}-01-01",
                    "submitted_to": f"{year}-12-31",
                    "group_by": "month",
                },
            )
        else:
            author = rng.choice([r["authors"][0] for r in rng.sample(records, 50) if r["authors"]])
            add(f"How many papers has {author} authored in the corpus?", {"author": author})

    freshness: list[dict[str, Any]] = []
    for i in range(n_freshness):
        days = [7, 14, 30][i % 3]
        topic = topics[i % len(topics)]
        since = (end - timedelta(days=days)).strftime("%Y-%m-%d")
        args: dict[str, Any] = {"topic": topic, "submitted_from": since}
        result = store.query(**args)
        freshness.append(
            {
                "q": f"What's new in {topic} since {since}?",
                "expected_tool": "metadata_query",
                "expected_tool_args": args,
                "expected_total": result["total"],
            }
        )
    return analytical, freshness


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval", type=int, default=140)
    parser.add_argument("--synthesis", type=int, default=25)
    parser.add_argument("--analytical", type=int, default=25)
    parser.add_argument("--freshness", type=int, default=10)
    args = parser.parse_args()

    records, window_end = load_records()
    store = MetadataStore(Path(load_settings().duckdb_path))

    print("templated sets (exact by construction)...")
    analytical, freshness = templated_questions(
        store, records, window_end, args.analytical, args.freshness
    )
    print(f"  analytical={len(analytical)} freshness={len(freshness)}")

    print("LLM-written sets (hand-check required)...")
    retrieval, synthesis = llm_questions(records, args.retrieval, args.synthesis)

    out = Path("eval/ground_truth")
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in [
        ("retrieval", retrieval),
        ("synthesis", synthesis),
        ("analytical", analytical),
        ("freshness", freshness),
    ]:
        if not rows:  # requested 0: leave the committed set untouched
            print(f"  skipped {name}.jsonl (0 requested)")
            continue
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  wrote {name}.jsonl ({len(rows)})")

    previous = Path("eval/ground_truth/manifest.json")
    hand_check: Any = "pending"
    if previous.exists():
        hand_check = json.loads(previous.read_text()).get("hand_check", "pending")
    manifest = {
        "generated": datetime.now(UTC).date().isoformat(),
        "snapshot_window_end": window_end,
        "generator_model": GENERATOR_MODEL,
        "seed": SEED,
        "counts": {
            name: len((out / f"{name}.jsonl").read_text().splitlines())
            for name in ("retrieval", "synthesis", "analytical", "freshness")
        },
        "hand_check": hand_check,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("manifest written (hand_check: " + str(manifest["hand_check"]) + ")")


if __name__ == "__main__":
    main()
