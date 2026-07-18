"""
Ingest base abstractions.

Defines the storage-agnostic interfaces the ingest pipeline depends on:
    - Chunk: a self-contained, traceable semantic unit
    - BaseVectorStore: semantic (embedding) index
    - BaseBM25Store: keyword (BM25) index
    - BaseChunkStore: canonical chunk + metadata store (source of truth)

Callers depend only on these ABCs; concrete backends (Chroma, rank-bm25,
SQLite) are swapped at construction time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Chunk:
    """
    A single traceable knowledge unit.

    Two text views are stored:
        - embed_text: heading path prepended (contextual retrieval)
        - bm25_text:  near-raw body (avoids keyword noise)

    chunk_id is deterministic (see chunk_builder) so hybrid merge can
    dedupe by id without comparing text.
    """

    chunk_id: str
    document_id: str
    document_name: str
    source_file: str

    # Body text (raw section content)
    text: str
    # Text used for embedding (context header + body)
    embed_text: str
    # Text used for BM25 (near-raw body)
    bm25_text: str

    # Hierarchical context
    heading_path: list[str] = field(default_factory=list)

    # Location / provenance
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None

    # Tree links
    parent_id: Optional[str] = None

    # Extras
    token_count: int = 0
    keywords: list[str] = field(default_factory=list)
    version: Optional[str] = None

    def flat_metadata(self) -> dict[str, Any]:
        """
        Flatten to a scalar-only dict for vector-store metadata.

        Chroma metadata values must be str/int/float/bool. heading_path and
        keywords are joined; full structured metadata lives in the ChunkStore.
        """
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "source_file": self.source_file,
            "heading_path": " > ".join(self.heading_path),
            "page_start": self.page_start if self.page_start is not None else -1,
            "page_end": self.page_end if self.page_end is not None else -1,
            "line_start": self.line_start if self.line_start is not None else -1,
            "line_end": self.line_end if self.line_end is not None else -1,
            "parent_id": self.parent_id or "",
            "token_count": self.token_count,
            "version": self.version or "",
        }


@dataclass
class VectorSearchResult:
    """One hit from a vector or BM25 search."""

    chunk_id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseVectorStore(ABC):
    """Semantic (embedding) index."""

    @abstractmethod
    def upsert(self, chunks: list[Chunk]) -> None:
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[VectorSearchResult]:
        ...

    @abstractmethod
    def delete_by_document(self, document_id: str) -> None:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


class BaseBM25Store(ABC):
    """Keyword (BM25) index."""

    @abstractmethod
    def add(self, chunks: list[Chunk]) -> None:
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> list[VectorSearchResult]:
        ...

    @abstractmethod
    def delete_by_document(self, document_id: str) -> None:
        ...

    @abstractmethod
    def save(self) -> None:
        ...

    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


class BaseChunkStore(ABC):
    """Canonical chunk store (source of truth for rich metadata)."""

    @abstractmethod
    def upsert(self, chunks: list[Chunk]) -> None:
        ...

    @abstractmethod
    def get(self, chunk_id: str) -> Optional[Chunk]:
        ...

    @abstractmethod
    def get_many(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        ...

    @abstractmethod
    def delete_by_document(self, document_id: str) -> None:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


__all__ = [
    "Chunk",
    "VectorSearchResult",
    "BaseVectorStore",
    "BaseBM25Store",
    "BaseChunkStore",
]
