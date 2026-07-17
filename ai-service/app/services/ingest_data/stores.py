"""
Store instances provider for RAG query service.

This module provides singleton instances of vector_store and bm25_store
that load from existing persisted data without re-running the ingestion pipeline.

Usage in RAG service::

    from app.services.ingest_data.stores import get_vector_store, get_bm25_store
    
    vector_store = get_vector_store()
    bm25_store = get_bm25_store()
    
    # Use for queries
    vector_results = vector_store.search(query="quy trình khám bệnh", top_k=5)
    bm25_results = bm25_store.search(query="quy trình khám bệnh", top_k=5)
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.ingest_data.ingest.base import (
    BaseBM25Store,
    BaseVectorStore,
)
from app.services.ingest_data.ingest.bm25_store import RankBM25Store
from app.services.ingest_data.ingest.chunk_store import ChunkStore
from app.services.ingest_data.ingest.vector_store import ChromaVectorStore


@lru_cache(maxsize=1)
def get_vector_store() -> BaseVectorStore:
    """
    Get the singleton ChromaVectorStore instance.
    
    Loads from the persisted Chroma database at the path specified in settings.
    This does NOT re-run ingestion; it connects to existing data.
    
    Returns:
        BaseVectorStore: ChromaVectorStore instance connected to existing data
    """
    settings = get_settings()
    
    # ChromaVectorStore automatically connects to existing collection
    # via get_or_create_collection (idempotent)
    vector_store = ChromaVectorStore(
        persist_directory=settings.chroma_persist_dir,
        collection_name=settings.chroma_collection_name,
    )
    
    return vector_store


@lru_cache(maxsize=1)
def get_bm25_store() -> BaseBM25Store:
    """
    Get the singleton RankBM25Store instance.
    
    Loads from the persisted BM25 pickle file at the path specified in settings.
    This does NOT re-run ingestion; it loads existing indexed data.
    
    Returns:
        BaseBM25Store: RankBM25Store instance with loaded index
    """
    settings = get_settings()
    
    # Create store and load existing pickle file
    bm25_store = RankBM25Store(index_path=settings.bm25_index_path)
    bm25_store.load()  # Load existing index from pickle file
    
    return bm25_store


@lru_cache(maxsize=1)
def get_chunk_store() -> ChunkStore:
    """
    Get the singleton ChunkStore instance.
    
    Connects to the existing SQLite database containing chunk metadata.
    This does NOT re-run ingestion; it connects to existing data.
    
    Returns:
        ChunkStore: SQLite-backed chunk metadata store
    """
    settings = get_settings()
    
    # ChunkStore automatically connects to existing SQLite database
    chunk_store = ChunkStore(db_path=settings.chunk_db_path)
    
    return chunk_store


def get_all_stores() -> tuple[BaseVectorStore, BaseBM25Store, ChunkStore]:
    """
    Get all three store instances at once.
    
    Convenience function to get vector_store, bm25_store, and chunk_store
    in a single call.
    
    Returns:
        tuple: (vector_store, bm25_store, chunk_store)
    
    Example::
    
        vector_store, bm25_store, chunk_store = get_all_stores()
        
        # Query both stores
        vector_results = vector_store.search(query="...", top_k=10)
        bm25_results = bm25_store.search(query="...", top_k=10)
        
        # Get chunk details from chunk_store
        for result in vector_results:
            chunk = chunk_store.get_chunk(result.chunk_id)
            if chunk:
                print(f"Chunk: {chunk.text[:100]}...")
    """
    return (
        get_vector_store(),
        get_bm25_store(),
        get_chunk_store(),
    )
