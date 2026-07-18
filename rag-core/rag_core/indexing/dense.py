from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from rag_core.indexing.bm25 import _matches, tokenize
from rag_core.schemas import Chunk, RetrievedChunk


class EmbeddingProvider(ABC):
    model_name = "unknown"

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]: ...


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic CPU baseline. Replace with a Vietnamese embedding provider for production."""
    model_name = "hashing-baseline-v1"

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        terms = tokenize(text)
        features = terms + [f"{a}_{b}" for a, b in zip(terms, terms[1:])]
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4]) % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._embed(query)


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str, device: str | None = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("Install heartcare-rag-core[models] to use sentence-transformers") from exc
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, query: str) -> list[float]:
        return self.model.encode([query], normalize_embeddings=True)[0].tolist()


class DenseIndex:
    def __init__(self, provider: EmbeddingProvider | None = None):
        self.provider = provider or HashingEmbeddingProvider()
        self.chunks: list[Chunk] = []
        self.vectors: list[list[float]] = []

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = [chunk for chunk in chunks if chunk.is_active]
        self.vectors = self.provider.embed_documents([chunk.retrieval_text for chunk in self.chunks])

    def search(self, query: str, top_k: int = 30, filters: dict[str, object] | None = None) -> list[RetrievedChunk]:
        query_vector = self.provider.embed_query(query)
        scored = []
        for chunk, vector in zip(self.chunks, self.vectors):
            if _matches(chunk, filters):
                score = sum(left * right for left, right in zip(query_vector, vector))
                scored.append(RetrievedChunk(chunk, score, "dense", dense_score=score))
        scored.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        for rank, result in enumerate(scored[:top_k], 1):
            result.rank = rank
        return scored[:top_k]

