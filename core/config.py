"""Runtime configuration, environment-driven (SPEC §5: Claude default, env-swappable)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAPERTRACE_", env_file=".env", extra="ignore")

    # provider:model for langchain init_chat_model; one env change swaps providers
    chat_model: str = "anthropic:claude-haiku-4-5"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384  # must match embedding_model's output size
    sparse_model: str = "Qdrant/bm25"  # fastembed sparse model; IDF applied by Qdrant
    rerank_model: str = "BAAI/bge-reranker-base"  # local cross-encoder
    rerank_candidates: int = 30  # fused pool rescored down to search_k
    max_per_paper: int = 3  # evidence dedup cap per paper
    qdrant_url: str = "http://localhost:6333"
    collection: str = "papers"
    search_k: int = 8
    max_turns: int = 10  # model turns in the evidence loop before giving up
    duckdb_path: str = "data/papers.duckdb"
    fulltext_budget: int = 2000  # SPEC §4: hybrid tier size; tiny values for quick runs
    s2_api_key: str | None = None  # Semantic Scholar; optional, unauthenticated works


def load_settings() -> Settings:
    return Settings()
