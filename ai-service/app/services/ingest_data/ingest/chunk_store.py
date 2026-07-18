"""
ChunkStore — SQLite-backed metadata store for documents and chunks.

Responsibilities:
  - Persist Document records (one per ingested file).
  - Persist Chunk records (many per document).
  - Provide fast lookup by chunk_id (used after BM25 / VectorDB retrieval).
  - Provide lookup by document_id + parent_heading_id (neighbor expansion).

Schema
------
documents
    document_id   TEXT  PRIMARY KEY
    source        TEXT  -- original filename / path
    title         TEXT
    created_at    TEXT  -- ISO-8601

chunks
    chunk_id          TEXT  PRIMARY KEY
    document_id       TEXT  REFERENCES documents(document_id)
    page_start        INTEGER
    page_end          INTEGER
    heading_path      TEXT  -- JSON array
    section           TEXT
    parent_heading_id TEXT
    offset_start      INTEGER
    offset_end        INTEGER
    text              TEXT

Indexes are created on (document_id) and (parent_heading_id) for fast
section-level expansion queries.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.ingest_data.ingest.chunk_builder import Chunk


# ---------------------------------------------------------------------------
# SQLite connection wrapper — auto-closes on context manager exit
# (sqlite3.Connection.__exit__ only commits/rolls back; on Windows the file
#  lock is NOT released until close() is called explicitly)
# ---------------------------------------------------------------------------


class _AutoCloseConnection:
    """Thin wrapper that commits + closes the underlying connection on exit."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # Proxy all attribute access to the wrapped connection
    def __getattr__(self, name: str):  # type: ignore[return]
        return getattr(self._conn, name)

    def __enter__(self) -> "_AutoCloseConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DocumentRecord:
    document_id: str
    source: str
    title: str
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ChunkRecord:
    """Mirrors a row in the *chunks* table."""

    chunk_id: str
    document_id: str
    text: str
    page_start: Optional[int]
    page_end: Optional[int]
    heading_path: list[str]
    section: str
    parent_heading_id: str
    offset_start: int
    offset_end: int

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> "ChunkRecord":
        return cls(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            text=chunk.text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            heading_path=chunk.heading_path,
            section=chunk.section,
            parent_heading_id=chunk.parent_heading_id,
            offset_start=chunk.offset_start,
            offset_end=chunk.offset_end,
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ChunkStore:
    """
    Thread-safe SQLite metadata store.

    One instance per process is sufficient; connections are created per call
    (SQLite handles concurrency at the file level via WAL mode).

    Usage::

        store = ChunkStore(db_path="type1_data/chunks.db")
        store.save_document(doc_record)
        store.save_chunks(chunk_records)

        record = store.get_chunk("chunk_000042")
        neighbors = store.get_chunks_by_heading("abc123def456")
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        source      TEXT NOT NULL,
        title       TEXT NOT NULL,
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id          TEXT PRIMARY KEY,
        document_id       TEXT NOT NULL REFERENCES documents(document_id),
        page_start        INTEGER,
        page_end          INTEGER,
        heading_path      TEXT NOT NULL DEFAULT '[]',
        section           TEXT NOT NULL DEFAULT '',
        parent_heading_id TEXT NOT NULL DEFAULT '',
        offset_start      INTEGER NOT NULL DEFAULT 0,
        offset_end        INTEGER NOT NULL DEFAULT 0,
        text              TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_chunks_document_id
        ON chunks(document_id);

    CREATE INDEX IF NOT EXISTS idx_chunks_parent_heading
        ON chunks(parent_heading_id);
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_document(self, doc: DocumentRecord) -> None:
        """Insert or replace a document record."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents
                    (document_id, source, title, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (doc.document_id, doc.source, doc.title, doc.created_at),
            )

    def save_chunks(self, chunks: list[ChunkRecord]) -> None:
        """Bulk-insert or replace chunk records."""
        rows = [
            (
                c.chunk_id,
                c.document_id,
                c.page_start,
                c.page_end,
                json.dumps(c.heading_path, ensure_ascii=False),
                c.section,
                c.parent_heading_id,
                c.offset_start,
                c.offset_end,
                c.text,
            )
            for c in chunks
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO chunks
                    (chunk_id, document_id, page_start, page_end,
                     heading_path, section, parent_heading_id,
                     offset_start, offset_end, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_chunk(self, chunk_id: str) -> Optional[ChunkRecord]:
        """Fetch a single chunk by its id. Returns None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
        return self._row_to_chunk(row) if row else None

    def get_chunks(self, chunk_ids: list[str]) -> list[ChunkRecord]:
        """Fetch multiple chunks by id. Order follows *chunk_ids*."""
        if not chunk_ids:
            return []
        placeholders = ",".join("?" * len(chunk_ids))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ).fetchall()

        # Preserve caller order
        by_id = {r["chunk_id"]: self._row_to_chunk(r) for r in rows}
        return [by_id[cid] for cid in chunk_ids if cid in by_id]

    def get_chunks_by_heading(self, parent_heading_id: str) -> list[ChunkRecord]:
        """
        Return all chunks that share the same heading section.
        Useful for neighbor / context expansion during retrieval.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE parent_heading_id = ? ORDER BY offset_start",
                (parent_heading_id,),
            ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def get_chunks_by_document(self, document_id: str) -> list[ChunkRecord]:
        """Return all chunks for a document, ordered by offset."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY offset_start",
                (document_id,),
            ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def get_document(self, document_id: str) -> Optional[DocumentRecord]:
        """Fetch a single document by its id. Returns None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        if row:
            return DocumentRecord(
                document_id=row["document_id"],
                source=row["source"],
                title=row["title"],
                created_at=row["created_at"],
            )
        return None

    def delete_document(self, document_id: str) -> None:
        """Remove a document and all its chunks."""
        with self._connect() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(self._DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            # Ensure the connection is closed when used as a context manager
            # (sqlite3.Connection.__exit__ only commits/rolls back by default;
            #  we subclass to also close so Windows file locks are released).
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return _AutoCloseConnection(conn)

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            text=row["text"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            heading_path=json.loads(row["heading_path"]),
            section=row["section"],
            parent_heading_id=row["parent_heading_id"],
            offset_start=row["offset_start"],
            offset_end=row["offset_end"],
        )
