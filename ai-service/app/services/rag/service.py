"""
RAGService — Retrieval-Augmented Generation Service built with LangGraph.

This is the core RAG service that orchestrates the multi-agent RAG pipeline:
    - Uses MainState for comprehensive state management
    - Graph from main_graph.py handles full workflow
    - Supports iterative planning and parallel execution

Architecture:
    START → planner → [router → subgraphs → merge → planner] → synthesizer → END

The graph construction is separated:
    1. build_rag_graph() — Initialize structure
    2. compile_rag_graph() — Compile for execution

The invoke() and stream() methods satisfy the AgentService interface,
so the API layer never needs to change.
"""

import logging
import time
import uuid
from typing import Any, AsyncIterator

from app.config import Settings
from app.services.base import AgentService
from app.services.rag.llm_factory import create_llm
from app.services.rag.graph.main_graph import (
    build_rag_graph,
    compile_rag_graph,
)
from app.services.rag.graph.main_state import MainState

logger = logging.getLogger(__name__)


class RAGService(AgentService):
    """
    RAG Service — LangGraph multi-agent implementation for RAG.

    Current graph::

        START → planner → [router → subgraphs → merge → planner] → synthesizer → END

    Graph construction is separated into:
        1. build_rag_graph() — Initialize structure (nodes + edges)
        2. compile_rag_graph() — Compile for execution
    
    Uses MainState (Pydantic) for comprehensive state management across all nodes.
    LLM is created via tier-based create_llm() factory with automatic fallback.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        # Build and compile graph using separated logic
        graph_builder = build_rag_graph(settings)
        self.graph = compile_rag_graph(graph_builder)
        logger.info("RAGService initialized with main graph")

    # ── AgentService Interface ───────────────────────────────────────

    async def invoke(self, message: str, **kwargs: Any) -> dict:
        """
        Run the full graph and return the complete result.
        
        This method:
            1. Creates initial MainState with trace_id
            2. Invokes the compiled graph
            3. Extracts final_answer from state
            4. Returns formatted response
        
        Args:
            message: User query string
            **kwargs: Optional parameters (session_id, max_iterations, etc.)
            
        Returns:
            dict with: answer, trace_id, iterations, latency_ms
        """
        start = time.perf_counter()
        trace_id = str(uuid.uuid4())

        logger.info(
            "Agent invoke started",
            extra={
                "trace_id": trace_id,
                "message_length": len(message),
            },
        )

        try:
            # Build initial MainState
            initial_state = MainState(
                trace_id=trace_id,
                session_id=kwargs.get("session_id"),
                query=message,
                max_iterations=kwargs.get("max_iterations", 5),
            )

            # Invoke the graph (returns dict, not MainState object)
            result = await self.graph.ainvoke(initial_state)
            
            latency_ms = (time.perf_counter() - start) * 1000

            logger.info(
                "Agent invoke completed",
                extra={
                    "trace_id": trace_id,
                    "latency_ms": f"{latency_ms:.1f}",
                    "iterations": result.get("iteration", 0),
                    "result_count": len(result.get("branch_results", [])),
                },
            )

            return {
                "answer": result.get("final_answer", ""),
                "trace_id": trace_id,
                "iterations": result.get("iteration", 0),
                "result_count": len(result.get("branch_results", [])),
                "error_count": len(result.get("errors", [])),
                "latency_ms": round(latency_ms, 1),
            }

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "Agent invoke failed",
                extra={
                    "trace_id": trace_id,
                    "latency_ms": f"{latency_ms:.1f}",
                    "error": str(exc),
                },
            )
            raise

    async def stream(self, message: str, **kwargs: Any) -> AsyncIterator[str]:
        """
        Stream tokens directly from the LLM.
        
        Note: This bypasses the full graph for simple streaming use cases.
        For full RAG pipeline, use invoke() instead.
        
        This is kept for backward compatibility and simple chat scenarios.
        
        Args:
            message: User query string
            **kwargs: Optional parameters
            
        Yields:
            str: Token chunks from LLM
        """
        start = time.perf_counter()

        logger.info(
            "Agent stream started",
            extra={"message_length": len(message)},
        )

        # Get LLM instance via tier-based factory (default to middle tier)
        llm = create_llm(self.settings, tier="middle")
        
        async for chunk in llm.astream(message):
            if chunk.content:
                yield chunk.content

        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Agent stream completed",
            extra={"latency_ms": f"{latency_ms:.1f}"},
        )
