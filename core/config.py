"""Runtime configuration, environment-driven (SPEC §5: Claude default, env-swappable)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAPERTRACE_", env_file=".env", extra="ignore")

    # provider:model for langchain init_chat_model; one env change swaps providers
    chat_model: str = "anthropic:claude-haiku-4-5"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384  # must match embedding_model's output size
    qdrant_url: str = "http://localhost:6333"
    collection: str = "papers"
    search_k: int = 8
    max_turns: int = 6  # model turns in the evidence loop before giving up


def load_settings() -> Settings:
    return Settings()
