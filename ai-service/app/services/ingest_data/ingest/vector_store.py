"""
ChromaVectorStore — Chroma implementation of BaseVectorStore.

Design:
  - Implements BaseVectorStore using chromadb (local persistent client).
  - Callers depend only on BaseVectorStore; switching backends means swapping
    the concrete class at construction time only.

Metadata stored per chunk:
    chunk_id, document_id, page_start, page_end, section, source

The full heading_path is NOT stored in the vector store to keep metadata
lightweight. Callers resolve rich metadata via ChunkStore after retrieval.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from app.services.ingest_data.ingest.base import BaseVectorStore, VectorSearchResult
from app.services.ingest_data.ingest.chunk_builder import Chunk


# ---------------------------------------------------------------------------
# ChromaVectorStore implementation
# ---------------------------------------------------------------------------


class ChromaVectorStore(BaseVectorStore):
    """
    Local persistent Chroma vector store.

    Uses OpenAI embedding function with text-embedding-3-small model
    configured via environment variables (EMBEDDING_API_KEY, EMBEDDING_BASE_URL,
    EMBEDDING_MODEL).

    To use a custom embedding function, pass it via *embedding_function*::

        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        store = ChromaVectorStore(
            persist_directory="type1_data/chroma",
            collection_name="documents",
            embedding_function=OpenAIEmbeddingFunction(api_key="..."),
        )
    """

    def __init__(
        self,
        persist_directory: str | Path,
        collection_name: str = "documents",
        embedding_function: Any = None,
        embedding_api_key: str = "",
        embedding_base_url: str = "",
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "chromadb is required for ChromaVectorStore. "
                "Install it with: pip install chromadb"
            ) from exc

        self._persist_dir = Path(persist_directory)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # get_or_create is idempotent — safe to call on every startup
        kwargs: dict[str, Any] = {}
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function
        else:
            # Prefer explicit args; fall back to os.getenv for backward compat
            api_key = embedding_api_key or os.getenv("EMBEDDING_API_KEY", "")
            base_url = embedding_base_url or os.getenv("EMBEDDING_BASE_URL", "")
            model = embedding_model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

            if not api_key:
                raise ValueError(
                    "EMBEDDING_API_KEY is required when no embedding_function is provided"
                )
            if not base_url:
                raise ValueError(
                    "EMBEDDING_BASE_URL is required when no embedding_function is provided"
                )

            kwargs["embedding_function"] = OpenAIEmbeddingFunction(
                api_key=api_key,
                api_base=base_url,
                model_name=model,
            )

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            **kwargs,
        )

    # ------------------------------------------------------------------
    # BaseVectorStore implementation
    # ------------------------------------------------------------------

    def upsert(self, chunks: list[Chunk], source: str) -> None:
        """Upsert all chunks into the Chroma collection."""
        if not chunks:
            return

        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "source": source,
                "page_start": c.page_start if c.page_start is not None else -1,
                "page_end": c.page_end if c.page_end is not None else -1,
                "section": c.section,
            }
            for c in chunks
        ]

        # Chroma upsert handles both insert and update
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[VectorSearchResult]:
        """Query the collection and return ranked results."""
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(top_k, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata

        result = self._collection.query(**kwargs)

        items: list[VectorSearchResult] = []
        for doc, meta, dist in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            # Chroma cosine distance ∈ [0, 2]; convert to similarity ∈ [-1, 1]
            similarity = 1.0 - dist
            items.append(
                VectorSearchResult(
                    chunk_id=meta["chunk_id"],
                    score=similarity,
                    text=doc,
                    metadata=dict(meta),
                )
            )

        return items

    def delete_by_document(self, document_id: str) -> None:
        """Delete all chunks belonging to *document_id*."""
        self._collection.delete(where={"document_id": document_id})

    def delete_by_chunk(self, chunk_id: str) -> None:
        """Delete a single chunk."""
        self._collection.delete(ids=[chunk_id])


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "BaseVectorStore",
    "VectorSearchResult",
    "ChromaVectorStore",
]
