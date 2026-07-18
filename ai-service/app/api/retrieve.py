"""
POST /retrieve — Run the full RAG pipeline and return a synthesized answer.

Accepts a query, invokes the LangGraph multi-agent pipeline
(planner → subgraphs → synthesizer), and returns the final answer
along with execution metadata.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_agent_service
from app.schemas.request import RetrieveRequest
from app.schemas.response import ErrorResponse, RetrieveResponse
from app.services.base import AgentService

router = APIRouter(prefix="/retrieve", tags=["Retrieval"])


@router.post(
    "",
    response_model=RetrieveResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Retrieval or pipeline error"},
    },
    summary="Run RAG pipeline and retrieve answer",
    description=(
        "Invoke the full RAG pipeline: planner decomposes the query into tasks, "
        "subgraphs execute hybrid search (vector + BM25 + RRF), "
        "and the synthesizer produces a final answer. "
        "Returns the answer along with trace metadata."
    ),
)
async def retrieve(
    request: RetrieveRequest,
    agent: AgentService = Depends(get_agent_service),
) -> RetrieveResponse:
    """
    Run the full RAG pipeline for the given query.

    The pipeline:
        1. Planner analyses query and creates retrieval tasks
        2. Router dispatches tasks to type1/type2/type3 subgraphs in parallel
        3. Each subgraph runs hybrid search (BM25 + vector → RRF fusion)
        4. Merge aggregates all branch results
        5. Planner decides to finish or replan
        6. Synthesizer produces the final answer
    """
    result = await agent.invoke(
        message=request.query,
        session_id=request.session_id,
        max_iterations=request.max_iterations,
    )

    return RetrieveResponse(
        query=request.query,
        answer=result["answer"],
        trace_id=result["trace_id"],
        iterations=result["iterations"],
        result_count=result["result_count"],
        error_count=result["error_count"],
        latency_ms=result["latency_ms"],
    )
