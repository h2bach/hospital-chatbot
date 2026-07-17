"""
BaseVectorStore — Abstract base class for vector database backends.

Defines the contract that all vector store implementations must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.services.ingest_data.ingest.chunk_builder import Chunk


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class VectorSearchResult:
    """Result from a vector similarity search."""
    
    chunk_id: str
    score: float          # higher is more relevant (distance converted to similarity)
    text: str
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseVectorStore(ABC):
    """
    Contract for all vector store backends.

    Implementations must be safe to call from async code (wrap blocking I/O
    in a thread executor if needed).
    """

    @abstractmethod
    def upsert(self, chunks: list[Chunk], source: str) -> None:
        """
        Insert or update *chunks* in the store.

        *source* is the original filename / document path and is stored as
        metadata for filtering.
        """

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[VectorSearchResult]:
        """
        Semantic similarity search.

        Returns up to *top_k* results ordered by descending relevance.
        Optional *filter_metadata* is passed as a where-clause to backends
        that support it (e.g. ``{"document_id": "doc_abc"}``)
        """

    @abstractmethod
    def delete_by_document(self, document_id: str) -> None:
        """Remove all vectors that belong to *document_id*."""

    @abstractmethod
    def delete_by_chunk(self, chunk_id: str) -> None:
        """Remove a single vector by *chunk_id*."""
