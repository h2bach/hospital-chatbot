from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from rag_core.app import RAGApplication


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def evaluate(chunks_path: Path, golden_path: Path) -> dict:
    app = RAGApplication(chunks_path)
    samples = [json.loads(line) for line in golden_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retrieval_samples = [sample for sample in samples if sample["kind"] == "retrieval"]
    recall = {1: 0, 3: 0, 5: 0}
    reciprocal_ranks = []
    failures = []
    latencies = []

    for sample in samples:
        started = time.perf_counter()
        retrieved = app.search(sample["query"], 5) if sample["kind"] == "retrieval" else []
        answer = app.answer(sample["query"])
        latencies.append((time.perf_counter() - started) * 1000)
        missing_terms = [term for term in sample.get("required_answer_terms", []) if term.casefold() not in answer.casefold()]
        if missing_terms:
            failures.append({"id": sample["id"], "type": "answer_terms", "missing": missing_terms})
        if sample["kind"] != "retrieval":
            continue
        expected = set(sample["expected_chunk_ids"])
        ranked_ids = [item.chunk.chunk_id for item in retrieved]
        for cutoff in recall:
            recall[cutoff] += bool(expected.intersection(ranked_ids[:cutoff]))
        rank = next((index for index, chunk_id in enumerate(ranked_ids, 1) if chunk_id in expected), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
        if not rank:
            failures.append({"id": sample["id"], "type": "retrieval", "retrieved": ranked_ids})

    count = len(retrieval_samples)
    return {
        "status": "pass" if not failures else "fail",
        "sample_count": len(samples),
        "retrieval_sample_count": count,
        "route_safety_sample_count": len(samples) - count,
        "recall_at_1": recall[1] / count,
        "recall_at_3": recall[3] / count,
        "recall_at_5": recall[5] / count,
        "mrr_at_5": statistics.fmean(reciprocal_ranks),
        "answer_term_pass_rate": (len(samples) - sum(failure["type"] == "answer_terms" for failure in failures)) / len(samples),
        "latency_ms_p50": round(percentile(latencies, 0.5), 2),
        "latency_ms_p95": round(percentile(latencies, 0.95), 2),
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the canonical docs/data_rag index")
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.chunks, args.golden)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
