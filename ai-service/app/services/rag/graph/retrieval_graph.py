"""
Retrieval graph — the retrieval-only RAG pipeline.

    START
      -> query_transform   (LLM once: rewrite + decompose)
      -> router            (Send fan-out, no LLM)
           -> retrieve_worker  x N   (parallel hybrid search, no LLM)
      -> merge             (RRF + dedupe, no LLM)
      -> END

The LLM is injected at graph-build time from RAGService (singleton).
Nodes never call create_llm() inside a request — eliminating per-request
factory overhead and race conditions.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import Settings
from app.services.rag.graph.nodes.merge import merge_node
from app.services.rag.graph.nodes.query_transform import query_transform_node
from app.services.rag.graph.nodes.retrieve_worker import retrieve_worker_node
from app.services.rag.graph.state import RetrievalState

logger = logging.getLogger(__name__)


def build_retrieval_graph(settings: Settings, llm: Any = None):
    """
    Build and compile the retrieval graph.

    Args:
        settings: Application settings singleton.
        llm: Pre-created LLM singleton injected by RAGService.__init__.
             If None, query_transform falls back to create_llm() (legacy path).
    """

    async def _query_transform(state: RetrievalState) -> dict:
        return await query_transform_node(state, settings, llm=llm)

    async def _worker(payload: dict) -> dict:
        return await retrieve_worker_node(payload["sub_query"], settings)

    async def _merge(state: RetrievalState) -> dict:
        return await merge_node(state, settings)

    def _route_to_workers(state: RetrievalState) -> list[Send]:
        """Fan out one worker per sub-query (parallel)."""
        return [
            Send("retrieve_worker", {"sub_query": sq}) for sq in state.sub_queries
        ]

    builder = StateGraph(RetrievalState)
    builder.add_node("query_transform", _query_transform)
    builder.add_node("retrieve_worker", _worker)
    builder.add_node("merge", _merge)

    builder.add_edge(START, "query_transform")
    builder.add_conditional_edges(
        "query_transform", _route_to_workers, ["retrieve_worker"]
    )
    builder.add_edge("retrieve_worker", "merge")
    builder.add_edge("merge", END)

    compiled = builder.compile()
    logger.info("Retrieval graph compiled")
    return compiled


__all__ = ["build_retrieval_graph"]
