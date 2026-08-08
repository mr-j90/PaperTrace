"""Full-text tier selection (SPEC §4): a hybrid of recency and citations at every budget.

Half the budget goes to recency (newest first), half to top-cited (highest first);
if either side has fewer candidates than its half, the other absorbs the slack. This
keeps the tier genuinely hybrid even when the trailing window alone exceeds the budget.
"""

import time
from datetime import date, timedelta
from typing import Any

import httpx

S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_BATCH_SIZE = 500
S2_DELAY_S = 1.1
S2_RETRIES = 3
RECENT_DAYS = 183  # the "trailing ~6 months" recency rule


def split_by_recency(
    records: list[dict[str, Any]], window_end: date
) -> tuple[list[str], list[str]]:
    """(recent_ids newest-first, rest_ids) for live (non-withdrawn) papers."""
    cutoff = (window_end - timedelta(days=RECENT_DAYS)).isoformat()
    live = [r for r in records if not r.get("withdrawn")]
    recent = sorted(
        (r for r in live if str(r["submitted"])[:10] >= cutoff),
        key=lambda r: str(r["submitted"]),
        reverse=True,
    )
    rest = [r for r in live if str(r["submitted"])[:10] < cutoff]
    return [str(r["arxiv_id"]) for r in recent], [str(r["arxiv_id"]) for r in rest]


def select_tier(
    recent_ids: list[str],
    rest_ids: list[str],
    budget: int,
    citations: dict[str, int],
) -> list[str]:
    cited_ranked = sorted(rest_ids, key=lambda aid: (-citations.get(aid, 0), aid))
    recent_share = budget // 2 + budget % 2  # recency gets the odd slot
    # either side's unused share flows to the other
    recent_take = min(len(recent_ids), max(recent_share, budget - len(cited_ranked)))
    cited_take = min(len(cited_ranked), budget - recent_take)
    recent_take = min(len(recent_ids), budget - cited_take)
    return recent_ids[:recent_take] + cited_ranked[:cited_take]


def fetch_citation_counts(
    arxiv_ids: list[str], api_key: str | None = None, client: httpx.Client | None = None
) -> dict[str, int]:
    """Citation counts from Semantic Scholar's batch API; zeros where unavailable.

    Any malformed or failed batch degrades to zero counts for that batch (tier
    selection then leans on recency) — loudly, never fatally.
    """
    counts: dict[str, int] = dict.fromkeys(arxiv_ids, 0)
    headers = {"x-api-key": api_key} if api_key else {}
    own_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        for start in range(0, len(arxiv_ids), S2_BATCH_SIZE):
            batch = arxiv_ids[start : start + S2_BATCH_SIZE]
            applied = False
            for attempt in range(1, S2_RETRIES + 1):
                time.sleep(S2_DELAY_S)
                try:
                    response = client.post(
                        S2_BATCH_URL,
                        params={"fields": "citationCount"},
                        json={"ids": [f"ARXIV:{aid}" for aid in batch]},
                        headers=headers,
                    )
                    if response.status_code != 200:
                        raise ValueError(f"HTTP {response.status_code}")
                    payload = response.json()
                    if not isinstance(payload, list) or len(payload) != len(batch):
                        raise ValueError("payload shape mismatch")
                    for aid, item in zip(batch, payload, strict=True):
                        if isinstance(item, dict) and item.get("citationCount") is not None:
                            counts[aid] = int(item["citationCount"])
                    applied = True
                    break
                except (httpx.HTTPError, ValueError, TypeError, KeyError):
                    time.sleep(5.0 * attempt)
            if not applied:
                print(f"  S2 batch at {start} failed after {S2_RETRIES} tries; zeros used")
    finally:
        if own_client:
            client.close()
    return counts
