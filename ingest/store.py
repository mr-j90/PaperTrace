"""DuckDB metadata store: every corpus paper, queryable (SPEC §4/§5)."""

from pathlib import Path
from typing import Any

import duckdb

SCHEMA = """
CREATE OR REPLACE TABLE papers (
    arxiv_id         VARCHAR PRIMARY KEY,
    title            VARCHAR NOT NULL,
    abstract         VARCHAR NOT NULL,
    authors          VARCHAR[] NOT NULL,
    primary_category VARCHAR,
    categories       VARCHAR[] NOT NULL,
    submitted        TIMESTAMP NOT NULL,
    updated          TIMESTAMP,
    doi              VARCHAR,
    topics           VARCHAR[] NOT NULL,
    withdrawn        BOOLEAN NOT NULL DEFAULT FALSE
)
"""


def load_papers(records: list[dict[str, Any]], db_path: Path) -> int:
    """(Re)create the papers table from normalized records. Idempotent by construction."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute(SCHEMA)
        con.executemany(
            "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r["arxiv_id"],
                    r["title"],
                    r["abstract"],
                    r["authors"],
                    r["primary_category"],
                    r["categories"],
                    r["submitted"],
                    r["updated"],
                    r["doi"],
                    r["topics"],
                    r["withdrawn"],
                )
                for r in records
            ],
        )
        count: int = con.execute("SELECT count(*) FROM papers").fetchone()[0]  # type: ignore[index]
    return count


def paper_count(db_path: Path) -> int:
    with duckdb.connect(str(db_path), read_only=True) as con:
        count: int = con.execute("SELECT count(*) FROM papers").fetchone()[0]  # type: ignore[index]
    return count
