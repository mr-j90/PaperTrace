"""Agent tools (SPEC §5). semantic_search final form; metadata_query arrives with #6."""

import json

from langchain_core.tools import BaseTool, tool

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
