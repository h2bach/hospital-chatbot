"""
retrieve_worker node — one hybrid-search worker per sub-query (no LLM).

The router fans out via LangGraph's Send API, invoking this node once per
sub-query. Each worker runs BM25 + vector search + RRF and appends a
WorkerResult to state.worker_results (merged via the Annotated list reducer).

Search is synchronous/CPU+IO bound, so it runs in a thread to avoid blocking
the event loop and to allow true parallelism across workers.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import Settings
from app.services.ingest_data.stores import get_stores
from app.services.rag.graph.hybrid_search import hybrid_search
from app.services.rag.graph.state import WorkerResult

logger = logging.getLogger(__name__)


async def retrieve_worker_node(sub_query: str, settings: Settings) -> dict:
    """Run hybrid search for a single sub-query."""
    start = time.perf_counter()
    stores = get_stores(settings)

    items = await asyncio.to_thread(
        hybrid_search,
        sub_query,
        stores.vector_store,
        stores.bm25_store,
        stores.chunk_store,
        settings.retrieval_bm25_top_k,
        settings.retrieval_vector_top_k,
        settings.retrieval_rrf_k,
        settings.retrieval_worker_top_k,
    )

    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        "retrieve_worker done",
        extra={
            "sub_query": sub_query[:80],
            "hits": len(items),
            "latency_ms": round(elapsed, 1),
        },
    )

    return {
        "worker_results": [
            WorkerResult(
                sub_query=sub_query,
                items=items,
                timings_ms={"hybrid_search": round(elapsed, 1)},
            )
        ]
    }


__all__ = ["retrieve_worker_node"]
