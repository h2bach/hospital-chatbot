"""
Base abstract classes for ingest data stores.

This module exports the abstract base classes that define the contracts
for all store implementations.
"""

from app.services.ingest_data.ingest.base.bm25_store import BaseBM25Store, BM25SearchResult
from app.services.ingest_data.ingest.base.vector_store import BaseVectorStore, VectorSearchResult

__all__ = [
    "BaseBM25Store",
    "BM25SearchResult",
    "BaseVectorStore", 
    "VectorSearchResult",
]
