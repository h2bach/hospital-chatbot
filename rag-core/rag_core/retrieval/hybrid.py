from __future__ import annotations

from dataclasses import dataclass

from rag_core.indexing import BM25Index, DenseIndex
from rag_core.reranking import LexicalReranker, Reranker
from rag_core.schemas import Chunk, RetrievedChunk


@dataclass(slots=True)
class RetrievalConfig:
    mode: str = "b4"
    candidate_k: int = 30
    final_k: int = 8
    rrf_k: int = 60
    expand_neighbors: int = 1
    max_context_tokens: int = 3000


def reciprocal_rank_fusion(rankings: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]:
    fused: dict[str, RetrievedChunk] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            key = item.chunk.chunk_id
            if key not in fused:
                fused[key] = RetrievedChunk(item.chunk, 0.0, "hybrid", bm25_score=item.bm25_score,
                                              dense_score=item.dense_score)
            target = fused[key]
            target.score += 1 / (k + rank)
            target.bm25_score = target.bm25_score if target.bm25_score is not None else item.bm25_score
            target.dense_score = target.dense_score if target.dense_score is not None else item.dense_score
    results = sorted(fused.values(), key=lambda item: (-item.score, item.chunk.chunk_id))
    for rank, item in enumerate(results, 1):
        item.rank = rank
    return results


class HybridRetriever:
    def __init__(self, chunks: list[Chunk], reranker: Reranker | None = None):
        self.chunks = chunks
        self.by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self.by_section: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            self.by_section.setdefault(chunk.section_id, []).append(chunk)
        self.bm25 = BM25Index()
        self.dense = DenseIndex()
        self.bm25.build(chunks)
        self.dense.build(chunks)
        self.reranker = reranker or LexicalReranker()

    def retrieve(self, query: str, config: RetrievalConfig | None = None,
                 filters: dict[str, object] | None = None) -> list[RetrievedChunk]:
        cfg = config or RetrievalConfig()
        bm25 = self.bm25.search(query, cfg.candidate_k, filters)
        dense = self.dense.search(query, cfg.candidate_k, filters)
        if cfg.mode == "b0":
            return bm25[:cfg.final_k]
        if cfg.mode == "b1":
            return dense[:cfg.final_k]
        candidates = reciprocal_rank_fusion([bm25, dense], cfg.rrf_k)[:cfg.candidate_k]
        if cfg.mode == "b2":
            return candidates[:cfg.final_k]
        candidates = self.reranker.rerank(query, candidates, cfg.final_k)
        if cfg.mode == "b3":
            return candidates
        return self._expand(candidates, cfg)

    def _expand(self, selected: list[RetrievedChunk], cfg: RetrievalConfig) -> list[RetrievedChunk]:
        expanded: dict[str, RetrievedChunk] = {item.chunk.chunk_id: item for item in selected}
        for item in selected:
            siblings = self.by_section.get(item.chunk.section_id, [])
            position = next((i for i, chunk in enumerate(siblings) if chunk.chunk_id == item.chunk.chunk_id), -1)
            if position >= 0:
                start, end = max(0, position - cfg.expand_neighbors), min(len(siblings), position + cfg.expand_neighbors + 1)
                for sibling in siblings[start:end]:
                    expanded.setdefault(sibling.chunk_id, RetrievedChunk(sibling, item.score * 0.8, "context_expansion"))
        ordered = sorted(expanded.values(), key=lambda item: (item.chunk.document_id, item.chunk.chunk_index))
        budgeted, tokens = [], 0
        for item in ordered:
            if tokens + item.chunk.token_count > cfg.max_context_tokens:
                continue
            budgeted.append(item)
            tokens += item.chunk.token_count
        return budgeted

