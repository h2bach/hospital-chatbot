"""
Chunk builder — Sections -> traceable Chunks.

Strategy (semantic-first, size-aware):
    1. Each markdown Section becomes one candidate chunk.
    2. Tiny sections (heading-only or < min tokens) merge into the next
       sibling/child so we never emit empty knowledge units.
    3. Oversized sections split on paragraph/line boundaries (never mid-line),
       keeping the same heading_path and metadata; sub-chunks get an index.

Each chunk carries two text views:
    - embed_text: "heading > path\n\nbody"  (contextual retrieval)
    - bm25_text:  body only                 (avoids keyword noise)

chunk_id is deterministic:
    <document_id>::<slug(heading_path)>::<chunk_index>
so re-ingesting the same document yields identical ids (idempotent upsert).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Optional

from app.services.ingest_data.ingest.base import Chunk
from app.services.ingest_data.ingest.markdown_parser import Section, parse_markdown


def _approx_tokens(text: str) -> int:
    """Cheap token estimate: whitespace-separated word count."""
    return len(text.split())


def _slug(text: str, max_len: int = 40) -> str:
    """ASCII slug for readable, stable chunk ids."""
    norm = unicodedata.normalize("NFKD", text)
    norm = norm.encode("ascii", "ignore").decode("ascii")
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return norm[:max_len] or "section"


def _document_id(source_file: str) -> str:
    """Stable document id from the source file name."""
    base = source_file.replace("\\", "/").split("/")[-1]
    stem = base.rsplit(".", 1)[0]
    return _slug(stem, max_len=60)


# Character cap protects the embedding model's real token limit. Whitespace
# token counts badly undercount dense Vietnamese table text (~2 chars/token),
# so we bound characters too. nomic-embed-text context is 2048 tokens; keep a
# conservative budget with headroom for the prepended heading path.
_MAX_CHARS_PER_CHUNK = 2400


def _oversized(text: str, max_tokens: int) -> bool:
    return _approx_tokens(text) > max_tokens or len(text) > _MAX_CHARS_PER_CHUNK


def _hard_slice(text: str, max_chars: int) -> list[str]:
    """Split a too-long single line into <= max_chars pieces (last resort)."""
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _split_body(body: str, max_tokens: int) -> list[str]:
    """
    Split an oversized body on paragraph boundaries, then hard lines.

    Never splits mid-line. Paragraphs (blank-line separated) are packed
    greedily up to max_tokens AND a character budget (protects the embedding
    model's real token limit for dense Vietnamese/table text).
    """
    paragraphs = re.split(r"\n\s*\n", body)
    parts: list[str] = []
    current: list[str] = []
    current_tokens = 0
    current_chars = 0

    def flush_current() -> None:
        nonlocal current, current_tokens, current_chars
        if current:
            parts.append("\n\n".join(current))
            current, current_tokens, current_chars = [], 0, 0

    for para in paragraphs:
        para = para.strip("\n")
        if not para.strip():
            continue
        ptok = _approx_tokens(para)
        pchar = len(para)

        if _oversized(para, max_tokens):
            # Flush current buffer first, then split this paragraph line-by-line
            flush_current()
            line_buf: list[str] = []
            line_tokens = 0
            line_chars = 0
            for ln in para.splitlines():
                # A single line longer than the budget can't split on boundaries;
                # hard-slice it by characters as a last resort.
                for piece in _hard_slice(ln, _MAX_CHARS_PER_CHUNK):
                    lt = _approx_tokens(piece)
                    lc = len(piece)
                    if line_buf and (
                        line_tokens + lt > max_tokens
                        or line_chars + lc > _MAX_CHARS_PER_CHUNK
                    ):
                        parts.append("\n".join(line_buf))
                        line_buf, line_tokens, line_chars = [], 0, 0
                    line_buf.append(piece)
                    line_tokens += lt
                    line_chars += lc
            if line_buf:
                parts.append("\n".join(line_buf))
            continue

        if current and (
            current_tokens + ptok > max_tokens
            or current_chars + pchar > _MAX_CHARS_PER_CHUNK
        ):
            flush_current()
        current.append(para)
        current_tokens += ptok
        current_chars += pchar

    flush_current()

    return parts or [body.strip()]


def _build_embed_text(heading_path: list[str], body: str) -> str:
    """Prepend the heading path as context (Contextual Retrieval)."""
    if heading_path:
        header = " > ".join(heading_path)
        return f"{header}\n\n{body}".strip()
    return body.strip()


def build_chunks(
    text: str,
    source_file: str,
    document_name: Optional[str] = None,
    version: Optional[str] = None,
    max_tokens: int = 512,
    min_tokens: int = 32,
) -> list[Chunk]:
    """
    Parse markdown and build traceable chunks.

    Args:
        text: Raw markdown content.
        source_file: File name/path (used for document_id + provenance).
        document_name: Human-readable document title (defaults to first H1).
        version: Optional version tag stored in metadata.
        max_tokens: Soft cap per chunk; larger sections are split.
        min_tokens: Sections smaller than this merge into the next one.

    Returns:
        Ordered list of Chunk.
    """
    sections = parse_markdown(text)
    document_id = _document_id(source_file)

    # Default document name = first H1 heading, else file stem
    if not document_name:
        h1 = next((s.heading for s in sections if s.level == 1 and s.heading), None)
        document_name = h1 or document_id

    # Merge tiny sections forward into the next section
    merged: list[Section] = []
    carry: Optional[Section] = None
    for sec in sections:
        if carry is not None:
            # Prepend carried heading context into this section's body
            prefix = carry.heading
            sec.body = (f"{prefix}\n{carry.body}\n\n{sec.body}").strip("\n") if carry.body else sec.body
            sec.line_start = carry.line_start
            carry = None

        body_tokens = _approx_tokens(sec.body)
        if body_tokens < min_tokens and sec.heading:
            # Too small on its own — carry forward to merge with the next section
            carry = sec
            continue
        merged.append(sec)

    if carry is not None:
        merged.append(carry)

    chunks: list[Chunk] = []
    for sec in merged:
        if not sec.body.strip() and not sec.heading:
            continue

        if not _oversized(sec.body, max_tokens):
            parts = [sec.body]
        else:
            parts = _split_body(sec.body, max_tokens)

        multi = len(parts) > 1
        path_slug = _slug("-".join(sec.heading_path) or "preamble", max_len=50)

        for i, part in enumerate(parts):
            body = part.strip()
            if not body:
                continue
            chunk_index = i
            chunk_id = f"{document_id}::{path_slug}::{chunk_index}"
            # Guard against collisions across identical heading paths
            if any(c.chunk_id == chunk_id for c in chunks):
                digest = hashlib.md5(body.encode("utf-8")).hexdigest()[:8]
                chunk_id = f"{document_id}::{path_slug}::{chunk_index}-{digest}"

            embed_text = _build_embed_text(sec.heading_path, body)

            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_name=document_name,
                    source_file=source_file.replace("\\", "/").split("/")[-1],
                    text=body,
                    embed_text=embed_text,
                    bm25_text=body,
                    heading_path=list(sec.heading_path),
                    line_start=sec.line_start,
                    line_end=sec.line_end,
                    token_count=_approx_tokens(body),
                    version=version,
                )
            )

    return chunks


__all__ = ["build_chunks"]
