"""Quick test for retrieve_parallel() — no pytest needed, runs with stdlib only."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag_core.app import RAGApplication

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "artifacts" / "data-rag" / "chunks.jsonl"

print("Loading RAGApplication...")
t0 = time.perf_counter()
app = RAGApplication(CHUNKS)
print(f"  Loaded in {time.perf_counter() - t0:.1f}s — {app.health()['indexed_chunks']} chunks\n")

# === Test 1: Single query via retrieve (baseline) ===
queries = [
    {"query": "giá chụp X-quang ngực thẳng", "top_k": 5},
    {"query": "quy trình khám ngoại trú tại TN1 CS1", "top_k": 5},
    {"query": "quyền lợi BHYT tại bệnh viện Tim Hà Nội", "top_k": 5},
]

print("=== Test 1: Tuần tự (3 lần retrieve) ===")
t1 = time.perf_counter()
sequential_results = []
for q in queries:
    r = app.retrieve(q["query"], q["top_k"])
    sequential_results.append(r)
sequential_ms = (time.perf_counter() - t1) * 1000
print(f"  Latency: {sequential_ms:.0f}ms")
for i, r in enumerate(sequential_results):
    print(f"  Query {i+1}: status={r['answerability']['status']}, "
          f"confidence={r['answerability']['confidence']['score']:.2f}, "
          f"evidence={len(r['evidence'])}")

# === Test 2: Parallel via retrieve_parallel ===
print("\n=== Test 2: Song song (retrieve_parallel) ===")
t2 = time.perf_counter()
parallel_result = app.retrieve_parallel(queries)
parallel_ms = (time.perf_counter() - t2) * 1000
print(f"  Latency: {parallel_ms:.0f}ms")
print(f"  Schema: {parallel_result['schema_version']}")
print(f"  Query count: {parallel_result['query_count']}")
for i, r in enumerate(parallel_result["results"]):
    print(f"  Query {i+1}: status={r['answerability']['status']}, "
          f"confidence={r['answerability']['confidence']['score']:.2f}, "
          f"evidence={len(r['evidence'])}")

# === Test 3: Correctness — same results ===
print("\n=== Test 3: Kiểm tra kết quả giống nhau ===")
all_match = True
for i in range(len(queries)):
    seq_status = sequential_results[i]["answerability"]["status"]
    par_status = parallel_result["results"][i]["answerability"]["status"]
    seq_evidence = len(sequential_results[i]["evidence"])
    par_evidence = len(parallel_result["results"][i]["evidence"])
    match = seq_status == par_status and seq_evidence == par_evidence
    symbol = "✓" if match else "✗"
    print(f"  {symbol} Query {i+1}: seq={seq_status}/{seq_evidence}ev, par={par_status}/{par_evidence}ev")
    if not match:
        all_match = False

# === Test 4: Edge cases ===
print("\n=== Test 4: Edge cases ===")
empty_result = app.retrieve_parallel([])
print(f"  Empty queries: query_count={empty_result['query_count']} {'✓' if empty_result['query_count'] == 0 else '✗'}")

single_result = app.retrieve_parallel([{"query": "giá khám bệnh", "top_k": 3}])
print(f"  Single query: query_count={single_result['query_count']} {'✓' if single_result['query_count'] == 1 else '✗'}")

skip_empty = app.retrieve_parallel([{"query": "", "top_k": 5}, {"query": "giá khám bệnh"}])
print(f"  Skip empty query: query_count={skip_empty['query_count']} {'✓' if skip_empty['query_count'] == 1 else '✗'}")

# === Summary ===
speedup = sequential_ms / max(parallel_ms, 1)
print(f"\n{'='*50}")
print(f"Tuần tự:  {sequential_ms:.0f}ms")
print(f"Song song: {parallel_ms:.0f}ms")
print(f"Speedup:  {speedup:.2f}x {'🚀' if speedup > 1.2 else ''}")
print(f"Kết quả:  {'✓ PASS' if all_match else '✗ FAIL'}")
