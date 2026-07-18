from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_MODEL = "BAAI/bge-m3"
DEFAULT_MAX_SEQUENCE_LENGTH = 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_active_chunks(path: Path) -> list[dict]:
    chunks: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not item.get("is_active", True):
                continue
            if not item.get("chunk_id") or not item.get("retrieval_text"):
                raise ValueError(f"Chunk không hợp lệ tại {path}:{line_number}")
            chunks.append(item)
    if not chunks:
        raise ValueError(f"Không có active chunk trong {path}")
    ids = [str(item["chunk_id"]) for item in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Chunk IDs không duy nhất")
    return chunks


def batches(values: list[dict], size: int) -> Iterable[tuple[int, list[dict]]]:
    for start in range(0, len(values), size):
        yield start, values[start:start + size]


def encode_with_oom_backoff(model, texts: list[str], batch_size: int, device: str):
    import torch

    current_batch_size = max(1, min(batch_size, len(texts)))
    while True:
        try:
            embeddings = model.encode(
                texts,
                batch_size=current_batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
                device=device,
            )
            return embeddings, current_batch_size
        except torch.OutOfMemoryError:
            if current_batch_size == 1:
                raise
            current_batch_size = max(1, current_batch_size // 2)
            torch.cuda.empty_cache()


def resolve_model_source(model_name_or_path: str) -> str:
    candidate = Path(model_name_or_path)
    return str(candidate.resolve()) if candidate.exists() else model_name_or_path


def build_dense_index(
    *,
    chunks_path: Path,
    output_root: Path,
    model_name_or_path: str = DEFAULT_MODEL,
    device: str = "cuda",
    batch_size: int = 64,
    shard_size: int = 2048,
    max_sequence_length: int = DEFAULT_MAX_SEQUENCE_LENGTH,
    force: bool = False,
) -> dict:
    if batch_size < 1 or shard_size < 1:
        raise ValueError("batch_size và shard_size phải lớn hơn 0")

    # Heavy ML imports stay optional for the normal BM25 web process.
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    if device.startswith("cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA được yêu cầu nhưng PyTorch không truy cập được GPU")
        torch.cuda.init()

    chunks_hash = sha256_file(chunks_path)
    chunks = load_active_chunks(chunks_path)
    model_source = resolve_model_source(model_name_or_path)
    index_id = f"bge-m3-{chunks_hash[:12]}"
    output_dir = output_root / index_id
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file() and not force:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("status") == "complete" and existing.get("chunks_sha256") == chunks_hash:
            return {**existing, "reused": True, "artifact_dir": str(output_dir)}

    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = SentenceTransformer(
        model_source,
        device=device,
        local_files_only=Path(model_source).exists(),
    )
    model.max_seq_length = max_sequence_length

    shard_records: list[dict] = []
    embedding_dimension: int | None = None
    effective_batch_sizes: list[int] = []
    for shard_index, (start, shard_chunks) in enumerate(batches(chunks, shard_size)):
        texts = [str(item["retrieval_text"]) for item in shard_chunks]
        encoded, effective_batch_size = encode_with_oom_backoff(model, texts, batch_size, device)
        encoded = np.asarray(encoded, dtype=np.float32)
        if encoded.ndim != 2 or encoded.shape[0] != len(shard_chunks):
            raise RuntimeError(f"Embedding shape không hợp lệ: {encoded.shape}")
        if not np.isfinite(encoded).all():
            raise RuntimeError(f"Embedding chứa NaN/Inf tại shard {shard_index}")
        norms = np.linalg.norm(encoded, axis=1)
        if not np.allclose(norms, 1.0, atol=2e-3):
            raise RuntimeError(f"Embedding chưa được chuẩn hóa tại shard {shard_index}")
        embedding_dimension = embedding_dimension or int(encoded.shape[1])
        if encoded.shape[1] != embedding_dimension:
            raise RuntimeError("Embedding dimension thay đổi giữa các shard")

        embedding_name = f"embeddings-{shard_index:05d}.npy"
        ids_name = f"chunk-ids-{shard_index:05d}.json"
        np.save(output_dir / embedding_name, encoded.astype(np.float16), allow_pickle=False)
        (output_dir / ids_name).write_text(
            json.dumps([item["chunk_id"] for item in shard_chunks], ensure_ascii=False),
            encoding="utf-8",
        )
        shard_records.append({
            "shard": shard_index,
            "start": start,
            "count": len(shard_chunks),
            "embedding_file": embedding_name,
            "chunk_ids_file": ids_name,
        })
        effective_batch_sizes.append(effective_batch_size)

    elapsed = time.perf_counter() - started
    cuda_device = torch.cuda.get_device_name(torch.cuda.current_device()) if device.startswith("cuda") else None
    manifest = {
        "schema_version": "heartcare.rag.dense-index.v1",
        "status": "complete",
        "index_id": index_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "chunks_file": str(chunks_path.resolve()),
        "chunks_sha256": chunks_hash,
        "chunk_count": len(chunks),
        "model": model_name_or_path,
        "model_source": model_source,
        "embedding_dimension": embedding_dimension,
        "embedding_dtype": "float16",
        "normalized": True,
        "similarity": "cosine_via_inner_product",
        "device": device,
        "cuda_device": cuda_device,
        "requested_batch_size": batch_size,
        "effective_batch_size_min": min(effective_batch_sizes),
        "effective_batch_size_max": max(effective_batch_sizes),
        "shard_size": shard_size,
        "shard_count": len(shard_records),
        "max_sequence_length": max_sequence_length,
        "elapsed_seconds": round(elapsed, 3),
        "chunks_per_second": round(len(chunks) / max(elapsed, 1e-9), 3),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "sentence_transformers": __import__("sentence_transformers").__version__,
        "hostname": platform.node(),
        "shards": shard_records,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "current.json").write_text(
        json.dumps({
            "index_id": index_id,
            "manifest": f"{index_id}/manifest.json",
            "chunks_sha256": chunks_hash,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {**manifest, "reused": False, "artifact_dir": str(output_dir)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a sharded GPU BGE-M3 dense index")
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_MODEL))
    parser.add_argument("--device", default=os.getenv("RAG_EMBEDDING_DEVICE", "cuda"))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--shard-size", type=int, default=2048)
    parser.add_argument("--max-sequence-length", type=int, default=DEFAULT_MAX_SEQUENCE_LENGTH)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_dense_index(
        chunks_path=args.chunks,
        output_root=args.output_dir,
        model_name_or_path=args.model,
        device=args.device,
        batch_size=args.batch_size,
        shard_size=args.shard_size,
        max_sequence_length=args.max_sequence_length,
        force=args.force,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
