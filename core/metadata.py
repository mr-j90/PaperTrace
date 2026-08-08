"""The metadata query engine (SPEC §5): typed filters -> SQL built by the tool, never the LLM.

Answers analytical questions (counts, groupings, listings) and freshness questions
(date-filtered) over the DuckDB papers store. Every parameter is bound — the LLM
supplies values only, so tool-arg exact-match and execution accuracy stay cheap to
evaluate (#9) and injection is impossible by construction.
"""

import time
from pathlib import Path
from typing import Any, Literal

import duckdb

GroupBy = Literal["month", "year", "topic", "category"]
Sort = Literal["newest", "oldest", "title"]

MAX_LIMIT = 50

_GROUP_EXPR: dict[str, str] = {
    "month": "strftime(submitted, '%Y-%m')",
    "year": "strftime(submitted, '%Y')",
    "topic": "topic",  # via unnest subquery
    "category": "primary_category",
}
_SORT_EXPR: dict[str, str] = {
    "newest": "submitted DESC",
    "oldest": "submitted ASC",
    "title": "title ASC",
}


def _build_where(
    *,
    topic: str | None,
    category: str | None,
    author: str | None,
    title_contains: str | None,
    arxiv_id: str | None,
    submitted_from: str | None,
    submitted_to: str | None,
    include_withdrawn: bool,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_withdrawn:
        clauses.append("NOT withdrawn")
    if topic:
        clauses.append("list_contains(topics, ?)")
        params.append(topic)
    if category:
        clauses.append("(primary_category = ? OR list_contains(categories, ?))")
        params.extend([category, category])
    if author:
        clauses.append("len(list_filter(authors, a -> a ILIKE '%' || ? || '%')) > 0")
        params.append(author)
    if title_contains:
        clauses.append("title ILIKE '%' || ? || '%'")
        params.append(title_contains)
    if arxiv_id:
        clauses.append("arxiv_id = ?")
        params.append(arxiv_id)
    if submitted_from:
        clauses.append("submitted >= CAST(? AS TIMESTAMP)")
        params.append(submitted_from)
    if submitted_to:
        clauses.append("submitted < CAST(? AS TIMESTAMP) + INTERVAL 1 DAY")
        params.append(submitted_to)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


class MetadataStore:
    """Read-only analytical queries over the papers table built by the ingest flow."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def query(
        self,
        *,
        topic: str | None = None,
        category: str | None = None,
        author: str | None = None,
        title_contains: str | None = None,
        arxiv_id: str | None = None,
        submitted_from: str | None = None,
        submitted_to: str | None = None,
        include_withdrawn: bool = False,
        group_by: GroupBy | None = None,
        sort: Sort = "newest",
        limit: int = 20,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), MAX_LIMIT))
        where, params = _build_where(
            topic=topic,
            category=category,
            author=author,
            title_contains=title_contains,
            arxiv_id=arxiv_id,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            include_withdrawn=include_withdrawn,
        )

        if group_by is not None and group_by not in _GROUP_EXPR:
            raise ValueError(f"group_by must be one of {sorted(_GROUP_EXPR)}")
        if sort not in _SORT_EXPR:
            raise ValueError(f"sort must be one of {sorted(_SORT_EXPR)}")
        if group_by == "topic":
            sql = (
                f"SELECT topic AS grp, count(*) AS n FROM "
                f"(SELECT unnest(topics) AS topic, * FROM papers {where}) "
                f"GROUP BY 1 ORDER BY 2 DESC, 1"
            )
        elif group_by:
            sql = (
                f"SELECT {_GROUP_EXPR[group_by]} AS grp, count(*) AS n "
                f"FROM papers {where} GROUP BY 1 ORDER BY 1"
            )
        else:
            sql = (
                f"SELECT arxiv_id, title, authors[1:3] AS authors, "
                f"strftime(submitted, '%Y-%m-%d') AS submitted, topics "
                f"FROM papers {where} ORDER BY {_SORT_EXPR[sort]} LIMIT {limit}"
            )
        total_sql = f"SELECT count(*) FROM papers {where}"

        # DuckDB is single-writer: reads fail while the ingest flow holds the file.
        # Retry briefly, then degrade to a tool-level error the agent can relay.
        for attempt in range(3):
            try:
                with duckdb.connect(str(self._db_path), read_only=True) as con:
                    row = con.execute(total_sql, params).fetchone()
                    total = int(row[0]) if row else 0
                    cursor = con.execute(sql, params)
                    columns = [d[0] for d in cursor.description or []]
                    rows = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
                break
            except duckdb.Error:
                if attempt == 2:
                    return {
                        "total": 0,
                        "rows": [],
                        "error": "metadata store unavailable — ingestion may be running "
                        "or has not been run yet; try again shortly",
                    }
                time.sleep(0.5 * (attempt + 1))

        result: dict[str, Any] = {"total": total, "rows": rows, "sql": sql}
        if arxiv_id and total == 0:
            result["note"] = (
                f"arxiv_id {arxiv_id} is not in the corpus — it may be outside the "
                "topical scope or newer than the latest ingest"
            )
        return result
