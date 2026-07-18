"""
POST /retrieve — Retrieval-only hybrid search.

Runs the retrieval pipeline (query rewrite/decompose -> parallel hybrid search
-> RRF merge) and returns contexts + structured citations + per-stage timings.

This service does NOT generate an answer. The backend decides whether to call
an LLM for synthesis using the returned context.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_agent_service
from app.schemas.request import RetrieveRequest
from app.schemas.response import (
    Citation,
    ErrorResponse,
    RetrieveContext,
    RetrieveResponse,
)
from app.services.base import AgentService

router = APIRouter(prefix="/retrieve", tags=["Retrieval"])


@router.post(
    "",
    response_model=RetrieveResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Retrieval error"},
    },
    summary="Hybrid retrieval (BM25 + vector) with citations",
    description=(
        "Rewrite and decompose the query, run parallel hybrid search across "
        "sub-queries, fuse with RRF, and return ranked contexts with citations."
    ),
)
async def retrieve(
    request: RetrieveRequest,
    agent: AgentService = Depends(get_agent_service),
) -> RetrieveResponse:
    """Retrieve relevant context via hybrid search."""
    result = await agent.retrieve(query=request.query, top_k=request.top_k)

    contexts = [
        RetrieveContext(
            chunk_id=c["chunk_id"],
            content=c["text"],
            score=c["score"],
            metadata=c["metadata"],
        )
        for c in result["contexts"]
    ]
    citations = [Citation(**c) for c in result["citations"]]

    return RetrieveResponse(
        query=result["query"],
        sub_queries=result["sub_queries"],
        contexts=contexts,
        citations=citations,
        total_results=result["total_results"],
        timings_ms=result["timings_ms"],
        trace_id=result["trace_id"],
        latency_ms=result["latency_ms"],
    )
