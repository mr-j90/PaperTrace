"""Local dense embeddings (SPEC §5: embeddings stay local; the chat LLM is the only paid API)."""

from collections.abc import Callable

Embedder = Callable[[list[str]], list[list[float]]]


def load_embedder(model_name: str) -> Embedder:
    """Load a sentence-transformers model lazily so tests never import torch."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def embed(texts: list[str]) -> list[list[float]]:
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [vector.tolist() for vector in vectors]

    return embed
