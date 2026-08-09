"""Normalize snapshot records: dedupe, flag withdrawals, validate required fields."""

from typing import Any

REQUIRED = ("arxiv_id", "title", "abstract", "authors", "categories", "submitted", "topics")

# arXiv withdrawals replace the abstract of the new version with a notice; the
# snapshot carries no version history, so this heuristic stands in until the
# delta refresh (#10) flags withdrawals from version data.
_WITHDRAWAL_MARKERS = ("has been withdrawn", "paper is withdrawn", "article is withdrawn")


def is_withdrawn(abstract: str, comment: str | None = None) -> bool:
    head = abstract[:300].lower()
    if any(marker in head for marker in _WITHDRAWAL_MARKERS):
        return True
    # arXiv puts withdrawal notices in the comment field of the new version
    return bool(comment) and "withdrawn" in str(comment).lower()


def normalize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for record in records:
        missing = [f for f in REQUIRED if not record.get(f)]
        if missing:
            raise ValueError(f"record {record.get('arxiv_id', '?')} missing fields: {missing}")
        record = {
            **record,
            "withdrawn": is_withdrawn(str(record["abstract"]), record.get("comment")),
        }
        record.setdefault("doi", None)
        record.setdefault("comment", None)
        record.setdefault("updated", None)
        record.setdefault("primary_category", None)
        seen[str(record["arxiv_id"])] = record
    return sorted(seen.values(), key=lambda r: str(r["arxiv_id"]))
