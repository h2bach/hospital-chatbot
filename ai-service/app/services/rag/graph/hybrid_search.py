"""
Hybrid search — BM25 + vector search fused with Reciprocal Rank Fusion (RRF).

Pure algorithm, no LLM. RRF is rank-based so it needs no score normalization
between the two very different scoring scales (BM25 term weights vs cosine
similarity):

    rrf_score(d) = sum over lists L of 1 / (k + rank_L(d))

Chunk metadata is enriched from the SQLite chunk store so downstream citations
carry the full heading_path and line ranges.
"""

from __future__ import annotations

from app.services.ingest_data.ingest.base import (
    BaseBM25Store,
    BaseChunkStore,
    BaseVectorStore,
)
from app.services.rag.graph.state import RetrievedItem


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> dict[str, float]:
    """
    Fuse multiple ranked id-lists into a combined score map.

    Args:
        ranked_lists: each inner list is chunk_ids ordered best-first.
        k: RRF constant (dampens the contribution of lower ranks).

    Returns:
        {chunk_id: fused_score}
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def hybrid_search(
    query: str,
    vector_store: BaseVectorStore,
    bm25_store: BaseBM25Store,
    chunk_store: BaseChunkStore,
    bm25_top_k: int = 30,
    vector_top_k: int = 30,
    rrf_k: int = 60,
    final_top_k: int = 10,
) -> list[RetrievedItem]:
    """
    Run BM25 + vector search for one query and fuse with RRF.

    Returns up to final_top_k items enriched with full chunk metadata.
    """
    vector_hits = vector_store.search(query, top_k=vector_top_k)
    bm25_hits = bm25_store.search(query, top_k=bm25_top_k)

    vector_ids = [h.chunk_id for h in vector_hits]
    bm25_ids = [h.chunk_id for h in bm25_hits]

    fused = reciprocal_rank_fusion([vector_ids, bm25_ids], k=rrf_k)
    if not fused:
        return []

    # Text/metadata lookup: prefer the vector/bm25 hit payloads, fall back to store.
    text_by_id: dict[str, str] = {}
    meta_by_id: dict[str, dict] = {}
    for h in vector_hits + bm25_hits:
        text_by_id.setdefault(h.chunk_id, h.text)
        meta_by_id.setdefault(h.chunk_id, h.metadata)

    top_ids = sorted(fused, key=lambda cid: fused[cid], reverse=True)[:final_top_k]

    # Enrich with full structured metadata from the chunk store.
    stored = chunk_store.get_many(top_ids)

    items: list[RetrievedItem] = []
    for cid in top_ids:
        chunk = stored.get(cid)
        if chunk is not None:
            metadata = {
                "document_id": chunk.document_id,
                "document_name": chunk.document_name,
                "source_file": chunk.source_file,
                "heading_path": chunk.heading_path,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "version": chunk.version,
            }
            text = chunk.text
        else:
            metadata = dict(meta_by_id.get(cid, {}))
            text = text_by_id.get(cid, "")

        items.append(
            RetrievedItem(
                chunk_id=cid,
                score=round(fused[cid], 6),
                text=text,
                metadata=metadata,
            )
        )
    return items


__all__ = ["hybrid_search", "reciprocal_rank_fusion"]
