from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class DenseIndex:
    def __init__(self, dense_root: Path, chunks_path: Path, model_path: str, device: str = "cpu"):
        import numpy as np
        import torch
        from sentence_transformers import SentenceTransformer

        current = json.loads((dense_root / "current.json").read_text(encoding="utf-8"))
        artifact_dir = dense_root / current["index_id"]
        self.manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest.get("status") != "complete":
            raise RuntimeError("Dense artifact chưa ở trạng thái complete")
        digest = hashlib.sha256()
        with chunks_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != self.manifest.get("chunks_sha256"):
            raise RuntimeError("Dense artifact không khớp canonical chunks hiện tại")

        self.chunk_ids: list[str] = []
        matrices = []
        for shard in self.manifest["shards"]:
            self.chunk_ids.extend(json.loads((artifact_dir / shard["chunk_ids_file"]).read_text(encoding="utf-8")))
            matrices.append(np.load(artifact_dir / shard["embedding_file"], allow_pickle=False))
        self.matrix = np.concatenate(matrices, axis=0)
        if self.matrix.shape != (len(self.chunk_ids), self.manifest["embedding_dimension"]):
            raise RuntimeError("Dense artifact shape không khớp manifest")
        if len(self.chunk_ids) != self.manifest.get("chunk_count") or len(set(self.chunk_ids)) != len(self.chunk_ids):
            raise RuntimeError("Dense artifact có số lượng hoặc chunk ID không hợp lệ")
        if not np.isfinite(self.matrix).all():
            raise RuntimeError("Dense artifact chứa embedding không hữu hạn")

        self.content_types: dict[str, str] = {}
        with chunks_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    chunk = json.loads(line)
                    self.content_types[str(chunk["chunk_id"])] = str(chunk.get("content_type", "paragraph"))
        if any(chunk_id not in self.content_types for chunk_id in self.chunk_ids):
            raise RuntimeError("Dense artifact có chunk ID không tồn tại trong canonical chunks")

        if device.startswith("cuda"):
            if not torch.cuda.is_available():
                raise RuntimeError("Dense service yêu cầu CUDA nhưng không truy cập được GPU")
            torch.cuda.init()
        self.device = device
        self.model = SentenceTransformer(model_path, device=device, local_files_only=Path(model_path).exists())
        self.model.max_seq_length = int(self.manifest["max_sequence_length"])
        self.lock = threading.Lock()
        self.np = np
        self.cuda_device = torch.cuda.get_device_name(0) if device.startswith("cuda") else None

    def health(self) -> dict:
        return {
            "status": "ok",
            "service": "heartcare-dense-retrieval",
            "index_id": self.manifest["index_id"],
            "chunk_count": len(self.chunk_ids),
            "embedding_dimension": self.manifest["embedding_dimension"],
            "model": "BAAI/bge-m3",
            "device": self.device,
            "cuda_device": self.cuda_device,
        }

    def search(self, query: str, top_k: int, allowed_content_types: set[str]) -> list[dict]:
        with self.lock:
            vector = self.model.encode(
                [query],
                batch_size=1,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
                device=self.device,
            )[0]
        scores = self.matrix @ vector
        candidate_count = min(len(scores), max(top_k * 12, 256))
        indices = self.np.argpartition(-scores, candidate_count - 1)[:candidate_count]
        indices = indices[self.np.argsort(-scores[indices])]
        results = []
        for index in indices:
            chunk_id = self.chunk_ids[int(index)]
            content_type = self.content_types[chunk_id]
            if allowed_content_types and content_type not in allowed_content_types:
                continue
            results.append({
                "chunk_id": chunk_id,
                "score": round(float(scores[index]), 7),
                "content_type": content_type,
            })
            if len(results) >= top_k:
                break
        return results


class Handler(BaseHTTPRequestHandler):
    index: DenseIndex

    def log_message(self, format: str, *args) -> None:
        return

    def send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(HTTPStatus.OK, self.index.health())
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/search":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 64 * 1024:
                raise ValueError("invalid_content_length")
            payload = json.loads(self.rfile.read(length))
            query = str(payload.get("query", "")).strip()
            if not query or len(query) > 4000:
                raise ValueError("invalid_query")
            top_k = max(1, min(int(payload.get("top_k", 20)), 100))
            allowed = {str(value) for value in payload.get("content_types", []) if str(value)}
            results = self.index.search(query, top_k, allowed)
            self.send_json(HTTPStatus.OK, {
                "schema_version": "heartcare.rag.dense-search.v1",
                "query": query,
                "index_id": self.index.manifest["index_id"],
                "results": results,
            })
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "dense_search_failed"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Internal BGE-M3 dense retrieval service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6690)
    parser.add_argument("--dense-root", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("RAG_EMBEDDING_MODEL"), required=not os.getenv("RAG_EMBEDDING_MODEL"))
    parser.add_argument("--device", default=os.getenv("RAG_EMBEDDING_DEVICE", "cpu"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index = DenseIndex(args.dense_root, args.chunks, args.model, args.device)
    Handler.index = index
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print(json.dumps(index.health(), ensure_ascii=False), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
