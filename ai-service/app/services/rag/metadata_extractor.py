"""
Metadata extraction utilities for building citation-rich API responses.

Extracts detailed source metadata from branch_results to provide full
traceability and transparency in RAG answers.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from app.services.ingest_data.ingest.chunk_store import ChunkStore

logger = logging.getLogger(__name__)


def extract_citation_metadata(
    branch_results: list[dict],
    chunk_store: ChunkStore,
) -> tuple[list[dict], list[dict], str]:
    """
    Extract detailed citation metadata from branch_results.
    
    Args:
        branch_results: List of BranchResult dicts from MainState
        chunk_store: ChunkStore instance for fetching document titles
        
    Returns:
        Tuple of (citations, source_documents, confidence):
        - citations: List of SourceCitation dicts
        - source_documents: List of SourceDocument dicts
        - confidence: 'high', 'medium', or 'low'
    """
    
    citations: list[dict] = []
    doc_map: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "document_id": "",
        "title": "Unknown Document",
        "source_path": None,
        "citation_count": 0,
        "sections_referenced": set(),
    })
    
    citation_number = 1
    total_sources = 0
    successful_sources = 0
    
    for branch_result in branch_results:
        if branch_result.get("status") != "success":
            continue
            
        successful_sources += 1
        source_metadata = branch_result.get("source_metadata", [])
        total_sources += len(source_metadata)
        
        for meta in source_metadata:
            chunk_id = meta.get("chunk_id", "")
            document_id = meta.get("document_id", "")
            
            # Fetch document title from database
            doc_title = "Unknown Document"
            source_path = None
            try:
                doc_record = chunk_store.get_document(document_id)
                if doc_record:
                    doc_title = doc_record.title
                    source_path = doc_record.source
            except Exception as exc:
                logger.warning(
                    f"Failed to fetch document {document_id}: {exc}",
                    extra={"document_id": document_id}
                )
            
            # Build citation
            heading_path = meta.get("heading_path", [])
            section = meta.get("section", "")
            page_start = meta.get("page_start")
            page_end = meta.get("page_end")
            
            # Get content preview from chunk if available
            content_preview = None
            if "text" in meta:
                text = meta["text"]
                content_preview = text[:200] + "..." if len(text) > 200 else text
            
            citation = {
                "citation_number": citation_number,
                "chunk_id": chunk_id,
                "document_id": document_id,
                "document_title": doc_title,
                "section": section if section else None,
                "heading_path": heading_path,
                "page_start": page_start,
                "page_end": page_end,
                "relevance_score": None,  # Can add if we store scores
                "content_preview": content_preview,
            }
            
            citations.append(citation)
            citation_number += 1
            
            # Update document aggregation
            if document_id:
                doc_info = doc_map[document_id]
                doc_info["document_id"] = document_id
                doc_info["title"] = doc_title
                doc_info["source_path"] = source_path
                doc_info["citation_count"] += 1
                if section:
                    doc_info["sections_referenced"].add(section)
    
    # Convert doc_map to list of SourceDocument dicts
    source_documents = [
        {
            "document_id": doc_id,
            "title": info["title"],
            "source_path": info["source_path"],
            "citation_count": info["citation_count"],
            "sections_referenced": sorted(list(info["sections_referenced"])),
        }
        for doc_id, info in doc_map.items()
    ]
    
    # Calculate confidence based on source quality
    confidence = _calculate_confidence(
        total_sources=total_sources,
        successful_sources=successful_sources,
        citation_count=len(citations),
    )
    
    return citations, source_documents, confidence


def _calculate_confidence(
    total_sources: int,
    successful_sources: int,
    citation_count: int,
) -> str:
    """
    Calculate answer confidence level based on retrieval quality.
    
    Logic:
    - high: >=5 citations from successful searches
    - medium: 2-4 citations from successful searches
    - low: <2 citations or many failed searches
    """
    if citation_count >= 5 and successful_sources > 0:
        return "high"
    elif citation_count >= 2 and successful_sources > 0:
        return "medium"
    else:
        return "low"


def parse_citation_numbers_from_answer(answer: str) -> list[int]:
    """
    Parse citation markers [N] from the synthesized answer.
    
    Returns sorted list of citation numbers that appear in the answer.
    
    Example:
        Input: "Quy trình [1] bao gồm [2] và [3]."
        Output: [1, 2, 3]
    """
    pattern = r'\[(\d+)\]'
    matches = re.findall(pattern, answer)
    return sorted(set(int(m) for m in matches))
