"""
Request schemas — validated by FastAPI before reaching any endpoint.
"""

from pydantic import BaseModel, Field

class RetrieveRequest(BaseModel):
    """Body for POST /retrieve."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="Query string for the RAG pipeline",
        examples=["What is the company policy on remote work?"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for multi-turn conversation tracking",
    )
    max_iterations: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum planner iterations before force-stopping",
    )


class IngestRequest(BaseModel):
    """Body for POST /ingest."""

    data_source_api: str = Field(
        ...,
        description="Backend API endpoint to fetch data from",
        examples=["https://backend.example.com/api/data"],
    )
    data_type: str = Field(
        ...,
        description="Type of data being ingested",
        examples=["document"],
    )
    auth_token: str | None = Field(
        default=None,
        description="Authentication token for backend API",
    )
    metadata: dict | None = Field(
        default=None,
        description="Additional metadata for processing",
    )


class UpdateDataRequest(BaseModel):
    """Body for POST /update."""

    operation: str = Field(
        ...,
        description="Operation type: 'create', 'update', or 'delete'",
        examples=["update"],
    )
    data_type: str = Field(
        ...,
        description="Type of data being updated",
        examples=["document"],
    )
    record_ids: list[str] = Field(
        ...,
        description="List of record IDs affected by this operation",
        examples=[["doc_123", "doc_456"]],
    )
    data_source_api: str | None = Field(
        default=None,
        description="Optional: Backend API to fetch updated data",
    )
    metadata: dict | None = Field(
        default=None,
        description="Additional context about the update",
    )
