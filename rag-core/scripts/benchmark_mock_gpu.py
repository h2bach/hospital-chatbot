from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date
from pathlib import Path

from rag_core.evaluation import evaluate_retriever
from rag_core.indexing import SentenceTransformerProvider
from rag_core.reranking import SentenceTransformerReranker
from rag_core.retrieval import HybridRetriever, RetrievalConfig
from rag_core.schemas import Chunk, GoldenSample


QUERIES = {
    "Giờ hoạt động": "Bệnh viện làm việc vào giờ nào?",
    "Chuẩn bị trước dịch vụ": "Tôi cần chuẩn bị gì trước khi sử dụng dịch vụ?",
    "Chính sách bảo hiểm": "Bệnh viện có chính sách bảo hiểm như thế nào?",
    "Chính sách bảo mật và xác thực": "Thông tin của tôi được bảo mật và xác thực ra sao?",
    "Hướng dẫn nhận kết quả": "Tôi nhận kết quả khám bằng cách nào?",
    "Quy trình khiếu nại": "Tôi muốn gửi khiếu nại thì làm thế nào?",
    "Quy trình đặt lịch": "Quy trình đặt lịch khám như thế nào?",
    "Quy trình đổi và hủy lịch": "Làm sao để đổi hoặc hủy lịch khám?",
    "Quy tắc chuyển cấp cứu hoặc nhân viên": "Khi nào cần chuyển cấp cứu hoặc gặp nhân viên?",
}


def ensure_device(device: str, attempts: int = 3) -> None:
    if not device.startswith("cuda"):
        return
    import torch
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            if not torch.cuda.is_available():
                raise RuntimeError("torch.cuda.is_available() returned false")
            torch.empty(1, device=device)
            return
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2)
    raise RuntimeError(f"CUDA preflight failed after {attempts} attempts: {error}") from error


def load_mock_chunks(path: Path) -> tuple[list[Chunk], list[GoldenSample]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    today = date.today()
    chunks: list[Chunk] = []
    grouped: dict[str, list[Chunk]] = {}
    for index, item in enumerate(raw):
        end = date.fromisoformat(item["effective_to"]) if item.get("effective_to") else None
        active = not item.get("is_deleted", False) and (end is None or end >= today)
        if not active:
            continue
        title = item["chunk_title"]
        chunk = Chunk(
            chunk_id=item["chunk_id"], document_id=item["knowledge_document_id"],
            version_id=f'{item["knowledge_document_id"]}:v{item.get("version", 1)}',
            section_id=f'{item["knowledge_document_id"]}:{title}', chunk_index=index,
            content_type="paragraph", content_text=item["chunk_content"],
            retrieval_text=f'{title}. {item["chunk_content"]} Từ khóa: {" ".join(item.get("keywords", []))}',
            heading_path=[title], token_count=item.get("token_count", 0),
            effective_from=item.get("effective_from"), effective_to=item.get("effective_to"), is_active=True,
        )
        chunks.append(chunk)
        grouped.setdefault(title, []).append(chunk)
    samples = []
    for number, (title, query) in enumerate(QUERIES.items(), 1):
        expected = grouped.get(title, [])
        samples.append(GoldenSample(
            query_id=f"mock_{number:02d}", query=query, intent="knowledge_lookup", risk_level="low",
            expected_document_ids=[item.document_id for item in expected],
            expected_section_ids=[item.section_id for item in expected],
            expected_chunk_ids=[item.chunk_id for item in expected],
        ))
    return chunks, samples


def load_canonical(chunks_path: Path, golden_path: Path) -> tuple[list[Chunk], list[GoldenSample]]:
    chunks = [Chunk(**json.loads(line)) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    samples = [GoldenSample(**json.loads(line)) for line in golden_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return chunks, samples


def latency(retriever: HybridRetriever, samples: list[GoldenSample], mode: str, repeats: int = 2) -> dict[str, float]:
    values = []
    for _ in range(repeats):
        for sample in samples:
            started = time.perf_counter()
            retriever.retrieve(sample.query, RetrievalConfig(mode=mode))
            values.append((time.perf_counter() - started) * 1000)
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return {"p50_ms": round(statistics.median(ordered), 2), "p95_ms": round(ordered[p95_index], 2)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--golden", type=Path, help="Canonical golden JSONL; omit to use the mock adapter")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--embedding-model", default="BAAI/bge-m3")
    parser.add_argument("--reranker-model", default="BAAI/bge-reranker-v2-m3")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    ensure_device(args.device)
    chunks, samples = load_canonical(args.chunks, args.golden) if args.golden else load_mock_chunks(args.chunks)
    started = time.perf_counter()
    embedding = SentenceTransformerProvider(args.embedding_model, args.device)
    reranker = SentenceTransformerReranker(args.reranker_model, args.device)
    retriever = HybridRetriever(chunks, reranker=reranker, embedding_provider=embedding)
    build_seconds = time.perf_counter() - started
    reports = {}
    for mode in ("b0", "b1", "b2", "b3", "b4"):
        report = evaluate_retriever(retriever, samples, mode).to_dict()
        report["latency"] = latency(retriever, samples, mode)
        reports[mode] = report
    payload = {
        "embedding_model": args.embedding_model, "reranker_model": args.reranker_model,
        "device": args.device, "chunk_count": len(chunks), "golden_count": len(samples),
        "index_build_seconds": round(build_seconds, 2), "baselines": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
