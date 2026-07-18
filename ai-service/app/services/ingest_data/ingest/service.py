"""
DefaultIngestService — markdown ingestion into the hybrid search stores.

Pipeline per document:
    read markdown -> build_chunks (semantic units, 2 text views, metadata)
        -> SQLiteChunkStore.upsert   (source of truth)
        -> ChromaVectorStore.upsert  (embeddings via Ollama)
        -> RankBM25Store.add + save  (keyword index)

``data_source_api`` accepts a local file path OR a directory (all *.md files
are ingested). Ingest is idempotent: deterministic chunk ids mean re-ingesting
a document replaces its chunks in every store.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.base import IngestService as IngestServiceABC
from app.services.ingest_data.ingest.chunk_builder import build_chunks
from app.services.ingest_data.stores import get_stores

logger = logging.getLogger(__name__)


class DefaultIngestService(IngestServiceABC):
    """Ingest markdown documents into vector + BM25 + chunk stores."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    # ── helpers ──────────────────────────────────────────────────────

    def _resolve_files(self, data_source_api: str) -> list[Path]:
        """Resolve a file or directory path to a list of markdown files."""
        path = Path(data_source_api)
        if path.is_dir():
            return sorted(path.glob("*.md"))
        if path.is_file():
            return [path]
        raise FileNotFoundError(f"Path not found: {data_source_api}")

    def _ingest_files_sync(self, files: list[Path], metadata: dict | None) -> dict:
        """Blocking ingest work — run inside a thread."""
        stores = get_stores(self.settings)
        version = (metadata or {}).get("version")

        total_chunks = 0
        per_document: list[dict] = []

        for file_path in files:
            text = file_path.read_text(encoding="utf-8")
            chunks = build_chunks(
                text=text,
                source_file=str(file_path),
                version=version,
                max_tokens=self.settings.chunk_max_tokens,
                min_tokens=self.settings.chunk_min_tokens,
            )
            if not chunks:
                per_document.append({"file": file_path.name, "chunks": 0})
                continue

            # Idempotent replace: clear existing chunks for this document first
            document_id = chunks[0].document_id
            stores.vector_store.delete_by_document(document_id)
            stores.chunk_store.delete_by_document(document_id)
            stores.bm25_store.delete_by_document(document_id)

            stores.chunk_store.upsert(chunks)
            stores.vector_store.upsert(chunks)
            stores.bm25_store.add(chunks)

            total_chunks += len(chunks)
            per_document.append(
                {
                    "file": file_path.name,
                    "document_id": document_id,
                    "chunks": len(chunks),
                }
            )
            logger.info(
                "Ingested document",
                extra={"file": file_path.name, "chunks": len(chunks)},
            )

        # Persist BM25 once after all documents
        stores.bm25_store.save()

        return {
            "total_chunks": total_chunks,
            "documents": per_document,
            "vector_count": stores.vector_store.count(),
            "bm25_count": stores.bm25_store.count(),
        }

    # ── IngestService contract ───────────────────────────────────────

    async def ingest(
        self,
        data_source_api: str,
        data_type: str,
        auth_token: str | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """Ingest markdown from a local file or directory path."""
        start = time.perf_counter()
        logger.info(
            "Ingestion started",
            extra={"data_source": data_source_api, "data_type": data_type},
        )

        try:
            files = self._resolve_files(data_source_api)
        except FileNotFoundError as exc:
            return {
                "status": "failed",
                "records_fetched": 0,
                "records_processed": 0,
                "job_id": None,
                "message": str(exc),
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            }

        result = await asyncio.to_thread(self._ingest_files_sync, files, metadata)

        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Ingestion completed",
            extra={
                "files": len(files),
                "total_chunks": result["total_chunks"],
                "latency_ms": f"{latency_ms:.1f}",
            },
        )

        return {
            "status": "completed",
            "records_fetched": len(files),
            "records_processed": result["total_chunks"],
            "job_id": None,
            "message": (
                f"Ingested {result['total_chunks']} chunks from {len(files)} file(s). "
                f"Vector={result['vector_count']} BM25={result['bm25_count']}."
            ),
            "latency_ms": round(latency_ms, 1),
            "details": result["documents"],
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
        """Delete documents by id, or re-ingest for create/update."""
        start = time.perf_counter()
        op = operation.lower()

        if op == "delete":
            stores = get_stores(self.settings)
            affected = 0
            for document_id in record_ids:
                await asyncio.to_thread(stores.vector_store.delete_by_document, document_id)
                await asyncio.to_thread(stores.chunk_store.delete_by_document, document_id)
                await asyncio.to_thread(stores.bm25_store.delete_by_document, document_id)
                affected += 1
            await asyncio.to_thread(stores.bm25_store.save)
            latency_ms = (time.perf_counter() - start) * 1000
            return {
                "status": "success",
                "records_affected": affected,
                "records_updated": affected,
                "records_failed": 0,
                "failed_ids": [],
                "message": f"Deleted {affected} document(s) from vector + chunk stores.",
                "latency_ms": round(latency_ms, 1),
            }

        if op in ("create", "update") and data_source_api:
            result = await self.ingest(
                data_source_api=data_source_api,
                data_type=data_type,
                metadata=metadata,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            return {
                "status": "success" if result["status"] == "completed" else "failed",
                "records_affected": result["records_fetched"],
                "records_updated": result["records_processed"],
                "records_failed": 0,
                "failed_ids": [],
                "message": result["message"],
                "latency_ms": round(latency_ms, 1),
            }

        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "failed",
            "records_affected": len(record_ids),
            "records_updated": 0,
            "records_failed": len(record_ids),
            "failed_ids": record_ids,
            "message": f"Unsupported operation '{operation}' or missing data_source_api.",
            "latency_ms": round(latency_ms, 1),
        }


# Backwards-compatible alias (DI + package __init__ import this name)
IngestService = DefaultIngestService

__all__ = ["DefaultIngestService", "IngestService"]
