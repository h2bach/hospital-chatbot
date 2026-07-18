"""
Application configuration.

Reads settings from environment variables / .env file.
Uses @lru_cache so .env is loaded only once per process.

LLM Tier System (single source of truth):
  Every LLM used by the RAG graph is configured via ONE of three tiers:
    - strong : Planner Chain 1 (planning, structured output)
    - middle : Planner Chain 2 (decision/replan), Synthesizer
    - cheap  : (reserved for lightweight future tasks)

  Each tier has:
    <TIER>_MODEL_PROVIDER   provider name  (other | google | openai | ollama)
    <TIER>_MODEL_NAME       model identifier passed to the provider API
    <TIER>_MODEL_API_KEY    API key (overrides the shared OTHER_API_KEY)
    <TIER>_MODEL_BASE_URL   base URL (overrides the shared OTHER_BASE_URL)

  Fallback order per tier:
    1. tier primary (from <TIER>_MODEL_*)
    2. FALLBACK_MODEL_* (optional second provider)
    3. GOOGLE_API_KEY + GOOGLE_MODEL (last-resort, if configured)

Supported providers:
    other   — any OpenAI-compatible REST endpoint (shopaikey, etc.)
    openai  — official OpenAI API
    google  — Google GenAI / Gemini
    ollama  — local Ollama server (no API key required)
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — every field maps to an env var."""

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "AI Service"
    app_version: str = "1.0.0"
    debug: bool = False

    # ── Shared LLM settings (apply to all tiers unless overridden) ───────────
    llm_max_tokens: int = 2048
    llm_timeout: int = 60           # seconds; generous for structured output
    llm_temperature: float = 0.7    # default for stream(); nodes always pass 0.0

    # ── Ollama (local, no API key) ───────────────────────────────────────────
    # Only needed when any tier uses provider="ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # ── Google GenAI (last-resort fallback for all tiers) ────────────────────
    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"

    # ── Tier: strong ─────────────────────────────────────────────────────────
    # Used by: Planner Chain 1 (initial task planning)
    strong_model_provider: str = "other"
    strong_model_name: str = "gpt-4o"
    strong_model_api_key: str = ""      # if empty → falls back to other_api_key
    strong_model_base_url: str = ""     # if empty → falls back to other_base_url

    # ── Tier: middle ─────────────────────────────────────────────────────────
    # Used by: Planner Chain 2 (decision/replan), Synthesizer
    middle_model_provider: str = "other"
    middle_model_name: str = "gpt-4o-mini"
    middle_model_api_key: str = ""
    middle_model_base_url: str = ""

    # ── Tier: cheap ──────────────────────────────────────────────────────────
    # Reserved for lightweight tasks (query rewriting, intent detection, etc.)
    cheap_model_provider: str = "other"
    cheap_model_name: str = "gpt-4o-mini"
    cheap_model_api_key: str = ""
    cheap_model_base_url: str = ""

    # ── Shared "other" provider credentials (OpenAI-compatible fallback) ─────
    # Used when a tier's own api_key / base_url is not set.
    other_api_key: str = ""
    other_base_url: str = "https://api.shopaikey.com/v1"
    other_model: str = "gpt-5.4-mini-2026-03-17"   # default for `other` provider

    # ── OpenAI (optional, if using official OpenAI API) ──────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # ── Data Ingestion ────────────────────────────────────────────────────────
    # Vector store backend
    vector_store_type: Literal["chroma", "qdrant", "weaviate", "pinecone"] = "chroma"
    vector_store_url: str = ""
    vector_store_api_key: str = ""

    # Chroma (local persistent, default backend)
    chroma_persist_dir: str = "type1_data/chroma"
    chroma_collection_name: str = "documents"

    # BM25 keyword index
    bm25_index_path: str = "type1_data/bm25.pkl"

    # SQLite chunk metadata store
    chunk_db_path: str = "type1_data/chunks.db"

    # Embedding
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"

    # Chunking parameters
    chunk_size: int = 1000
    chunk_overlap: int = 200
    batch_size: int = 100
    max_concurrent_requests: int = 5

    # Backend API settings
    backend_api_timeout: int = 60
    backend_api_retry_count: int = 3

    # ── Server ────────────────────────────────────────────────────────────────
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
