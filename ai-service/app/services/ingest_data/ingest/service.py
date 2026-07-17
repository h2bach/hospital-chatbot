"""
DefaultIngestService — Full ingestion pipeline implementation.

Pipeline:
    markdown text
        → MarkdownParser      → list[DocumentNode]
        → ChunkBuilder        → list[Chunk]
        → ChunkStore.save     → SQLite  (metadata)
        → ChromaVectorStore.upsert → Chroma (semantic search)
        → RankBM25Store.add + save → BM25 pickle (keyword search)

Stores are constructed from Settings on first use (lazy init) so that the
FastAPI process does not open file handles at import time.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from functools import cached_property
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.base import IngestService
from app.services.ingest_data.ingest.base import BaseBM25Store, BaseVectorStore
from app.services.ingest_data.ingest.bm25_store import RankBM25Store
from app.services.ingest_data.ingest.chunk_builder import Chunk, ChunkBuilder
from app.services.ingest_data.ingest.chunk_store import (
    ChunkRecord,
    ChunkStore,
    DocumentRecord,
)
from app.services.ingest_data.ingest.markdown_parser import MarkdownParser
from app.services.ingest_data.ingest.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class DefaultIngestService(IngestService):
    """
    Concrete ingestion service that wires together the full pipeline.

    All heavy I/O (Chroma writes, BM25 rebuild) is executed in a thread pool
    via asyncio.to_thread so the FastAPI event loop is never blocked.

    Dependency injection via abstract types:
        - vector_store : BaseVectorStore   — swap to any backend
        - bm25_store   : BaseBM25Store     — swap to any backend
        - chunk_store  : ChunkStore        — SQLite, no abstraction needed
    """

    def __init__(
        self,
        settings: Settings,
        vector_store: BaseVectorStore | None = None,
        bm25_store: BaseBM25Store | None = None,
    ) -> None:
        super().__init__(settings)
        # Allow injection; fall back to defaults built from settings
        self._vector_store_override = vector_store
        self._bm25_store_override = bm25_store

    # ------------------------------------------------------------------
    # Lazy-initialised stores (created once per process, thread-safe)
    # ------------------------------------------------------------------

    @cached_property
    def _chunk_store(self) -> ChunkStore:
        return ChunkStore(db_path=self.settings.chunk_db_path)

    @cached_property
    def _vector_store(self) -> BaseVectorStore:
        if self._vector_store_override is not None:
            return self._vector_store_override
        return ChromaVectorStore(
            persist_directory=self.settings.chroma_persist_dir,
            collection_name=self.settings.chroma_collection_name,
        )

    @cached_property
    def _bm25_store(self) -> BaseBM25Store:
        if self._bm25_store_override is not None:
            return self._bm25_store_override
        store = RankBM25Store(index_path=self.settings.bm25_index_path)
        store.load()   # no-op on first run
        return store

    # ------------------------------------------------------------------
    # Public API — IngestService contract
    # ------------------------------------------------------------------

    async def ingest(
        self,
        data_source_api: str,
        data_type: str,
        auth_token: str | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Ingest a markdown file into VectorDB + BM25 + SQLite.

        Parameters
        ----------
        data_source_api:
            Path to the markdown file on disk  (e.g. ``/data/hanoi_2024.md``).
        data_type:
            Document type label stored as part of the metadata  (e.g. ``"document"``).
        auth_token:
            Unused for local-file ingestion; reserved for future API-fetch mode.
        metadata:
            Optional extra fields to attach to the DocumentRecord
            (e.g. ``{"title": "Quy trình khám ngoại trú"}``).
        """
        start = time.perf_counter()

        logger.info(
            "Ingestion started",
            extra={"data_source": data_source_api, "data_type": data_type},
        )

        md_path = Path(data_source_api)
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown file not found: {md_path}")

        markdown_text = md_path.read_text(encoding="utf-8")

        extra_meta = metadata or {}
        document_id = _make_document_id(str(md_path))
        title = extra_meta.get("title", md_path.stem)

        doc_record = DocumentRecord(
            document_id=document_id,
            source=str(md_path),
            title=title,
        )

        # Run the CPU-bound pipeline in a thread to avoid blocking the event loop
        chunks = await asyncio.to_thread(
            self._run_pipeline,
            markdown_text,
            document_id,
        )

        # Persist to all three stores (also in threads — Chroma/BM25 do file I/O)
        await asyncio.to_thread(self._persist, doc_record, chunks, str(md_path))

        latency_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "Ingestion completed",
            extra={
                "document_id": document_id,
                "chunks_created": len(chunks),
                "latency_ms": f"{latency_ms:.1f}",
            },
        )

        return {
            "status": "success",
            "document_id": document_id,
            "source": str(md_path),
            "records_fetched": 1,
            "records_processed": len(chunks),
            "latency_ms": round(latency_ms, 1),
        }

    async def update(
        self,
        operation: str,
        data_type: str,
        record_ids: list[str],
        data_source_api: str | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Update or delete documents / chunks.

        Supported operations:
          - ``"delete"``  — remove all chunks for the given document_ids
          - ``"reindex"`` — delete then re-ingest from data_source_api
        """
        start = time.perf_counter()

        logger.info(
            "Update operation started",
            extra={"operation": operation, "record_count": len(record_ids)},
        )

        if operation == "delete":
            await asyncio.to_thread(self._delete_documents, record_ids)
            records_updated = len(record_ids)
            records_failed = 0
        elif operation == "reindex":
            if not data_source_api:
                return {
                    "status": "failed",
                    "message": "data_source_api is required for reindex",
                    "latency_ms": 0.0,
                }
            await asyncio.to_thread(self._delete_documents, record_ids)
            await self.ingest(data_source_api, data_type, metadata=metadata)
            records_updated = len(record_ids)
            records_failed = 0
        else:
            return {
                "status": "failed",
                "message": f"Unknown operation: {operation!r}. Use 'delete' or 'reindex'.",
                "records_affected": len(record_ids),
                "records_updated": 0,
                "records_failed": len(record_ids),
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            }

        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "success",
            "operation": operation,
            "records_affected": len(record_ids),
            "records_updated": records_updated,
            "records_failed": records_failed,
            "latency_ms": round(latency_ms, 1),
        }

    # ------------------------------------------------------------------
    # Internal pipeline steps (synchronous — run in thread pool)
    # ------------------------------------------------------------------

    def _run_pipeline(self, markdown_text: str, document_id: str) -> list[Chunk]:
        """Parse markdown → build chunks. Pure CPU work."""
        parser = MarkdownParser()
        nodes = parser.parse(markdown_text)

        builder = ChunkBuilder(
            document_id=document_id,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        chunks = builder.build(nodes)

        logger.debug(
            "Pipeline: parsed %d nodes → %d chunks",
            len(nodes),
            len(chunks),
        )
        return chunks

    def _persist(
        self,
        doc_record: DocumentRecord,
        chunks: list[Chunk],
        source: str,
    ) -> None:
        """Write to SQLite, Chroma, and BM25 index."""
        # 1. SQLite — always first so metadata is available before vector writes
        self._chunk_store.save_document(doc_record)
        chunk_records = [ChunkRecord.from_chunk(c) for c in chunks]
        self._chunk_store.save_chunks(chunk_records)

        # 2. Vector store
        self._vector_store.upsert(chunks, source=source)

        # 3. BM25 index — add + persist atomically
        self._bm25_store.add(chunks)
        self._bm25_store.save()

    def _delete_documents(self, document_ids: list[str]) -> None:
        """Remove all traces of the given documents from every store."""
        for doc_id in document_ids:
            # Collect chunk_ids before deletion (needed for BM25)
            chunk_records = self._chunk_store.get_chunks_by_document(doc_id)
            chunk_ids = [r.chunk_id for r in chunk_records]

            self._chunk_store.delete_document(doc_id)
            self._vector_store.delete_by_document(doc_id)
            self._bm25_store.delete_by_document(doc_id, chunk_ids)

        self._bm25_store.save()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _make_document_id(source: str) -> str:
    """
    Deterministic document id: first 16 hex chars of SHA-1(source path).

    Using the path (not file content) means re-ingesting the same file
    overwrites the previous record rather than creating a duplicate.
    """
    return "doc_" + hashlib.sha1(source.encode()).hexdigest()[:16]
