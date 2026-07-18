from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from rag_core.schemas import Chunk, RetrievedChunk


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text.lower())
    return re.findall(r"[\wÀ-ỹ]+", normalized, re.UNICODE)


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.chunks: dict[str, Chunk] = {}
        self.term_frequencies: dict[str, Counter[str]] = {}
        self.document_frequencies: Counter[str] = Counter()
        self.average_length = 0.0

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = {chunk.chunk_id: chunk for chunk in chunks if chunk.is_active}
        self.term_frequencies = {}
        self.document_frequencies = Counter()
        lengths = []
        for chunk in self.chunks.values():
            terms = tokenize(chunk.retrieval_text)
            tf = Counter(terms)
            self.term_frequencies[chunk.chunk_id] = tf
            self.document_frequencies.update(tf.keys())
            lengths.append(len(terms))
        self.average_length = sum(lengths) / len(lengths) if lengths else 0.0

    def search(self, query: str, top_k: int = 30, filters: dict[str, object] | None = None) -> list[RetrievedChunk]:
        terms, count = tokenize(query), len(self.chunks)
        results = []
        for chunk_id, chunk in self.chunks.items():
            if not _matches(chunk, filters):
                continue
            tf = self.term_frequencies[chunk_id]
            length = sum(tf.values())
            score = 0.0
            for term in terms:
                frequency = tf[term]
                if not frequency:
                    continue
                df = self.document_frequencies[term]
                idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / (self.average_length or 1))
                score += idf * frequency * (self.k1 + 1) / denominator
            if score:
                results.append(RetrievedChunk(chunk, score, "bm25", bm25_score=score))
        results.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        for rank, result in enumerate(results[:top_k], 1):
            result.rank = rank
        return results[:top_k]


def _matches(chunk: Chunk, filters: dict[str, object] | None) -> bool:
    if not filters:
        return True
    return all(getattr(chunk, key, None) == value for key, value in filters.items())

