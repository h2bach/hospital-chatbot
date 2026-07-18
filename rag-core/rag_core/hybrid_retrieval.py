from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DenseHit:
    chunk_id: str
    score: float


class DenseShardIndex:
    """Read a versioned dense artifact and search normalized BGE-M3 vectors."""

    def __init__(self, root: Path):
        import numpy as np

        pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
        self.manifest = json.loads((root / pointer["manifest"]).read_text(encoding="utf-8"))
        if self.manifest.get("status") != "complete":
            raise ValueError("Dense index chưa hoàn tất")
        self.root = root / self.manifest["index_id"]
        self.ids: list[str] = []
        matrices = []
        for shard in self.manifest["shards"]:
            matrix = np.load(self.root / shard["embedding_file"], mmap_mode="r")
            ids = json.loads((self.root / shard["chunk_ids_file"]).read_text(encoding="utf-8"))
            expected_shape = (shard["count"], self.manifest["embedding_dimension"])
            if matrix.shape != expected_shape or len(ids) != shard["count"]:
                raise ValueError(f"Dense shard {shard['shard']} không khớp manifest")
            matrices.append(matrix)
            self.ids.extend(ids)
        if len(self.ids) != self.manifest["chunk_count"] or len(self.ids) != len(set(self.ids)):
            raise ValueError("Dense chunk IDs thiếu hoặc trùng")
        self.matrix = np.concatenate(matrices, axis=0).astype(np.float32, copy=False)

    def search_vectors(self, query_vectors, top_k: int = 10) -> list[list[DenseHit]]:
        import numpy as np

        vectors = np.asarray(query_vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.shape[1] != self.manifest["embedding_dimension"]:
            raise ValueError("Query embedding dimension không khớp dense index")
        limit = max(1, min(top_k, len(self.ids)))
        all_hits: list[list[DenseHit]] = []
        for vector in vectors:
            scores = self.matrix @ vector
            candidate_rows = np.argpartition(scores, -limit)[-limit:]
            ordered_rows = candidate_rows[np.argsort(scores[candidate_rows])[::-1]]
            all_hits.append([
                DenseHit(self.ids[int(row)], float(scores[int(row)]))
                for row in ordered_rows
            ])
        return all_hits


def reciprocal_rank_fusion(
    bm25_ids: list[str],
    dense_hits: list[DenseHit],
    *,
    top_k: int = 10,
    rank_constant: int = 60,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for rank, chunk_id in enumerate(bm25_ids, 1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rank_constant + rank)
    for rank, hit in enumerate(dense_hits, 1):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (rank_constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
