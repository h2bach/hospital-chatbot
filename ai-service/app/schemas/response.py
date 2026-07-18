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

class RetrieveResponse(BaseModel):
    """Successful response from POST /retrieve.
    
    The RAG pipeline runs the full graph (planner → subgraphs → synthesizer)
    and returns a synthesized answer along with execution metadata.
    """

    query: str
    answer: str = Field(description="Synthesized answer from the RAG pipeline")
    trace_id: str = Field(description="Unique trace ID for this request")
    iterations: int = Field(description="Number of planner iterations executed")
    result_count: int = Field(description="Total branch results collected")
    error_count: int = Field(description="Number of failed branches")
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
