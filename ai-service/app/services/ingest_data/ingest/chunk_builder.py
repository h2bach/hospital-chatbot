"""
ChunkBuilder — Groups DocumentNodes into Chunks with full metadata.

Chunking strategy:
  - Accumulate nodes until estimated token count reaches chunk_size.
  - When a new heading is encountered that is at the same or higher level
    (i.e. lower heading number) as the previous heading, flush the current
    chunk first (natural section boundary).
  - Overlap: the last `chunk_overlap` characters of the previous chunk are
    prepended to the next chunk's text (simple character-based overlap so we
    never need a tokeniser as a hard dependency).
  - Page range: track page_start / page_end across all nodes in a chunk.
  - parent_heading_id: SHA1 of the heading_path tuple, stable identifier for
    the logical section that contains the chunk.  Used for neighbor expansion
    during retrieval without re-reading the source file.

Token estimation:
  Uses a fast heuristic: len(text) // 4  (≈ GPT tokeniser average).
  Accurate enough for chunking purposes; avoids a mandatory tiktoken dep.
  If tiktoken is installed it is used automatically for better accuracy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

from app.services.ingest_data.ingest.markdown_parser import DocumentNode

# ---------------------------------------------------------------------------
# Optional tiktoken for accurate token counts
# ---------------------------------------------------------------------------
try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:  # type: ignore[return]
        return len(_enc.encode(text))

except ImportError:  # tiktoken not installed — fall back to heuristic
    def _count_tokens(text: str) -> int:
        return len(text) // 4


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """A single chunk ready to be stored in VectorDB + BM25 + SQLite."""

    chunk_id: str                          # e.g. "chunk_000042"
    document_id: str
    text: str                              # clean text only — no injected metadata
    page_start: Optional[int]
    page_end: Optional[int]
    heading_path: list[str]                # snapshot when chunk was flushed
    section: str                           # heading_path[-1] or ""
    parent_heading_id: str                 # stable hash of heading_path
    offset_start: int                      # char offset within the full document
    offset_end: int


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class ChunkBuilder:
    """
    Converts a list of :class:`DocumentNode` objects into :class:`Chunk` objects.

    Usage::

        builder = ChunkBuilder(
            document_id="doc_abc123",
            chunk_size=1000,
            chunk_overlap=200,
        )
        chunks = builder.build(nodes)
    """

    def __init__(
        self,
        document_id: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        self._document_id = document_id
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, nodes: list[DocumentNode]) -> list[Chunk]:
        """
        Process *nodes* and return an ordered list of :class:`Chunk` objects.
        """
        chunks: list[Chunk] = []

        # Running state for the current in-progress chunk
        buffer_nodes: list[DocumentNode] = []
        buffer_tokens: int = 0
        overlap_tail: str = ""          # tail of the previous chunk for overlap
        char_offset: int = 0            # rolling character offset in the doc
        chunk_index: int = 0

        for node in nodes:
            node_tokens = _count_tokens(node.content)

            # Natural section boundary: flush when heading level resets context
            if (
                node.type == "heading"
                and node.level is not None
                and buffer_nodes
                and self._is_section_boundary(node, buffer_nodes)
            ):
                chunk = self._flush(
                    buffer_nodes,
                    chunk_index,
                    char_offset,
                    overlap_tail,
                )
                if chunk is not None:
                    # Update offsets and overlap after flush
                    char_offset = chunk.offset_end
                    overlap_tail = self._make_overlap_tail(chunk.text)
                    chunks.append(chunk)
                    chunk_index += 1
                buffer_nodes = []
                buffer_tokens = 0

            # Size boundary: flush when adding this node would overflow
            if buffer_tokens + node_tokens > self._chunk_size and buffer_nodes:
                chunk = self._flush(
                    buffer_nodes,
                    chunk_index,
                    char_offset,
                    overlap_tail,
                )
                if chunk is not None:
                    char_offset = chunk.offset_end
                    overlap_tail = self._make_overlap_tail(chunk.text)
                    chunks.append(chunk)
                    chunk_index += 1
                buffer_nodes = []
                buffer_tokens = 0

            buffer_nodes.append(node)
            buffer_tokens += node_tokens

        # Flush the remaining nodes
        if buffer_nodes:
            chunk = self._flush(
                buffer_nodes,
                chunk_index,
                char_offset,
                overlap_tail,
            )
            if chunk is not None:
                chunks.append(chunk)

        return chunks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _flush(
        self,
        nodes: list[DocumentNode],
        index: int,
        offset_start: int,
        overlap_tail: str,
    ) -> Optional[Chunk]:
        """Create a Chunk from the current buffer."""
        # Concatenate node content (skip heading nodes — they are captured
        # in heading_path and don't need to be duplicated in the text body)
        parts = [n.content for n in nodes if n.type != "heading"]
        if not parts and not overlap_tail:
            return None

        body = "\n\n".join(p for p in parts if p.strip())
        text = (overlap_tail + "\n\n" + body).strip() if overlap_tail else body

        if not text:
            return None

        # heading_path: use the path of the FIRST non-heading node so the
        # section label reflects where the chunk *starts*, not where it ends.
        # Fall back to the last heading node if the buffer is heading-only.
        path_node = next(
            (n for n in nodes if n.type != "heading"),
            nodes[-1],
        )
        heading_path = list(path_node.heading_path)

        # Page range
        pages = [n.page for n in nodes if n.page is not None]
        page_start = min(pages) if pages else None
        page_end = max(pages) if pages else None

        offset_end = offset_start + len(text)

        return Chunk(
            chunk_id=f"chunk_{index:06d}",
            document_id=self._document_id,
            text=text,
            page_start=page_start,
            page_end=page_end,
            heading_path=heading_path,
            section=heading_path[-1] if heading_path else "",
            parent_heading_id=_heading_id(heading_path),
            offset_start=offset_start,
            offset_end=offset_end,
        )

    def _make_overlap_tail(self, text: str) -> str:
        """Return the last `chunk_overlap` characters of *text*."""
        if self._chunk_overlap <= 0:
            return ""
        return text[-self._chunk_overlap :]

    @staticmethod
    def _is_section_boundary(
        new_heading: DocumentNode,
        buffer: list[DocumentNode],
    ) -> bool:
        """
        Return True when *new_heading* starts a new top-level section relative
        to the content already in *buffer*.

        We flush on any heading whose level is ≤ the level of the first heading
        seen in the current buffer (i.e. it is a sibling or ancestor section).
        """
        first_heading = next((n for n in buffer if n.type == "heading"), None)
        if first_heading is None:
            # Buffer has no heading yet → only flush for H1/H2 to avoid
            # splitting tiny sections unnecessarily.
            return (new_heading.level or 99) <= 2
        return (new_heading.level or 99) <= (first_heading.level or 99)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _heading_id(heading_path: list[str]) -> str:
    """
    Stable, short identifier for a heading path.

    Built as the first 12 hex chars of SHA-1(JSON(path)).
    Deterministic across runs — the same section always gets the same id.
    """
    raw = json.dumps(heading_path, ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]
