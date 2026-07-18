"""
ChromaVectorStore — semantic index backed by a local persistent Chroma client.

Embeddings are computed by an injected OllamaEmbedder (no network API). We
compute embeddings ourselves and pass them to Chroma via ``embeddings=`` /
``query_embeddings=`` so Chroma never calls out on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.services.ingest_data.ingest.base import (
    BaseVectorStore,
    Chunk,
    VectorSearchResult,
)
from app.services.ingest_data.ingest.embeddings import OllamaEmbedder


class ChromaVectorStore(BaseVectorStore):
    """Local persistent Chroma collection using externally-computed embeddings."""

    def __init__(
        self,
        persist_directory: str | Path,
        embedder: OllamaEmbedder,
        collection_name: str = "documents",
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "chromadb is required. Install with: pip install chromadb"
            ) from exc

        self._embedder = embedder
        self._persist_dir = Path(persist_directory)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # No embedding_function: we always pass vectors explicitly.
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        embeddings = self._embedder([c.embed_text for c in chunks])
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[c.flat_metadata() for c in chunks],
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[VectorSearchResult]:
        count = self._collection.count()
        if count == 0:
            return []

        query_embedding = self._embedder.embed_query(query)
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, count),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata

        result = self._collection.query(**kwargs)
        items: list[VectorSearchResult] = []
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        dists = result["distances"][0]
        for doc, meta, dist in zip(docs, metas, dists):
            items.append(
                VectorSearchResult(
                    chunk_id=meta["chunk_id"],
                    score=1.0 - float(dist),   # cosine distance -> similarity
                    text=doc,
                    metadata=dict(meta),
                )
            )
        return items

    def delete_by_document(self, document_id: str) -> None:
        self._collection.delete(where={"document_id": document_id})

    def count(self) -> int:
        return self._collection.count()


__all__ = ["ChromaVectorStore"]
