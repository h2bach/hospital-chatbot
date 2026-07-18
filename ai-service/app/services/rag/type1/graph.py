"""
Type1 subgraph — Vector/document hybrid search RAG.

This subgraph:
1. Receives a Type1State (task_id, query, parameters) from Router via Send().
2. Runs hybrid search (BM25 + Vector) with RRF fusion.
3. Emits a BranchResult into MainState.branch_results via the `emit_result` node.

Key design:
  The final node `emit_result` returns {"branch_results": [BranchResult(...)]}
  which maps directly to MainState.branch_results (Annotated[list, add] reducer).
  This avoids field-name collisions when multiple subgraphs run in parallel.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated
from operator import add
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.services.rag.graph.schemas import BranchResult
from app.services.rag.type1.state import Type1State


class Type1SubgraphOutput(TypedDict):
    """Output schema for the Type1 subgraph — only branch_results is exposed."""
    branch_results: Annotated[list[BranchResult], add]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lazy store accessors
# ─────────────────────────────────────────────────────────────────────────────

def _get_stores(settings: Settings):
    from app.services.ingest_data.ingest.vector_store import ChromaVectorStore
    from app.services.ingest_data.ingest.bm25_store import RankBM25Store
    from app.services.ingest_data.ingest.chunk_store import ChunkStore

    vector_store = ChromaVectorStore(
        persist_directory=settings.chroma_persist_dir,
        collection_name=settings.chroma_collection_name,
        embedding_api_key=settings.embedding_api_key,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
    )
    bm25_store = RankBM25Store(index_path=settings.bm25_index_path)
    bm25_store.load()
    chunk_store = ChunkStore(db_path=settings.chunk_db_path)
    return vector_store, bm25_store, chunk_store


# ─────────────────────────────────────────────────────────────────────────────
# RRF fusion
# ─────────────────────────────────────────────────────────────────────────────

def _rrf_fusion(vector_results: list, bm25_results: list, top_k: int, k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for rank, r in enumerate(vector_results, 1):
        scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + 1.0 / (k + rank)
    for rank, r in enumerate(bm25_results, 1):
        scores[r.chunk_id] = scores.get(r.chunk_id, 0.0) + 1.0 / (k + rank)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [cid for cid, _ in ranked[:top_k]]


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: retrieve
# ─────────────────────────────────────────────────────────────────────────────

async def _retrieve_node(state: Type1State, settings: Settings) -> dict:
    """Perform hybrid search and write results into Type1State fields."""
    start = time.perf_counter()
    task_id = state.task_id
    query = state.query
    top_k: int = state.parameters.get("top_k", 5)

    logger.info(
        "Type1 retrieve: started",
        extra={"task_id": task_id, "query": query[:80], "top_k": top_k},
    )

    try:
        vector_store, bm25_store, chunk_store = await asyncio.to_thread(
            _get_stores, settings
        )
        vector_results, bm25_results = await asyncio.gather(
            asyncio.to_thread(vector_store.search, query, top_k * 2),
            asyncio.to_thread(bm25_store.search, query, top_k * 2),
        )

        fused_ids = _rrf_fusion(vector_results, bm25_results, top_k=top_k)

        if not fused_ids:
            logger.warning("Type1 retrieve: no results", extra={"task_id": task_id})
            return {
                "status": "success",
                "content": "No relevant documents found.",
                "raw_results": [],
                "latency": time.perf_counter() - start,
            }

        chunk_records = await asyncio.to_thread(chunk_store.get_chunks, fused_ids)

        passages: list[str] = []
        source_metadata: list[dict] = []
        for idx, chunk in enumerate(chunk_records, 1):
            heading = " > ".join(chunk.heading_path) if chunk.heading_path else ""
            pages = (
                f"p.{chunk.page_start}"
                if chunk.page_start == chunk.page_end
                else f"p.{chunk.page_start}-{chunk.page_end}"
            )
            passages.append(f"[{idx}] ({pages} | {heading})\n{chunk.text}")
            source_metadata.append({
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "section": chunk.section,
                "heading_path": chunk.heading_path,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
            })

        latency = time.perf_counter() - start
        logger.info(
            "Type1 retrieve: done",
            extra={"task_id": task_id, "chunks": len(chunk_records), "latency_s": f"{latency:.2f}"},
        )
        return {
            "status": "success",
            "content": "\n\n---\n\n".join(passages),
            "raw_results": source_metadata,
            "latency": latency,
        }

    except Exception as exc:
        latency = time.perf_counter() - start
        logger.error(
            "Type1 retrieve: error",
            extra={"task_id": task_id, "error": str(exc)},
            exc_info=True,
        )
        return {
            "status": "failed",
            "error": str(exc),
            "content": "",
            "raw_results": [],
            "latency": latency,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: emit_result
# Converts Type1State → BranchResult and writes to MainState.branch_results
# ─────────────────────────────────────────────────────────────────────────────

async def _emit_result_node(state: Type1State) -> dict:
    """
    Final node: package Type1State into a BranchResult.

    Returns {"branch_results": [BranchResult(...)]} which LangGraph
    writes to MainState.branch_results via the `add` reducer.
    No field-name collisions with MainState possible.
    """
    branch_status = "success" if state.status == "success" else "failed"

    result = BranchResult(
        task_id=state.task_id,
        data_type="type1",
        status=branch_status,
        content=state.content,
        source_metadata=state.raw_results,
        latency=state.latency,
        token_usage=state.token_usage,
    )

    logger.info(
        "Type1 emit_result",
        extra={
            "task_id": state.task_id,
            "status": branch_status,
            "content_len": len(state.content),
        },
    )
    return {"branch_results": [result]}


# ─────────────────────────────────────────────────────────────────────────────
# Subgraph builder
# ─────────────────────────────────────────────────────────────────────────────

def build_type1_subgraph(settings: Settings):
    """
    Build and compile the Type1 subgraph.

    Graph: START → retrieve → emit_result → END

    The `emit_result` node outputs {"branch_results": [...]} which goes
    directly into MainState.branch_results through the `add` reducer —
    no field conflicts when multiple subgraphs run in parallel.
    """

    async def retrieve_wrapper(state: Type1State) -> dict:
        return await _retrieve_node(state, settings)

    builder = StateGraph(Type1State, output=Type1SubgraphOutput)
    builder.add_node("retrieve", retrieve_wrapper)
    builder.add_node("emit_result", _emit_result_node)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "emit_result")
    builder.add_edge("emit_result", END)

    compiled = builder.compile()
    logger.info("Type1 subgraph compiled")
    return compiled
