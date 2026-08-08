"""Agent tools (SPEC §5). Tracer ships semantic_search; metadata_query arrives with #6."""

import json

from langchain_core.tools import BaseTool, tool

from core.retrieval import SemanticIndex


def make_semantic_search(index: SemanticIndex, k: int) -> BaseTool:
    @tool
    def semantic_search(query: str) -> str:
        """Search the paper corpus by meaning. Returns matching papers as JSON:
        arxiv_id, title, snippet, score. Cite papers by their arxiv_id."""
        evidence = index.search(query, k)
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
