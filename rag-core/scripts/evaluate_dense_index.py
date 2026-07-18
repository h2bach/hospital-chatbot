from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate BGE-M3 Recall@k and MRR")
    parser.add_argument("--dense-root", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--model")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    import numpy as np
    from sentence_transformers import SentenceTransformer

    current = json.loads((args.dense_root / "current.json").read_text(encoding="utf-8"))
    artifact_dir = args.dense_root / current["index_id"]
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    chunk_ids: list[str] = []
    matrices = []
    for shard in manifest["shards"]:
        chunk_ids.extend(json.loads((artifact_dir / shard["chunk_ids_file"]).read_text(encoding="utf-8")))
        matrices.append(np.load(artifact_dir / shard["embedding_file"], allow_pickle=False))
    matrix = np.concatenate(matrices, axis=0)

    source_ids: dict[str, str] = {}
    titles: dict[str, str] = {}
    for chunk in jsonl(args.chunks):
        facts = chunk.get("metadata") or {}
        source_ids[chunk["chunk_id"]] = str(facts.get("source_chunk_id", ""))
        titles[chunk["chunk_id"]] = str(facts.get("title") or facts.get("service_name") or "")

    golden = jsonl(args.golden)
    model_path = args.model or manifest["model_source"]
    model = SentenceTransformer(model_path, device=args.device, local_files_only=Path(model_path).exists())
    model.max_seq_length = int(manifest["max_sequence_length"])
    query_vectors = model.encode(
        [item["query"] for item in golden],
        batch_size=min(32, len(golden)),
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        device=args.device,
    )

    results = []
    reciprocal_ranks = []
    hit_count = 0
    for item, vector in zip(golden, query_vectors):
        scores = matrix @ vector
        top_indices = np.argpartition(-scores, args.top_k - 1)[:args.top_k]
        top_indices = top_indices[np.argsort(-scores[top_indices])]
        expected = set(item["expected_source_chunk_ids"])
        expected_rank = None
        rows = []
        for rank, index in enumerate(top_indices, 1):
            chunk_id = chunk_ids[int(index)]
            source_id = source_ids.get(chunk_id, "")
            if expected_rank is None and source_id in expected:
                expected_rank = rank
            rows.append({
                "rank": rank,
                "score": round(float(scores[index]), 6),
                "chunk_id": chunk_id,
                "source_chunk_id": source_id,
                "title": titles.get(chunk_id, ""),
            })
        if expected_rank is not None:
            hit_count += 1
            reciprocal_ranks.append(1.0 / expected_rank)
        else:
            reciprocal_ranks.append(0.0)
        results.append({
            "query": item["query"],
            "expected_source_chunk_ids": sorted(expected),
            "expected_rank": expected_rank,
            "top_k": rows,
        })

    report = {
        "schema_version": "heartcare.rag.dense-evaluation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index_id": manifest["index_id"],
        "model": "BAAI/bge-m3",
        "device": args.device,
        "cuda_device": manifest.get("cuda_device"),
        "corpus_chunks": len(chunk_ids),
        "query_count": len(golden),
        "top_k": args.top_k,
        "recall_at_k": round(hit_count / len(golden), 6),
        "mrr_at_k": round(sum(reciprocal_ranks) / len(golden), 6),
        "results": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
