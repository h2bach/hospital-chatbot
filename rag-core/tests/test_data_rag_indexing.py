import json
from pathlib import Path

from rag_core.indexing import build_index


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs"


def test_builds_canonical_multidocument_index_and_normalized_prices(tmp_path):
    report = build_index(SOURCE, tmp_path)
    assert report["document_count"] == 3
    assert report["chunk_count"] == 12757
    assert report["normalized_price_rows"] == 2946
    assert report["max_token_count"] <= 384
    assert report["duplicate_chunk_ids"] == 0
    assert report["price_diagnostics"]["continuation_rows_merged"] == 132
    assert report["price_diagnostics"]["orphan_continuations"] == 0
    assert report["price_diagnostics"]["malformed_numbered_rows"] == 0
    assert report["bhyt_diagnostics"]["parsed_chunks"] == 9750
    assert report["bhyt_diagnostics"]["parsed_knowledge_chunks"] == 9731
    assert report["bhyt_diagnostics"]["legal_source_count"] == 19
    assert report["bhyt_diagnostics"]["chunks_by_source_type"] == {
        "policy": 28,
        "price": 9702,
        "update_alert": 1,
    }
    assert report["bhyt_diagnostics"]["missing_source_line_count"] == 0
    assert report["bhyt_diagnostics"]["inactive_chunk_count"] == 0
    assert report["bhyt_diagnostics"]["resolved_legal_basis_count"] == 19410
    assert report["bhyt_diagnostics"]["missing_legal_source_references"] == 0
    assert report["bhyt_diagnostics"]["chunks_with_legal_context"] == 9731

    normalized_lines = (tmp_path / "normalized-price-list.md").read_text(encoding="utf-8").splitlines()
    service_rows = normalized_lines[4:]
    assert len(service_rows) == 2946
    assert all(line.startswith("| ") for line in service_rows)
    assert any("Siêu âm doppler động mạch thận" in line and "103-106" in line for line in service_rows)

    chunks = [json.loads(line) for line in (tmp_path / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {chunk["document_id"] for chunk in chunks} == {
        "doc_qt_25_01",
        "doc_gia_dvbv_tim_hn",
        "doc_bhyt_benh_vien_tim_hn",
    }
    assert all(chunk["source_file"] in {
        "quy-trinh-don-tiep-benh-nhan.md",
        "GiaDVBV_tim_HN.md",
        "bhyt_benh_vien_tim_ha_noi_rag.json",
    } for chunk in chunks)

    bhyt_chunks = [chunk for chunk in chunks if chunk["document_id"] == "doc_bhyt_benh_vien_tim_hn"]
    assert len(bhyt_chunks) == 9750
    knowledge_chunks = [chunk for chunk in bhyt_chunks if chunk["content_type"] != "bhyt_legal_document"]
    assert len(knowledge_chunks) == 9731
    assert all(chunk["authority_level"] == 3 for chunk in knowledge_chunks)
    assert all(chunk["source_line_start"] > 0 for chunk in bhyt_chunks)
    assert {chunk["content_type"] for chunk in bhyt_chunks} == {
        "bhyt_legal_document",
        "bhyt_policy",
        "bhyt_price_service",
        "bhyt_update_alert",
    }

    legal_chunks = [chunk for chunk in bhyt_chunks if chunk["content_type"] == "bhyt_legal_document"]
    assert len(legal_chunks) == 19
    future = next(chunk for chunk in legal_chunks if chunk["metadata"]["source_id"] == "SRC_TT_25_2026_FUTURE")
    assert "Ngày ban hành: 2026-06-30" in future["content_text"]
    assert "Ngày hiệu lực: 2026-08-15" in future["content_text"]
    assert "Chưa có hiệu lực tại ngày chốt dữ liệu" in future["content_text"]

    historical = next(
        chunk for chunk in legal_chunks
        if chunk["metadata"]["source_id"] == "SRC_NQ_45_2024_HISTORICAL"
    )
    assert historical["effective_to"] == "2026-01-27"
    assert "Bị thay thế/bãi bỏ từ: 2026-01-27" in historical["content_text"]
    assert historical["is_active"] is True

    future_alert = next(
        chunk for chunk in knowledge_chunks
        if chunk["metadata"]["source_chunk_id"] == "POL_FUTURE_UPDATE_001"
    )
    legal_context = future_alert["metadata"]["legal_context"]
    assert legal_context[0]["resolution_status"] == "resolved"
    assert legal_context[0]["issued_date"] == "2026-06-30"
    assert legal_context[0]["effective_from"] == "2026-08-15"
    assert "Căn cứ pháp lý: 25/2026/TT-BYT" in future_alert["content_text"]


def test_latest_artifact_tag_writes_only_tagged_deterministic_files(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_report = build_index(SOURCE, first, artifact_tag="latest")
    second_report = build_index(SOURCE, second, artifact_tag="_latest")

    expected = {
        "documents_latest.jsonl",
        "sections_latest.jsonl",
        "chunks_latest.jsonl",
        "citations_latest.jsonl",
        "normalized-price-list_latest.md",
        "index_report_latest.json",
    }
    assert {path.name for path in first.iterdir()} == expected
    assert first_report["artifact_tag"] == "_latest"
    assert second_report["artifact_tag"] == "_latest"
    for filename in expected - {"index_report_latest.json"}:
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
