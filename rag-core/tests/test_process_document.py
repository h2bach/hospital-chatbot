from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "mock-data/mock_data/quy-trinh-don-tiep-benh-nhan.md"
GOLDEN = Path(__file__).resolve().parents[1] / "examples/quy-trinh-don-tiep.golden.jsonl"
CHUNKS = Path(__file__).resolve().parents[1] / "artifacts/quy-trinh-don-tiep/chunks.jsonl"


def test_real_process_document_preserves_pages_and_chunk_limits():
    import json
    chunks = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    pages = {chunk["page_start"] for chunk in chunks}
    assert set(range(2, 11)) <= pages
    assert max(chunk["token_count"] for chunk in chunks) <= 384
    assert len(chunks) == 65


def test_real_process_golden_ids_exist_in_canonical_chunks():
    import json
    available = {json.loads(line)["chunk_id"] for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()}
    samples = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {chunk_id for sample in samples for chunk_id in sample["expected_chunk_ids"]}
    assert len(samples) == 15
    assert expected <= available
