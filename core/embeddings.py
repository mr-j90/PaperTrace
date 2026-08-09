"""Local embedding models (SPEC §5: retrieval stays local; the chat LLM is the only paid API)."""

from collections.abc import Callable
from dataclasses import dataclass

Embedder = Callable[[list[str]], list[list[float]]]

SparseVec = tuple[list[int], list[float]]  # (indices, values)


@dataclass
class SparseEmbedder:
    """BM25-style sparse vectors; doc and query sides weight differently."""

    embed_docs: Callable[[list[str]], list[SparseVec]]
    embed_query: Callable[[str], SparseVec]


def load_embedder(model_name: str) -> Embedder:
    """Load a sentence-transformers model lazily so tests never import torch."""
    from sentence_transformers import SentenceTransformer

    # explicit CPU: MPS segfaults when tools run in executor threads, and every
    # deploy target is CPU-only anyway
    model = SentenceTransformer(model_name, device="cpu")

    def embed(texts: list[str]) -> list[list[float]]:
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [vector.tolist() for vector in vectors]

    return embed


def load_sparse_embedder(model_name: str) -> SparseEmbedder:
    """fastembed BM25 term weights; Qdrant applies IDF server-side (Modifier.IDF)."""
    from fastembed import SparseTextEmbedding

    model = SparseTextEmbedding(model_name)

    def embed_docs(texts: list[str]) -> list[SparseVec]:
        return [(e.indices.tolist(), e.values.tolist()) for e in model.embed(texts)]

    def embed_query(text: str) -> SparseVec:
        [e] = list(model.query_embed(text))
        return (e.indices.tolist(), e.values.tolist())

    return SparseEmbedder(embed_docs=embed_docs, embed_query=embed_query)
