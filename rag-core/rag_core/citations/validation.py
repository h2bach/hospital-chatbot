from __future__ import annotations

from html import escape

from rag_core.schemas import RetrievedChunk


def render_evidence(items: list[RetrievedChunk]) -> str:
    blocks = []
    for item in items:
        chunk = item.chunk
        blocks.append(
            f'<evidence chunk_id="{escape(chunk.chunk_id)}" document_id="{escape(chunk.document_id)}" '
            f'version_id="{escape(chunk.version_id)}" page_start="{chunk.page_start or ""}" '
            f'page_end="{chunk.page_end or ""}" section="{escape(" > ".join(chunk.heading_path))}" '
            f'authority_level="{chunk.authority_level}">\n{escape(chunk.content_text)}\n</evidence>'
        )
    return "\n\n".join(blocks)


def validate_citations(cited_chunk_ids: list[str], evidence: list[RetrievedChunk]) -> tuple[bool, list[str]]:
    available = {item.chunk.chunk_id for item in evidence}
    invalid = [chunk_id for chunk_id in cited_chunk_ids if chunk_id not in available]
    return not invalid, invalid

