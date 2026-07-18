import json
from pathlib import Path

from rag_core.indexing import build_index


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/data_rag"


def test_builds_canonical_multidocument_index_and_normalized_prices(tmp_path):
    report = build_index(SOURCE, tmp_path)
    assert report["document_count"] == 3
    assert report["chunk_count"] == 12738
    assert report["normalized_price_rows"] == 2946
    assert report["max_token_count"] <= 384
    assert report["duplicate_chunk_ids"] == 0
    assert report["price_diagnostics"]["continuation_rows_merged"] == 132
    assert report["price_diagnostics"]["orphan_continuations"] == 0
    assert report["price_diagnostics"]["malformed_numbered_rows"] == 0
    assert report["bhyt_diagnostics"]["parsed_chunks"] == 9731
    assert report["bhyt_diagnostics"]["chunks_by_source_type"] == {
        "policy": 28,
        "price": 9702,
        "update_alert": 1,
    }
    assert report["bhyt_diagnostics"]["missing_source_line_count"] == 0
    assert report["bhyt_diagnostics"]["inactive_chunk_count"] == 0

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
    assert len(bhyt_chunks) == 9731
    assert all(chunk["authority_level"] == 3 for chunk in bhyt_chunks)
    assert all(chunk["source_line_start"] > 0 for chunk in bhyt_chunks)
    assert {chunk["content_type"] for chunk in bhyt_chunks} == {
        "bhyt_policy",
        "bhyt_price_service",
        "bhyt_update_alert",
    }
