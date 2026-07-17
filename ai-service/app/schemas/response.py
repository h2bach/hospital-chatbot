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

class RetrieveContext(BaseModel):
    """Single context item returned from retrieval."""
    
    content: str = Field(description="The retrieved content/text")
    score: float = Field(description="Relevance score")
    metadata: dict = Field(default_factory=dict, description="Associated metadata")
    source: str | None = Field(default=None, description="Source identifier")


class RetrieveResponse(BaseModel):
    """Successful response from POST /retrieve."""

    query: str
    data_type: str
    contexts: list[RetrieveContext]
    total_results: int
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
