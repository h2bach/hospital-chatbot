from __future__ import annotations

from abc import ABC, abstractmethod

from rag_core.indexing.bm25 import tokenize
from rag_core.schemas import RetrievedChunk


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[RetrievedChunk], top_k: int = 8) -> list[RetrievedChunk]: ...


class LexicalReranker(Reranker):
    def rerank(self, query: str, candidates: list[RetrievedChunk], top_k: int = 8) -> list[RetrievedChunk]:
        query_terms = set(tokenize(query))
        for item in candidates:
            terms = set(tokenize(item.chunk.retrieval_text))
            overlap = len(query_terms & terms) / max(1, len(query_terms | terms))
            item.rerank_score = 0.7 * item.score + 0.3 * overlap
        results = sorted(candidates, key=lambda item: (-(item.rerank_score or 0), item.chunk.chunk_id))[:top_k]
        for rank, item in enumerate(results, 1):
            item.rank = rank
            item.score = item.rerank_score or item.score
        return results


class SentenceTransformerReranker(Reranker):
    def __init__(self, model_name: str, device: str | None = None):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("Install heartcare-rag-core[models] to use a cross-encoder") from exc
        self.model = CrossEncoder(model_name, device=device)

    def rerank(self, query: str, candidates: list[RetrievedChunk], top_k: int = 8) -> list[RetrievedChunk]:
        scores = self.model.predict([(query, item.chunk.retrieval_text) for item in candidates])
        for item, score in zip(candidates, scores):
            item.rerank_score = float(score)
        results = sorted(candidates, key=lambda item: -(item.rerank_score or 0))[:top_k]
        for rank, item in enumerate(results, 1):
            item.rank, item.score = rank, item.rerank_score or item.score
        return results

