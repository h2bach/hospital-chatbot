from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rag_core.chunking import ChunkingConfig, chunk_document
from rag_core.chunking.structure import content_hash, stable_id
from rag_core.parsing import parse_markdown
from rag_core.schemas import Chunk, CitationSpan, Document, DocumentVersion, Section


@dataclass(slots=True)
class IngestionResult:
    document: Document
    version: DocumentVersion
    sections: list[Section]
    chunks: list[Chunk]
    citations: list[CitationSpan]
    normalized_markdown: str
    skipped_as_duplicate: bool = False


def ingest_markdown(source: str, config: dict, chunking: ChunkingConfig | None = None) -> IngestionResult:
    parsed = parse_markdown(source, config.get("title", "Untitled"))
    digest = content_hash(source)
    document_id = config.get("document_id") or stable_id("doc", config.get("source_uri", parsed.title))
    version_number = int(config.get("version_number", 1))
    version_id = config.get("version_id") or stable_id("ver", document_id, version_number, digest)
    document_fields = {key: value for key, value in config.items() if key in Document.__dataclass_fields__}
    document_fields.update(document_id=document_id, title=config.get("title", parsed.title), content_hash=digest,
                           latest_version_id=version_id)
    document = Document(**document_fields)
    version = DocumentVersion(
        version_id=version_id,
        document_id=document_id,
        version_number=version_number,
        status=config.get("version_status", "published"),
        issued_date=config.get("issued_date"),
        effective_from=document.effective_from,
        effective_to=document.effective_to,
        supersedes_version_id=config.get("supersedes_version_id"),
        content_hash=digest,
        embedding_model=config.get("embedding_model", "hashing-baseline-v1"),
    )
    sections, chunks, citations = chunk_document(parsed, document, version, chunking)
    return IngestionResult(document, version, sections, chunks, citations, parsed.normalized_markdown)


def write_artifacts(result: IngestionResult, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "document.json", result.document.to_dict())
    _write_json(output / "version.json", result.version.to_dict())
    _write_jsonl(output / "sections.jsonl", result.sections)
    _write_jsonl(output / "chunks.jsonl", result.chunks)
    _write_jsonl(output / "citations.jsonl", result.citations)
    (output / "normalized.md").write_text(result.normalized_markdown, encoding="utf-8")
    _write_json(output / "ingestion_report.json", {
        "document_id": result.document.document_id,
        "version_id": result.version.version_id,
        "section_count": len(result.sections),
        "chunk_count": len(result.chunks),
        "citation_count": len(result.citations),
        "content_hash": result.document.content_hash,
    })


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[object]) -> None:
    path.write_text("".join(json.dumps(value.to_dict(), ensure_ascii=False) + "\n" for value in values), encoding="utf-8")

