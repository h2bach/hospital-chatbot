"""
BaseBM25Store — Abstract base class for BM25 keyword search backends.

Defines the contract that all BM25 implementations must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.ingest_data.ingest.chunk_builder import Chunk


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class BM25SearchResult:
    """Result from a BM25 keyword search."""
    
    chunk_id: str
    score: float        # raw BM25 score (higher is better)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseBM25Store(ABC):
    """
    Contract for keyword-search backends.

    All methods are synchronous because BM25 operations are CPU-bound and
    typically fast enough to run in-process.  Wrap in asyncio.to_thread() if
    you need to call from async code without blocking the event loop.
    """

    @abstractmethod
    def add(self, chunks: list[Chunk]) -> None:
        """
        Add (or re-index) chunks.
        
        Existing chunk_ids are replaced.
        """

    @abstractmethod
    def delete(self, chunk_ids: list[str]) -> None:
        """
        Remove chunks by id.
        
        Unknown ids are silently ignored.
        """

    @abstractmethod
    def delete_by_document(self, document_id: str, chunk_ids: list[str]) -> None:
        """
        Remove all chunks belonging to a document.

        *chunk_ids* must be the full list of chunk_ids for that document
        (obtained from ChunkStore.get_chunks_by_document before deletion).
        """

    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> list[BM25SearchResult]:
        """
        Keyword search.

        Returns up to *top_k* results ordered by descending BM25 score.
        Returns an empty list when the index is empty.
        """

    @abstractmethod
    def save(self) -> None:
        """Persist the current index to durable storage."""

    @abstractmethod
    def load(self) -> None:
        """
        Load a previously persisted index.
        
        No-op if nothing is saved yet.
        """
