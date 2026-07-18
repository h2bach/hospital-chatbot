"""
RankBM25Store — rank-bm25 implementation with pickle persistence.

Design:
  - Implements BaseBM25Store using the `rank-bm25` library (BM25Okapi).
  - Only text is indexed; chunk_id is the bridge to metadata in ChunkStore.

Internal data layout::

    _corpus_ids:    list[str]    — ordered list of chunk_ids
    _corpus_tokens: list[list[str]] — tokenised text per chunk (parallel to above)
    _bm25:          BM25Okapi | None — rebuilt on every mutation, lazy on load

The index is rebuilt from scratch on every add/delete because BM25Okapi does
not support incremental updates.  For large corpora (>100k chunks) this becomes
slow; in that case replace the implementation with an Elasticsearch/OpenSearch
backend while keeping the same BaseBM25Store interface.

Pickle file layout:
    {"corpus_ids": [...], "corpus_tokens": [...]}
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Optional

from app.services.ingest_data.ingest.base import BaseBM25Store, BM25SearchResult
from app.services.ingest_data.ingest.chunk_builder import Chunk

# Attempt to import BM25Okapi at module level
from rank_bm25 import BM25Okapi


# ---------------------------------------------------------------------------
# Tokeniser (simple, language-agnostic)
# ---------------------------------------------------------------------------

# Split on whitespace and punctuation, lowercase.
_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def _tokenise(text: str) -> list[str]:
    """Lowercase, split on non-word characters, drop empty tokens."""
    return [t for t in _TOKEN_RE.split(text.lower()) if t]


# ---------------------------------------------------------------------------
# RankBM25Store implementation
# ---------------------------------------------------------------------------


class RankBM25Store(BaseBM25Store):
    """
    BM25 index backed by `rank-bm25` (BM25Okapi) with pickle persistence.

    Usage::

        store = RankBM25Store(index_path="type1_data/bm25.pkl")
        store.load()               # load existing index (no-op on first run)
        store.add(chunks)
        store.save()

        results = store.search("quy định xử lý hồ sơ", top_k=10)
        # → [BM25SearchResult(chunk_id="chunk_000042", score=3.14), ...]
    """

    def __init__(self, index_path: str | Path) -> None:
        if BM25Okapi is None:
            raise ImportError(
                "rank-bm25 is required for RankBM25Store. "
                "Install it with: pip install rank-bm25"
            )

        self._index_path = Path(index_path)
        self._index_path.parent.mkdir(parents=True, exist_ok=True)

        self._corpus_ids: list[str] = []
        self._corpus_tokens: list[list[str]] = []
        self._bm25: Optional[BM25OkapiType] = None  # type: ignore[valid-type]

    # ------------------------------------------------------------------
    # BaseBM25Store implementation
    # ------------------------------------------------------------------

    def add(self, chunks: list[Chunk]) -> None:
        """
        Add chunks to the index.

        If a chunk_id already exists it is replaced (old entry removed first).
        """
        if not chunks:
            return

        # Build lookup for fast duplicate detection
        existing_ids = set(self._corpus_ids)

        new_ids: list[str] = []
        new_tokens: list[list[str]] = []

        for chunk in chunks:
            if chunk.chunk_id in existing_ids:
                # Replace: remove old entry
                idx = self._corpus_ids.index(chunk.chunk_id)
                self._corpus_ids.pop(idx)
                self._corpus_tokens.pop(idx)
            new_ids.append(chunk.chunk_id)
            new_tokens.append(_tokenise(chunk.text))

        self._corpus_ids.extend(new_ids)
        self._corpus_tokens.extend(new_tokens)
        self._rebuild_index()

    def delete(self, chunk_ids: list[str]) -> None:
        """Remove chunks by id."""
        if not chunk_ids:
            return

        ids_to_remove = set(chunk_ids)
        pairs = [
            (cid, tok)
            for cid, tok in zip(self._corpus_ids, self._corpus_tokens)
            if cid not in ids_to_remove
        ]
        if not pairs:
            self._corpus_ids = []
            self._corpus_tokens = []
            self._bm25 = None
            return

        self._corpus_ids, self._corpus_tokens = map(list, zip(*pairs))
        self._rebuild_index()

    def delete_by_document(self, document_id: str, chunk_ids: list[str]) -> None:
        """Remove all chunks belonging to *document_id* using their chunk_ids."""
        self.delete(chunk_ids)

    def search(self, query: str, top_k: int = 10) -> list[BM25SearchResult]:
        """Keyword search using BM25Okapi scoring."""
        if self._bm25 is None or not self._corpus_ids:
            return []

        query_tokens = _tokenise(query)
        if not query_tokens:
            return []

        scores: list[float] = self._bm25.get_scores(query_tokens).tolist()  # type: ignore[union-attr]

        # Pair scores with chunk_ids and sort descending
        ranked = sorted(
            zip(self._corpus_ids, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        return [
            BM25SearchResult(chunk_id=cid, score=score)
            for cid, score in ranked[:top_k]
            if score > 0  # omit zero-score (no term overlap)
        ]

    def save(self) -> None:
        """Pickle the corpus to disk."""
        payload = {
            "corpus_ids": self._corpus_ids,
            "corpus_tokens": self._corpus_tokens,
        }
        with open(self._index_path, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def load(self) -> None:
        """Load a pickled corpus from disk.  No-op if the file does not exist."""
        if not self._index_path.exists():
            return
        with open(self._index_path, "rb") as fh:
            payload = pickle.load(fh)
        self._corpus_ids = payload.get("corpus_ids", [])
        self._corpus_tokens = payload.get("corpus_tokens", [])
        self._rebuild_index()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_index(self) -> None:
        """Rebuild BM25Okapi from the current corpus."""
        if self._corpus_tokens:
            self._bm25 = BM25Okapi(self._corpus_tokens)  # type: ignore[misc]
        else:
            self._bm25 = None


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "BaseBM25Store",
    "BM25SearchResult",
    "RankBM25Store",
]
