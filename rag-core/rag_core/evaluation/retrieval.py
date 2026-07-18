from __future__ import annotations

import math
from dataclasses import dataclass, field

from rag_core.retrieval import HybridRetriever, RetrievalConfig
from rag_core.schemas import GoldenSample


@dataclass(slots=True)
class EvaluationReport:
    configuration: str
    sample_count: int
    recall_at_k: dict[int, float]
    mrr: float
    ndcg_at_k: dict[int, float]
    document_hit_rate: float
    section_hit_rate: float
    failures: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration": self.configuration, "sample_count": self.sample_count,
            "recall_at_k": self.recall_at_k, "mrr": self.mrr, "ndcg_at_k": self.ndcg_at_k,
            "document_hit_rate": self.document_hit_rate, "section_hit_rate": self.section_hit_rate,
            "failures": self.failures,
        }


def evaluate_retriever(retriever: HybridRetriever, samples: list[GoldenSample], mode: str = "b4",
                       ks: tuple[int, ...] = (1, 3, 5, 10)) -> EvaluationReport:
    recalls = {k: 0.0 for k in ks}
    ndcgs = {k: 0.0 for k in ks}
    reciprocal_ranks: list[float] = []
    document_hits = section_hits = 0
    failures = []
    max_k = max(ks)
    for sample in samples:
        found = retriever.retrieve(sample.query, RetrievalConfig(mode=mode, final_k=max_k))
        # B4 adds parent/neighbor chunks for generation context. These are not retrieval
        # candidates and must not alter retrieval rank metrics.
        ranked = sorted((item for item in found if item.source != "context_expansion"), key=lambda item: item.rank)
        ids = [item.chunk.chunk_id for item in ranked]
        expected = set(sample.expected_chunk_ids)
        relevant_positions = [index for index, chunk_id in enumerate(ids, 1) if chunk_id in expected]
        reciprocal_ranks.append(1 / relevant_positions[0] if relevant_positions else 0.0)
        for k in ks:
            hit_count = len(expected & set(ids[:k]))
            recalls[k] += hit_count / max(1, len(expected))
            dcg = sum(1 / math.log2(position + 1) for position in relevant_positions if position <= k)
            ideal = sum(1 / math.log2(position + 1) for position in range(1, min(len(expected), k) + 1))
            ndcgs[k] += dcg / ideal if ideal else 0.0
        found_docs = {item.chunk.document_id for item in ranked}
        found_sections = {item.chunk.section_id for item in ranked}
        document_hits += int(bool(found_docs & set(sample.expected_document_ids)))
        section_hits += int(bool(found_sections & set(sample.expected_section_ids)))
        if not relevant_positions:
            failures.append({"query_id": sample.query_id, "query": sample.query, "retrieved_chunk_ids": ids})
    count = len(samples) or 1
    return EvaluationReport(mode, len(samples), {k: value / count for k, value in recalls.items()},
                            sum(reciprocal_ranks) / count, {k: value / count for k, value in ndcgs.items()},
                            document_hits / count, section_hits / count, failures)
