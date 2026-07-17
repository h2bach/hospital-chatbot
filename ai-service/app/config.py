"""
Application configuration.

Reads settings from environment variables / .env file.
Uses @lru_cache so .env is loaded only once per process.

Supports multiple LLM providers:
    - ollama (local, free, no API key)
    - google  (Google GenAI / Gemini)
    - other   (OpenAI-compatible API endpoints)
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — every field maps to an env var."""

    # ── App ──────────────────────────────────────────────
    app_name: str = "AI Service"
    app_version: str = "1.0.0"
    debug: bool = False

    # ── Ollama ───────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # ── Google GenAI ─────────────────────────────────────
    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"

    # ── OpenAI ───────────────────────────────────────────
    openai_api_key: str = ""  # Read from OPENAI_API_KEY env var
    openai_model: str = "gpt-4o-mini"

    # ── Other Provider (OpenAI-compatible) ──────────────
    other_api_key: str = ""
    other_base_url: str = "https://api.shopaikey.com/v1"
    other_model: str = "gpt-5.4-mini-2026-03-17"

    # ── Shared LLM settings ─────────────────────────────
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_timeout: int = 30  # seconds

    # ── Data Ingestion ───────────────────────────────────
    # Vector store configuration
    vector_store_type: Literal["pinecone", "weaviate", "qdrant", "chroma"] = "chroma"
    vector_store_url: str = "http://localhost:8001"
    vector_store_api_key: str = ""

    # Embedding configuration
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.shopaikey.com/v1"
    embedding_model: str = "text-embedding-3-small"

    # Chroma local persistent storage
    chroma_persist_dir: str = "data/chroma"
    chroma_collection_name: str = "documents"

    # BM25 pickle index path
    bm25_index_path: str = "data/bm25.pkl"

    # SQLite metadata store path
    chunk_db_path: str = "data/chunks.db"

    # Ingestion settings for embedding 
    chunk_size: int = 1000
    chunk_overlap: int = 200
    batch_size: int = 100
    max_concurrent_requests: int = 5
    
    # Backend API settings
    backend_api_timeout: int = 60  # seconds
    backend_api_retry_count: int = 3

    # ── Server ───────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()
