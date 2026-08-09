"""Local cross-encoder re-ranking (SPEC §5): rescores fused candidates to final evidence.

Doubles as the PaperQA2-style evidence rescoring step — the rubric's re-ranking
best-practice point, with the eval delta demonstrated in the 4-way ladder (#9).
"""

from collections.abc import Callable

Reranker = Callable[[str, list[str]], list[float]]
"""(query, candidate_texts) -> relevance score per candidate, higher is better."""


def load_reranker(model_name: str) -> Reranker:
    """Load a cross-encoder lazily so tests never import torch."""
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name, device="cpu")  # see embeddings.py: MPS + threads segfault

    def rerank(query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        scores = model.predict([(query, text) for text in texts], show_progress_bar=False)
        return [float(score) for score in scores]

    return rerank
