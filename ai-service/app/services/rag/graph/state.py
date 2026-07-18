"""
RetrievalState — state for the retrieval-only RAG graph.

Flow:
    query_transform (LLM, once) -> sub_queries
        -> fan-out to hybrid_search workers (parallel, no LLM)
        -> merge (RRF across workers, dedupe, citations; no LLM)
        -> contexts + citations returned to the backend

The backend (not this service) decides whether to call an LLM to synthesize
an answer. This service is retrieval-only.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from pydantic import BaseModel, Field


class RetrievedItem(BaseModel):
    """A single retrieved chunk with fused score and full metadata."""

    chunk_id: str
    score: float
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(BaseModel):
    """Output of one hybrid-search worker (one sub-query)."""

    sub_query: str
    items: list[RetrievedItem] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class RetrievalState(BaseModel):
    """Single source of truth passed through the graph."""

    # Input
    query: str
    trace_id: str = ""
    top_k: int = 12

    # After query_transform
    sub_queries: list[str] = Field(default_factory=list)

    # Fan-in target: workers append their results here.
    # Annotated + operator.add lets parallel branches merge into one list.
    worker_results: Annotated[list[WorkerResult], operator.add] = Field(
        default_factory=list
    )

    # After merge
    contexts: list[RetrievedItem] = Field(default_factory=list)

    # Timings collected across the pipeline (ms)
    timings_ms: dict[str, float] = Field(default_factory=dict)


__all__ = ["RetrievedItem", "WorkerResult", "RetrievalState"]
