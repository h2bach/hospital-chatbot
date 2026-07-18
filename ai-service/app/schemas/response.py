"""
Response schemas — guarantees a consistent JSON contract for every endpoint.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Chat ─────────────────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    """Successful response from POST /chat."""

    answer: str
    model: str
    conversation_id: str | None = None
    usage: dict | None = None
    latency_ms: float
    timestamp: datetime = Field(default_factory=_utcnow)


# ── Health ───────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str = "ok"
    version: str
    model: str
    timestamp: datetime = Field(default_factory=_utcnow)


# ── Error ────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standardised error envelope returned by all exception handlers."""

    error: str
    detail: str | None = None
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=_utcnow)


# ── Retrieve ─────────────────────────────────────────────────────────────

class SourceCitation(BaseModel):
    """
    Citation metadata for a single source chunk used in the answer.
    
    Provides full traceability from answer back to original document.
    """
    
    citation_number: int = Field(
        description="Citation number as referenced in the answer (e.g., [1], [2])"
    )
    
    chunk_id: str = Field(
        description="Unique identifier for this chunk in the database"
    )
    
    document_id: str = Field(
        description="Document this chunk belongs to"
    )
    
    document_title: str | None = Field(
        default=None,
        description="Human-readable title of the source document"
    )
    
    section: str | None = Field(
        default=None,
        description="Top-level section/chapter name"
    )
    
    heading_path: list[str] = Field(
        default_factory=list,
        description="Full heading hierarchy (e.g., ['Quy trình khám', 'Đăng ký', 'Bước 1'])"
    )
    
    page_start: int | None = Field(
        default=None,
        description="Starting page number in the original document"
    )
    
    page_end: int | None = Field(
        default=None,
        description="Ending page number (same as page_start for single-page chunks)"
    )
    
    relevance_score: float | None = Field(
        default=None,
        description="Search relevance score (0.0-1.0, higher is more relevant)"
    )
    
    content_preview: str | None = Field(
        default=None,
        description="First 200 characters of the chunk content for preview"
    )


class SourceDocument(BaseModel):
    """
    Aggregated information about a source document used in the answer.
    
    Groups multiple citations from the same document for better UX.
    """
    
    document_id: str = Field(
        description="Unique document identifier"
    )
    
    title: str = Field(
        description="Document title"
    )
    
    source_path: str | None = Field(
        default=None,
        description="Original file path or URL of the document"
    )
    
    citation_count: int = Field(
        description="Number of times this document was cited in the answer"
    )
    
    sections_referenced: list[str] = Field(
        default_factory=list,
        description="List of sections from this document that were used"
    )


class RetrieveResponse(BaseModel):
    """Successful response from POST /retrieve.
    
    The RAG pipeline runs the full graph (planner → subgraphs → synthesizer)
    and returns a synthesized answer along with full citation metadata for 
    transparency and user trust.
    """

    query: str = Field(
        description="Original user query"
    )
    
    answer: str = Field(
        description="Synthesized answer from the RAG pipeline with [N] citation markers"
    )
    
    citations: list[SourceCitation] = Field(
        default_factory=list,
        description="Detailed metadata for each citation referenced in the answer"
    )
    
    source_documents: list[SourceDocument] = Field(
        default_factory=list,
        description="Aggregated information about all documents used"
    )
    
    trace_id: str = Field(
        description="Unique trace ID for this request (for debugging)"
    )
    
    iterations: int = Field(
        description="Number of planner iterations executed"
    )
    
    result_count: int = Field(
        description="Total number of chunks retrieved across all searches"
    )
    
    error_count: int = Field(
        description="Number of failed retrieval branches"
    )
    
    confidence: str = Field(
        default="medium",
        description="Answer confidence level: 'high', 'medium', 'low' based on source quality"
    )
    
    latency_ms: float = Field(
        description="Total pipeline execution time in milliseconds"
    )
    
    timestamp: datetime = Field(
        default_factory=_utcnow,
        description="Response generation timestamp"
    )


# ── Ingest ───────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    """Successful response from POST /ingest."""

    status: str = Field(description="Status of ingestion: 'started', 'processing', 'completed'")
    data_type: str
    records_fetched: int | None = None
    records_processed: int | None = None
    job_id: str | None = Field(default=None, description="Job ID for async tracking")
    message: str | None = None
    latency_ms: float
    timestamp: datetime = Field(default_factory=_utcnow)


# ── Update ───────────────────────────────────────────────────────────────

class UpdateDataResponse(BaseModel):
    """Successful response from POST /update."""

    status: str = Field(description="Status: 'success', 'partial', 'failed'")
    operation: str
    data_type: str
    records_affected: int
    records_updated: int
    records_failed: int
    failed_ids: list[str] = Field(default_factory=list)
    message: str | None = None
    latency_ms: float
    timestamp: datetime = Field(default_factory=_utcnow)
