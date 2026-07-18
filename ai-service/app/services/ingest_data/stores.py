"""
Shared store factory.

Provides process-wide singletons for the embedder and the three stores so
ingest and retrieval operate on the same Chroma collection, BM25 index, and
SQLite chunk store. Thread-safe lazy initialization.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from app.config import Settings
from app.services.ingest_data.ingest.base import (
    BaseBM25Store,
    BaseChunkStore,
    BaseVectorStore,
)
from app.services.ingest_data.ingest.bm25_store import RankBM25Store
from app.services.ingest_data.ingest.chunk_store import SQLiteChunkStore
from app.services.ingest_data.ingest.embeddings import OllamaEmbedder
from app.services.ingest_data.ingest.vector_store import ChromaVectorStore


@dataclass
class Stores:
    """Bundle of the shared retrieval/ingest stores."""

    embedder: OllamaEmbedder
    vector_store: BaseVectorStore
    bm25_store: BaseBM25Store
    chunk_store: BaseChunkStore


_lock = threading.Lock()
_stores: Stores | None = None


def get_stores(settings: Settings) -> Stores:
    """Return the shared Stores bundle, building it once per process."""
    global _stores
    if _stores is not None:
        return _stores
    with _lock:
        if _stores is not None:
            return _stores

        embedder = OllamaEmbedder(
            model=settings.embedding_ollama_model,
            base_url=settings.embedding_ollama_base_url,
            max_concurrency=settings.embedding_max_concurrency,
        )
        vector_store = ChromaVectorStore(
            persist_directory=settings.chroma_persist_dir,
            embedder=embedder,
            collection_name=settings.chroma_collection_name,
        )
        bm25_store = RankBM25Store(index_path=settings.bm25_index_path)
        bm25_store.load()
        chunk_store = SQLiteChunkStore(db_path=settings.chunk_db_path)

        _stores = Stores(
            embedder=embedder,
            vector_store=vector_store,
            bm25_store=bm25_store,
            chunk_store=chunk_store,
        )
        return _stores


def reset_stores() -> None:
    """Drop the cached stores (used by tests / after re-index)."""
    global _stores
    with _lock:
        _stores = None


__all__ = ["Stores", "get_stores", "reset_stores"]
