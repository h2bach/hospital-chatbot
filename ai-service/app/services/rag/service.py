"""
RAGService — retrieval-only RAG service (LangGraph).

Pipeline (see graph/retrieval_graph.py):
    query_transform (LLM once) -> parallel hybrid-search workers -> merge

invoke() returns retrieved contexts + citations + per-stage timings. This
service does NOT generate answers; the backend decides whether to call an LLM
for synthesis.

The LLM used by QueryTransform is created ONCE in __init__ and kept as a
singleton on self.llm — never created inside a request hot-path.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, AsyncIterator

from app.config import Settings
from app.services.base import AgentService
from app.services.rag.graph.retrieval_graph import build_retrieval_graph
from app.services.rag.graph.state import RetrievalState
from app.services.rag.llm_factory import create_query_transform_llm

logger = logging.getLogger(__name__)


def build_citation(metadata: dict[str, Any]) -> dict[str, Any]:
    """Build a structured citation from chunk metadata (no LLM)."""
    heading_path = metadata.get("heading_path") or []
    if isinstance(heading_path, str):
        heading_path = [p.strip() for p in heading_path.split(">") if p.strip()]
    return {
        "document": metadata.get("document_name") or metadata.get("document_id"),
        "source_file": metadata.get("source_file"),
        "heading_path": heading_path,
        "line_start": metadata.get("line_start"),
        "line_end": metadata.get("line_end"),
        "page_start": metadata.get("page_start"),
        "page_end": metadata.get("page_end"),
        "version": metadata.get("version"),
    }


class RAGService(AgentService):
    """Retrieval-only RAG service."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

        # B3: LLM singleton — created ONCE here, reused by every request.
        # Never created inside a node or request handler.
        self.llm = create_query_transform_llm(settings)

        # Graph compiled once at construction; passed self.llm so nodes never
        # call create_llm() at request time.
        self.graph = build_retrieval_graph(settings, llm=self.llm)
        logger.info("RAGService initialized (retrieval-only, LLM pre-loaded)")

    async def warmup(self) -> None:
        """
        Warm every hot path before the server accepts traffic:

          1. Direct LLM inference — forces qwen2.5 to load into Ollama VRAM
             (keep_alive starts counting). MUST bypass the heuristic-skip in
             query_transform, otherwise a short warmup query would skip the LLM
             and leave the model cold for the first real complex query.
          2. Full graph ainvoke with a DECOMPOSABLE query — JIT-warms LangGraph
             routing, the Send fan-out, and the search/embedding path.
        """
        # 1. Force real LLM load (cannot be skipped by heuristics).
        try:
            t = time.perf_counter()
            await self.llm.ainvoke("ping")
            logger.info(
                "LLM warmup (model loaded) in %.0fms",
                (time.perf_counter() - t) * 1000,
            )
        except Exception as exc:
            logger.warning("LLM warmup failed (non-fatal): %s", exc)

        # 2. Full pipeline warm with a query that triggers decomposition
        #    (>8 words + conjunction) so both LLM and search paths are exercised.
        try:
            await self.graph.ainvoke(
                RetrievalState(
                    query="khởi động hệ thống và làm nóng đường dẫn tìm kiếm truy vấn",
                    trace_id="warmup",
                    top_k=1,
                )
            )
            logger.info("RAGService warmup complete")
        except Exception as exc:
            logger.warning("RAGService warmup failed (non-fatal): %s", exc)

    async def retrieve(
        self, query: str, top_k: int | None = None, **kwargs: Any
    ) -> dict:
        """
        Run the retrieval pipeline and return contexts + citations + timings.
        """
        start = time.perf_counter()
        trace_id = kwargs.get("trace_id") or str(uuid.uuid4())

        initial = RetrievalState(
            query=query,
            trace_id=trace_id,
            top_k=top_k or self.settings.retrieval_final_top_k,
        )

        result = await self.graph.ainvoke(initial)

        contexts = result["contexts"] if isinstance(result, dict) else result.contexts
        sub_queries = (
            result["sub_queries"] if isinstance(result, dict) else result.sub_queries
        )
        timings = result["timings_ms"] if isinstance(result, dict) else result.timings_ms

        latency_ms = (time.perf_counter() - start) * 1000
        timings = {**timings, "total": round(latency_ms, 1)}

        contexts_out = []
        citations_out = []
        for item in contexts:
            meta = item.metadata if hasattr(item, "metadata") else item["metadata"]
            text = item.text if hasattr(item, "text") else item["text"]
            score = item.score if hasattr(item, "score") else item["score"]
            chunk_id = item.chunk_id if hasattr(item, "chunk_id") else item["chunk_id"]
            contexts_out.append(
                {"chunk_id": chunk_id, "text": text, "score": score, "metadata": meta}
            )
            citations_out.append(
                {"chunk_id": chunk_id, "score": score, **build_citation(meta)}
            )

        logger.info(
            "retrieve completed",
            extra={
                "trace_id": trace_id,
                "results": len(contexts_out),
                "latency_ms": f"{latency_ms:.1f}",
            },
        )

        return {
            "query": query,
            "sub_queries": sub_queries,
            "contexts": contexts_out,
            "citations": citations_out,
            "total_results": len(contexts_out),
            "timings_ms": timings,
            "trace_id": trace_id,
            "latency_ms": round(latency_ms, 1),
        }

    async def invoke(self, message: str, **kwargs: Any) -> dict:
        return await self.retrieve(message, **kwargs)

    async def stream(self, message: str, **kwargs: Any) -> AsyncIterator[str]:
        result = await self.retrieve(message, **kwargs)
        for ctx in result["contexts"]:
            yield ctx["text"] + "\n\n"


__all__ = ["RAGService", "build_citation"]

