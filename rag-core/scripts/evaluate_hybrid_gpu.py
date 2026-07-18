from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from rag_core.app import RAGApplication
from rag_core.hybrid_retrieval import DenseShardIndex, reciprocal_rank_fusion


def metrics(rankings: list[list[str]], expected: list[set[str]]) -> dict:
    recall = {1: 0, 3: 0, 5: 0}
    reciprocal_ranks = []
    for ranked, wanted in zip(rankings, expected, strict=True):
        for cutoff in recall:
            recall[cutoff] += bool(wanted.intersection(ranked[:cutoff]))
        rank = next((index for index, chunk_id in enumerate(ranked[:5], 1) if chunk_id in wanted), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    count = max(1, len(expected))
    return {
        "recall_at_1": recall[1] / count,
        "recall_at_3": recall[3] / count,
        "recall_at_5": recall[5] / count,
        "mrr_at_5": statistics.fmean(reciprocal_ranks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate BM25, BGE-M3 and RRF hybrid retrieval")
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--dense-index", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    started = time.perf_counter()
    app = RAGApplication(args.chunks)
    dense = DenseShardIndex(args.dense_index)
    samples = [
        json.loads(line) for line in args.golden.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_source_id = {
        str((chunk.metadata or {}).get("source_chunk_id")): chunk.chunk_id
        for chunk in app.chunks
        if (chunk.metadata or {}).get("source_chunk_id")
    }
    expected = []
    for sample in samples:
        ids = set(sample.get("expected_chunk_ids", []))
        ids.update(by_source_id[source_id] for source_id in sample.get("expected_source_chunk_ids", []) if source_id in by_source_id)
        if not ids:
            raise ValueError(f"Golden sample không resolve được evidence: {sample['id']}")
        expected.append(ids)

    model = SentenceTransformer(
        args.model,
        device=args.device,
        local_files_only=Path(args.model).exists(),
    )
    model.max_seq_length = int(dense.manifest["max_sequence_length"])
    queries = [sample["query"] for sample in samples]
    query_vectors = model.encode(
        queries,
        batch_size=min(64, len(queries)),
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
        device=args.device,
    )
    dense_hits = dense.search_vectors(query_vectors, top_k=50)

    bm25_rankings = []
    dense_rankings = []
    hybrid_rankings = []
    failures = []
    for sample, hits, wanted in zip(samples, dense_hits, expected, strict=True):
        bm25_ids = [item.chunk.chunk_id for item in app.search(sample["query"], 10)]
        dense_ids = [item.chunk_id for item in hits]
        hybrid_ids = [chunk_id for chunk_id, _ in reciprocal_rank_fusion(bm25_ids, hits, top_k=10)]
        bm25_rankings.append(bm25_ids)
        dense_rankings.append(dense_ids)
        hybrid_rankings.append(hybrid_ids)
        if not wanted.intersection(hybrid_ids[:5]):
            failures.append({
                "id": sample["id"],
                "expected": sorted(wanted),
                "bm25_top5": bm25_ids[:5],
                "dense_top5": dense_ids[:5],
                "hybrid_top5": hybrid_ids[:5],
            })

    report = {
        "schema_version": "heartcare.rag.hybrid-evaluation.v1",
        "status": "pass" if not failures else "fail",
        "sample_count": len(samples),
        "chunks_sha256": dense.manifest["chunks_sha256"],
        "dense_index_id": dense.manifest["index_id"],
        "model": args.model,
        "device": args.device,
        "bm25": metrics(bm25_rankings, expected),
        "dense": metrics(dense_rankings, expected),
        "hybrid_rrf": metrics(hybrid_rankings, expected),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "failures": failures,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
