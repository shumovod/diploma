from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    perplexity_api_key: str = ""
    perplexity_sonar_model: str = "sonar"
    perplexity_timeout_seconds: float = 120.0
    perplexity_search_context_size: str = "high"

    chroma_persist_directory: str = "./chroma_data"
    chroma_collection_name: str = "student_helper_kb"

    rag_retrieve_k: int = 4
    rag_min_docs_chars: int = 80
    rag_ingest_max_chars: int = 360
    rag_ingest_chunk_overlap: int = 40

    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
