from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from rag_core.schemas import Chunk, CitationSpan, Document, DocumentVersion, Section


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,
  content_hash TEXT NOT NULL, latest_version_id TEXT
);
CREATE TABLE IF NOT EXISTS document_versions (
  version_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_number INTEGER NOT NULL,
  status TEXT NOT NULL, content_hash TEXT NOT NULL, payload TEXT NOT NULL,
  UNIQUE(document_id, version_number), FOREIGN KEY(document_id) REFERENCES documents(document_id)
);
CREATE TABLE IF NOT EXISTS sections (
  section_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_id TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, version_id TEXT NOT NULL,
  section_id TEXT NOT NULL, is_active INTEGER NOT NULL, content_hash TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citation_spans (
  citation_id TEXT PRIMARY KEY, chunk_id TEXT NOT NULL, payload TEXT NOT NULL,
  FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
);
CREATE INDEX IF NOT EXISTS idx_chunks_active ON chunks(document_id, is_active);
CREATE INDEX IF NOT EXISTS idx_chunks_version ON chunks(version_id);
"""


class CanonicalStore:
    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(path)
        self.connection.executescript(SCHEMA)

    def upsert_ingestion(self, document: Document, version: DocumentVersion, sections: Iterable[Section],
                         chunks: Iterable[Chunk], citations: Iterable[CitationSpan]) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET "
                "payload=excluded.payload,status=excluded.status,content_hash=excluded.content_hash,latest_version_id=excluded.latest_version_id",
                (document.document_id, json.dumps(document.to_dict(), ensure_ascii=False), str(document.status),
                 document.content_hash, document.latest_version_id),
            )
            self.connection.execute(
                "INSERT INTO document_versions VALUES(?,?,?,?,?,?) ON CONFLICT(version_id) DO UPDATE SET payload=excluded.payload,status=excluded.status",
                (version.version_id, version.document_id, version.version_number, version.status,
                 version.content_hash, json.dumps(version.to_dict(), ensure_ascii=False)),
            )
            for item in sections:
                self.connection.execute("INSERT OR REPLACE INTO sections VALUES(?,?,?,?)", (
                    item.section_id, item.document_id, item.version_id, json.dumps(item.to_dict(), ensure_ascii=False)))
            for item in chunks:
                self.connection.execute("INSERT OR REPLACE INTO chunks VALUES(?,?,?,?,?,?,?)", (
                    item.chunk_id, item.document_id, item.version_id, item.section_id, int(item.is_active),
                    item.content_hash, json.dumps(item.to_dict(), ensure_ascii=False)))
            for item in citations:
                self.connection.execute("INSERT OR REPLACE INTO citation_spans VALUES(?,?,?)", (
                    item.citation_id, item.chunk_id, json.dumps(item.to_dict(), ensure_ascii=False)))

    def deactivate_document(self, document_id: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE documents SET status='inactive' WHERE document_id=?", (document_id,))
            self.connection.execute("UPDATE chunks SET is_active=0 WHERE document_id=?", (document_id,))

    def active_chunks(self) -> list[Chunk]:
        rows = self.connection.execute("SELECT payload FROM chunks WHERE is_active=1 ORDER BY rowid").fetchall()
        return [Chunk(**json.loads(row[0])) for row in rows]

    def close(self) -> None:
        self.connection.close()

