"""Agent tools (SPEC §5): semantic_search over the layered index, metadata_query over DuckDB."""

import json

from langchain_core.tools import BaseTool, tool

from core.metadata import GroupBy, MetadataStore, Sort
from core.retrieval import Scope, SemanticIndex


def make_semantic_search(index: SemanticIndex, k: int) -> BaseTool:
    @tool
    def semantic_search(query: str, scope: Scope = "all") -> str:
        """Search the paper corpus by meaning (hybrid keyword+vector, reranked).

        scope: "abstracts" searches every paper's abstract card; "fulltext" searches
        section-level passages of the full-text tier; "all" (default) searches both.
        Returns matching papers as JSON: arxiv_id, title, snippet, score.
        Cite papers by their arxiv_id."""
        evidence = index.search(query, k, scope=scope)
        return json.dumps(
            [
                {
                    "arxiv_id": e.arxiv_id,
                    "title": e.title,
                    "snippet": e.snippet,
                    "score": round(e.score, 4),
                }
                for e in evidence
            ]
        )

    return semantic_search


def make_metadata_query(store: MetadataStore) -> BaseTool:
    @tool
    def metadata_query(
        topic: str | None = None,
        category: str | None = None,
        author: str | None = None,
        title_contains: str | None = None,
        arxiv_id: str | None = None,
        submitted_from: str | None = None,
        submitted_to: str | None = None,
        group_by: GroupBy | None = None,
        sort: Sort = "newest",
        limit: int = 20,
    ) -> str:
        """Answer analytical questions about the paper corpus with exact numbers:
        counts, groupings, and listings over paper metadata. Use this (not
        semantic_search) for "how many", "per month/year", "latest papers",
        "papers by <author>", and "what's new since <date>" questions.

        topic: one of rag | agents | eval | llmops. category: an arXiv category
        like cs.CL. author: name substring. submitted_from/submitted_to:
        YYYY-MM-DD (inclusive). group_by month|year|topic|category returns
        grouped counts; otherwise returns up to `limit` matching papers.
        The result's `total` is the exact count of matching papers (withdrawn
        papers excluded). Note: group_by=topic counts a paper once per topic it
        carries, so topic sums can exceed `total`. Cite listed papers by their
        arxiv_id."""
        result = store.query(
            topic=topic,
            category=category,
            author=author,
            title_contains=title_contains,
            arxiv_id=arxiv_id,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
            group_by=group_by,
            sort=sort,
            limit=limit,
        )
        return json.dumps(result, default=str)

    return metadata_query
