"""
SQLiteChunkStore — canonical chunk store (source of truth).

Stores the full Chunk (including structured heading_path and keywords as JSON)
so retrieval can resolve rich metadata and build accurate citations without
relying on the LLM. Vector/BM25 stores only keep flattened scalar metadata.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from app.services.ingest_data.ingest.base import BaseChunkStore, Chunk


class SQLiteChunkStore(BaseChunkStore):
    """SQLite-backed chunk store."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id      TEXT PRIMARY KEY,
                    document_id   TEXT NOT NULL,
                    document_name TEXT,
                    source_file   TEXT,
                    text          TEXT,
                    embed_text    TEXT,
                    bm25_text     TEXT,
                    heading_path  TEXT,   -- JSON array
                    page_start    INTEGER,
                    page_end      INTEGER,
                    line_start    INTEGER,
                    line_end      INTEGER,
                    parent_id     TEXT,
                    token_count   INTEGER,
                    keywords      TEXT,   -- JSON array
                    version       TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)"
            )

    def _row_to_chunk(self, row: sqlite3.Row) -> Chunk:
        return Chunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            document_name=row["document_name"] or "",
            source_file=row["source_file"] or "",
            text=row["text"] or "",
            embed_text=row["embed_text"] or "",
            bm25_text=row["bm25_text"] or "",
            heading_path=json.loads(row["heading_path"] or "[]"),
            page_start=row["page_start"] if row["page_start"] != -1 else None,
            page_end=row["page_end"] if row["page_end"] != -1 else None,
            line_start=row["line_start"] if row["line_start"] != -1 else None,
            line_end=row["line_end"] if row["line_end"] != -1 else None,
            parent_id=row["parent_id"] or None,
            token_count=row["token_count"] or 0,
            keywords=json.loads(row["keywords"] or "[]"),
            version=row["version"] or None,
        )

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, document_id, document_name, source_file,
                    text, embed_text, bm25_text, heading_path,
                    page_start, page_end, line_start, line_end,
                    parent_id, token_count, keywords, version
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    document_id=excluded.document_id,
                    document_name=excluded.document_name,
                    source_file=excluded.source_file,
                    text=excluded.text,
                    embed_text=excluded.embed_text,
                    bm25_text=excluded.bm25_text,
                    heading_path=excluded.heading_path,
                    page_start=excluded.page_start,
                    page_end=excluded.page_end,
                    line_start=excluded.line_start,
                    line_end=excluded.line_end,
                    parent_id=excluded.parent_id,
                    token_count=excluded.token_count,
                    keywords=excluded.keywords,
                    version=excluded.version
                """,
                [
                    (
                        c.chunk_id,
                        c.document_id,
                        c.document_name,
                        c.source_file,
                        c.text,
                        c.embed_text,
                        c.bm25_text,
                        json.dumps(c.heading_path, ensure_ascii=False),
                        c.page_start if c.page_start is not None else -1,
                        c.page_end if c.page_end is not None else -1,
                        c.line_start if c.line_start is not None else -1,
                        c.line_end if c.line_end is not None else -1,
                        c.parent_id or "",
                        c.token_count,
                        json.dumps(c.keywords, ensure_ascii=False),
                        c.version or "",
                    )
                    for c in chunks
                ],
            )

    def get(self, chunk_id: str) -> Optional[Chunk]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
            return self._row_to_chunk(row) if row else None

    def get_many(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" * len(chunk_ids))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ).fetchall()
        return {row["chunk_id"]: self._row_to_chunk(row) for row in rows}

    def delete_by_document(self, document_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


__all__ = ["SQLiteChunkStore"]
