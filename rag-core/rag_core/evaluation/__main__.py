from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_core.evaluation import evaluate_retriever
from rag_core.retrieval import HybridRetriever
from rag_core.schemas import Chunk, GoldenSample


def load_jsonl(path: Path, model):
    return [model(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare HeartCare retrieval baselines B0-B4")
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--golden", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    chunks = load_jsonl(args.chunks, Chunk)
    samples = load_jsonl(args.golden, GoldenSample)
    retriever = HybridRetriever(chunks)
    reports = {mode: evaluate_retriever(retriever, samples, mode).to_dict() for mode in ("b0", "b1", "b2", "b3", "b4")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"samples": len(samples), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

