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

class Citation(BaseModel):
    """Structured citation built from chunk metadata (no LLM involved)."""

    chunk_id: str
    score: float
    document: str | None = None
    source_file: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    line_start: int | None = None
    line_end: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    version: str | None = None


class RetrieveContext(BaseModel):
    """Single context item returned from retrieval."""

    chunk_id: str = Field(description="Deterministic chunk identifier")
    content: str = Field(description="The retrieved content/text")
    score: float = Field(description="Fused relevance score (RRF)")
    metadata: dict = Field(default_factory=dict, description="Associated metadata")


class RetrieveResponse(BaseModel):
    """Successful response from POST /retrieve (retrieval-only)."""

    query: str
    sub_queries: list[str] = Field(default_factory=list)
    contexts: list[RetrieveContext]
    citations: list[Citation] = Field(default_factory=list)
    total_results: int
    timings_ms: dict = Field(default_factory=dict)
    trace_id: str | None = None
    latency_ms: float
    timestamp: datetime = Field(default_factory=_utcnow)


# ── Ingest ───────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    """Successful response from POST /ingest."""

    status: str = Field(description="Status of ingestion: 'started', 'processing', 'completed'")
    data_type: str
    records_fetched: int | None = None
    records_processed: int | None = None
    job_id: str | None = Field(default=None, description="Job ID for async tracking")
    message: str | None = None
    details: list[dict] | None = Field(
        default=None, description="Per-document ingestion details"
    )
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
