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
    # Use 127.0.0.1 (not "localhost"): on Windows, "localhost" adds a ~2s
    # IPv6/DNS resolution delay per new connection.
    ollama_base_url: str = "http://127.0.0.1:11434"
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

    # Local persistence paths (Chroma + BM25 + SQLite chunk store)
    chroma_persist_dir: str = "data/chroma"
    chroma_collection_name: str = "documents"
    bm25_index_path: str = "data/bm25.pkl"
    chunk_db_path: str = "data/chunks.db"

    # ── Embedding (local, via Ollama) ─────────────────────
    # nomic-embed-text: 768-dim, ~274MB, runs locally in Ollama
    embedding_ollama_model: str = "nomic-embed-text"
    embedding_ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_max_concurrency: int = 5   # parallel embed requests to Ollama

    # ── Query transform (LLM) ─────────────────────────────
    # Local Ollama model used as the always-available fallback for the single
    # LLM call (rewrite + decompose). qwen2.5:3b is small and fast.
    query_transform_ollama_model: str = "qwen2.5:3b"
    # Hard cap on generated tokens for query decompose — sub-queries are short,
    # no need to generate 2048 tokens. Caps LLM latency by ~40-60%.
    query_transform_max_tokens: int = 150
    # keep_alive: keep qwen resident in Ollama VRAM between requests.
    # Prevents model unload on sparse traffic (avoids 2-4s cold reload).
    query_transform_keep_alive: str = "30m"

    # ── Chunking ──────────────────────────────────────────
    # Semantic chunking: split by markdown sections, then by size if too long
    chunk_max_tokens: int = 512      # soft cap per chunk (approx by whitespace tokens)
    chunk_min_tokens: int = 32       # merge tiny sections upward
    chunk_overlap: int = 0           # sections are self-contained; no token overlap
    batch_size: int = 100
    max_concurrent_requests: int = 5

    # ── Retrieval (hybrid search) ─────────────────────────
    retrieval_bm25_top_k: int = 30        # candidates from BM25 per sub-query
    retrieval_vector_top_k: int = 30      # candidates from vector search per sub-query
    retrieval_rrf_k: int = 60             # RRF constant
    retrieval_worker_top_k: int = 10      # results kept per sub-query after fusion
    retrieval_final_top_k: int = 12       # final results after merge across sub-queries
    retrieval_max_subqueries: int = 3     # max sub-queries from QueryTransform
    retrieval_max_concurrency: int = 5    # parallel retrieval workers

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
