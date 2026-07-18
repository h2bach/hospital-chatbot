"""
merge node — combine worker results into the final context set (no LLM).

Steps:
    1. Collect ranked id-lists from every worker.
    2. Fuse across workers with RRF (a chunk retrieved for several sub-queries
       ranks higher).
    3. Deduplicate by chunk_id, keep richest text/metadata.
    4. Return top-K contexts with fused scores.

Citations are built by the backend from each item's metadata; this node only
guarantees the metadata is present and accurate.
"""

from __future__ import annotations

import logging
import time

from app.config import Settings
from app.services.rag.graph.hybrid_search import reciprocal_rank_fusion
from app.services.rag.graph.state import RetrievalState, RetrievedItem

logger = logging.getLogger(__name__)


async def merge_node(state: RetrievalState, settings: Settings) -> dict:
    """Fuse and deduplicate worker results into final contexts."""
    start = time.perf_counter()

    ranked_lists: list[list[str]] = []
    item_by_id: dict[str, RetrievedItem] = {}

    for worker in state.worker_results:
        ranked_lists.append([it.chunk_id for it in worker.items])
        for it in worker.items:
            # Keep the item with the longest text (richest) on collisions.
            existing = item_by_id.get(it.chunk_id)
            if existing is None or len(it.text) > len(existing.text):
                item_by_id[it.chunk_id] = it

    fused = reciprocal_rank_fusion(ranked_lists, k=settings.retrieval_rrf_k)

    top_ids = sorted(fused, key=lambda cid: fused[cid], reverse=True)
    top_ids = top_ids[: state.top_k or settings.retrieval_final_top_k]

    contexts: list[RetrievedItem] = []
    for cid in top_ids:
        base = item_by_id.get(cid)
        if base is None:
            continue
        contexts.append(
            RetrievedItem(
                chunk_id=cid,
                score=round(fused[cid], 6),
                text=base.text,
                metadata=base.metadata,
            )
        )

    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        "merge done",
        extra={
            "trace_id": state.trace_id,
            "workers": len(state.worker_results),
            "final_contexts": len(contexts),
            "latency_ms": round(elapsed, 1),
        },
    )

    return {
        "contexts": contexts,
        "timings_ms": {**state.timings_ms, "merge": round(elapsed, 1)},
    }


__all__ = ["merge_node"]
