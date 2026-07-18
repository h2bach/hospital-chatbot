from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from rag_core.parsing import ParsedMarkdown
from rag_core.schemas import Chunk, CitationSpan, Document, DocumentVersion, Section


@dataclass(slots=True)
class ChunkingConfig:
    target_tokens: int = 256
    max_tokens: int = 384
    overlap_tokens: int = 32


def stable_id(prefix: str, *parts: object, length: int = 20) -> str:
    value = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:length]}"


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE)))


def _sentence_groups(text: str, max_tokens: int) -> list[str]:
    if estimate_tokens(text) <= max_tokens:
        return [text]
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    groups: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in sentences:
        tokens = estimate_tokens(sentence)
        if current and size + tokens > max_tokens:
            groups.append(" ".join(current))
            current, size = [], 0
        current.append(sentence)
        size += tokens
    if current:
        groups.append(" ".join(current))
    return groups


def _table_groups(text: str, max_tokens: int) -> list[str]:
    if estimate_tokens(text) <= max_tokens:
        return [text]
    lines = [line for line in text.splitlines() if line.strip()]
    # Keep each source row intact when possible. The separator row carries no
    # retrieval value; column meaning is already represented in the table header.
    rows = [line for index, line in enumerate(lines) if index != 1]
    groups: list[str] = []
    for row in rows:
        groups.extend(_sentence_groups(row, max_tokens))
    return groups


def chunk_document(
    parsed: ParsedMarkdown,
    document: Document,
    version: DocumentVersion,
    config: ChunkingConfig | None = None,
) -> tuple[list[Section], list[Chunk], list[CitationSpan]]:
    cfg = config or ChunkingConfig()
    sections: list[Section] = []
    section_by_path: dict[tuple[str, ...], Section] = {}
    section_order = 0

    for node in parsed.nodes:
        if node.node_type != "heading":
            continue
        path = tuple(node.heading_path)
        parent = section_by_path.get(path[:-1])
        section = Section(
            section_id=stable_id("sec", document.document_id, version.version_id, *path),
            document_id=document.document_id,
            version_id=version.version_id,
            parent_section_id=parent.section_id if parent else None,
            section_level=node.level,
            section_order=section_order,
            heading=node.text,
            heading_path=list(path),
            page_start=node.page_start,
            page_end=node.page_end,
            offset_start=node.offset_start,
            offset_end=node.offset_end,
        )
        section_order += 1
        sections.append(section)
        section_by_path[path] = section

    root_path = (parsed.title,)
    if not sections:
        root = Section(stable_id("sec", document.document_id, version.version_id, parsed.title), document.document_id,
                       version.version_id, None, 1, 0, parsed.title, [parsed.title])
        sections.append(root)
        section_by_path[root_path] = root

    chunks: list[Chunk] = []
    for node in parsed.nodes:
        if node.node_type == "heading" or not node.text.strip():
            continue
        path = tuple(node.heading_path) or tuple(sections[0].heading_path)
        section = section_by_path.get(path) or sections[0]
        # Tables are row-split only when they exceed the hard limit. Lists, FAQ and
        # code remain atomic; paragraphs split on sentence boundaries.
        if node.node_type == "table":
            parts = _table_groups(node.text, cfg.max_tokens)
        elif node.node_type in {"list", "faq", "code"}:
            parts = [node.text]
        else:
            parts = _sentence_groups(node.text, cfg.max_tokens)
        for part in parts:
            idx = len(chunks)
            chunk_id = stable_id("chk", document.document_id, version.version_id, section.section_id, idx, part)
            heading_prefix = " > ".join(section.heading_path)
            chunk = Chunk(
                chunk_id=chunk_id,
                document_id=document.document_id,
                version_id=version.version_id,
                section_id=section.section_id,
                chunk_index=idx,
                content_type=node.node_type,
                content_text=part,
                retrieval_text=f"{heading_prefix}.\n{part}" if heading_prefix else part,
                heading_path=list(section.heading_path),
                page_start=node.page_start,
                page_end=node.page_end,
                offset_start=node.offset_start,
                offset_end=node.offset_end,
                token_count=estimate_tokens(part),
                content_hash=content_hash(part),
                authority_level=document.authority_level,
                effective_from=document.effective_from,
                effective_to=document.effective_to,
            )
            chunks.append(chunk)

    for index, chunk in enumerate(chunks):
        chunk.previous_chunk_id = chunks[index - 1].chunk_id if index else None
        chunk.next_chunk_id = chunks[index + 1].chunk_id if index + 1 < len(chunks) else None

    citations = [CitationSpan(
        citation_id=stable_id("cit", chunk.chunk_id, chunk.offset_start, chunk.offset_end),
        chunk_id=chunk.chunk_id,
        page=chunk.page_start,
        section_id=chunk.section_id,
        start_offset=chunk.offset_start,
        end_offset=chunk.offset_end,
        quote_text=chunk.content_text,
        source_anchor=f"page={chunk.page_start or ''}&section={chunk.section_id}&start={chunk.offset_start}&end={chunk.offset_end}",
    ) for chunk in chunks]
    return sections, chunks, citations
