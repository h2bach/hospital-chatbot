"""
RankBM25Store — keyword index backed by rank-bm25 (BM25Okapi).

rank-bm25 has no incremental add, so we keep the full corpus in memory and
rebuild the index on each add()/load(). The corpus (tokens + chunk ids +
lightweight metadata) is persisted with pickle so it survives restarts.

Tokenizer: unicode-aware, lowercased, punctuation stripped. Works for
Vietnamese (diacritics preserved) without extra dependencies.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path

from app.services.ingest_data.ingest.base import (
    BaseBM25Store,
    Chunk,
    VectorSearchResult,
)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Lowercase, unicode word tokens."""
    return _TOKEN_RE.findall(text.lower())


class RankBM25Store(BaseBM25Store):
    """In-memory BM25 index with pickle persistence."""

    def __init__(self, index_path: str | Path) -> None:
        self._index_path = Path(index_path)
        self._chunk_ids: list[str] = []
        self._texts: list[str] = []
        self._metadatas: list[dict] = []
        self._tokenized: list[list[str]] = []
        self._bm25 = None  # lazily (re)built

    def _rebuild(self) -> None:
        from rank_bm25 import BM25Okapi

        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)
        else:
            self._bm25 = None

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        # Deduplicate by chunk_id (idempotent re-ingest)
        existing = set(self._chunk_ids)
        for c in chunks:
            if c.chunk_id in existing:
                # Replace in place
                idx = self._chunk_ids.index(c.chunk_id)
                self._texts[idx] = c.text
                self._metadatas[idx] = c.flat_metadata()
                self._tokenized[idx] = tokenize(c.bm25_text)
                continue
            self._chunk_ids.append(c.chunk_id)
            self._texts.append(c.text)
            self._metadatas.append(c.flat_metadata())
            self._tokenized.append(tokenize(c.bm25_text))
            existing.add(c.chunk_id)
        self._rebuild()

    def search(self, query: str, top_k: int = 10) -> list[VectorSearchResult]:
        if self._bm25 is None or not self._chunk_ids:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results: list[VectorSearchResult] = []
        for i in ranked[:top_k]:
            if scores[i] <= 0:
                continue
            results.append(
                VectorSearchResult(
                    chunk_id=self._chunk_ids[i],
                    score=float(scores[i]),
                    text=self._texts[i],
                    metadata=dict(self._metadatas[i]),
                )
            )
        return results

    def delete_by_document(self, document_id: str) -> None:
        """Drop all entries belonging to a document, then rebuild the index."""
        keep = [
            i
            for i, meta in enumerate(self._metadatas)
            if meta.get("document_id") != document_id
        ]
        if len(keep) == len(self._chunk_ids):
            return
        self._chunk_ids = [self._chunk_ids[i] for i in keep]
        self._texts = [self._texts[i] for i in keep]
        self._metadatas = [self._metadatas[i] for i in keep]
        self._tokenized = [self._tokenized[i] for i in keep]
        self._rebuild()

    def save(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunk_ids": self._chunk_ids,
            "texts": self._texts,
            "metadatas": self._metadatas,
            "tokenized": self._tokenized,
        }
        with open(self._index_path, "wb") as f:
            pickle.dump(payload, f)

    def load(self) -> None:
        if not self._index_path.exists():
            return
        with open(self._index_path, "rb") as f:
            payload = pickle.load(f)
        self._chunk_ids = payload.get("chunk_ids", [])
        self._texts = payload.get("texts", [])
        self._metadatas = payload.get("metadatas", [])
        self._tokenized = payload.get("tokenized", [])
        self._rebuild()

    def count(self) -> int:
        return len(self._chunk_ids)


__all__ = ["RankBM25Store", "tokenize"]
