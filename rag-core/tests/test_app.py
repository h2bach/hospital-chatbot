import json
from pathlib import Path

from rag_core.app import RAGApplication


ROOT = Path(__file__).resolve().parents[2]
APP = RAGApplication(
    ROOT / "rag-core/artifacts/data-rag/chunks.jsonl",
)


def test_health_reports_loaded_corpus_and_catalog():
    health = APP.health()
    assert health["status"] == "ok"
    assert health["document_count"] == 3
    assert health["indexed_chunks"] == 12738
    assert health["price_service_chunks"] == 12648
    assert health["bhyt_policy_chunks"] == 29
    assert health["knowledge_sources"] == 3


def test_knowledge_catalog_and_ordered_context_are_read_only_extensions():
    catalog = APP.knowledge_catalog()
    assert {item["document_id"] for item in catalog} == {
        "doc_qt_25_01",
        "doc_gia_dvbv_tim_hn",
        "doc_bhyt_benh_vien_tim_hn",
    }

    result = APP.expand_context("chk_f6142fc961652bf17c16", "section", 5)
    assert result["schema_version"] == "heartcare.rag.context.v1"
    assert result["status"] == "exact"
    assert result["anchor_chunk_id"] == "chk_f6142fc961652bf17c16"
    assert 1 <= len(result["chunks"]) <= 5
    assert [item["line_start"] for item in result["chunks"]] == sorted(
        item["line_start"] for item in result["chunks"]
    )


def test_unpublished_manifest_sources_are_not_searchable(tmp_path):
    manifest = tmp_path / "knowledge_sources.json"
    manifest.write_text(
        '[{"document_id":"doc_qt_25_01","status":"published"},'
        '{"document_id":"doc_gia_dvbv_tim_hn","status":"draft"}]',
        encoding="utf-8",
    )
    application = RAGApplication(
        ROOT / "rag-core/artifacts/data-rag/chunks.jsonl",
        knowledge_manifest_path=manifest,
    )
    assert application.health()["document_ids"] == ["doc_qt_25_01"]
    assert application.retrieve("Mã 19.0069.1829 giá bao nhiêu?", 5)["answerability"]["status"] == "insufficient"


def test_grounded_answer_has_canonical_citation():
    answer = APP.answer("Không mang thẻ bảo hiểm giấy thì dùng gì thay thế?")
    assert "Vss" in answer
    assert "CCCD" in answer
    assert "quy-trinh-don-tiep-benh-nhan.md" in answer


def test_price_answer_uses_structured_service_row_and_source_line():
    answer = APP.answer("Mã 18.0119.0012 giá bao nhiêu?")
    assert "Chụp X-quang ngực thẳng" in answer
    assert "64.300 đồng" in answer
    assert "GiaDVBV_tim_HN.md, dòng 203" in answer


def test_generic_examination_price_does_not_retrieve_process_text():
    answer = APP.answer("Giá khám bệnh tại cơ sở 1 là bao nhiêu?")
    assert "Giá Khám bệnh" in answer
    assert "50.600 đồng" in answer
    assert "GiaDVBV_tim_HN.md" in answer


def test_out_of_scope_question_abstains():
    answer = APP.answer("Ai là tổng thống Mỹ?")
    assert "chưa tìm thấy thông tin đủ căn cứ" in answer
    assert "**Nguồn:**" not in answer


def test_emergency_route_precedes_retrieval():
    answer = APP.answer("Tôi đang đau ngực dữ dội và khó thở")
    assert "115" in answer
    assert "không thể chẩn đoán" in answer.lower()


def test_dynamic_data_is_not_answered_from_static_rag():
    answer = APP.answer("Bác sĩ nào còn lịch chiều nay?")
    assert "dữ liệu vận hành" in answer
    assert "chunk_" not in answer


def test_legal_document_query_uses_exact_code_and_preserves_temporal_context(tmp_path):
    chunk = {
        "chunk_id": "chk_legal_test_000001",
        "document_id": "doc_bhyt_benh_vien_tim_hn",
        "section_id": "sec_legal",
        "content_text": (
            "Văn bản: Thông tư thử nghiệm\n"
            "Số/ký hiệu: 25/2026/TT-BYT\n"
            "Cơ quan ban hành: Bộ Y tế\n"
            "Ngày ban hành: 2026-06-30\n"
            "Ngày hiệu lực: 2026-08-15\n"
            "Trạng thái pháp lý: Chưa có hiệu lực tại ngày chốt dữ liệu"
        ),
        "retrieval_text": (
            "Thông tư 25/2026/TT-BYT Bộ Y tế ngày ban hành ngày hiệu lực. "
            "Ngày ban hành 2026-06-30. Ngày hiệu lực 2026-08-15."
        ),
        "heading_path": ["BHYT", "Danh mục nguồn", "Thông tư"],
        "token_count": 40,
        "page_start": None,
        "is_active": True,
        "content_type": "bhyt_legal_document",
        "source_file": "bhyt_benh_vien_tim_ha_noi_rag.json",
        "source_line_start": 175,
        "source_line_end": 175,
        "metadata": {
            "source_id": "SRC_TT_25_2026_FUTURE",
            "document_code": "25/2026/TT-BYT",
            "title": "Thông tư thử nghiệm",
            "issuer": "Bộ Y tế",
            "issued_date": "2026-06-30",
            "effective_from": "2026-08-15",
            "legal_status": "Chưa có hiệu lực tại ngày chốt dữ liệu",
        },
    }
    chunks_path = tmp_path / "chunks_latest.jsonl"
    chunks_path.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")
    application = RAGApplication(chunks_path)

    result = application.retrieve("Thông tư 25/2026/TT-BYT ban hành và có hiệu lực khi nào?", 5)
    assert result["answerability"]["status"] == "exact"
    assert result["answerability"]["confidence"]["reason_codes"] == ["EXACT_LEGAL_DOCUMENT_CODE"]
    assert result["evidence"][0]["chunk"]["facts"]["issued_date"] == "2026-06-30"
    assert result["evidence"][0]["chunk"]["facts"]["effective_from"] == "2026-08-15"
    assert "Ngày hiệu lực: 2026-08-15" in application.answer(
        "Thông tư 25/2026/TT-BYT có hiệu lực khi nào?"
    )

    missing = application.retrieve("Thông tư 99/2099/TT-BYT có hiệu lực khi nào?", 5)
    assert missing["answerability"]["status"] == "insufficient"
    assert missing["evidence"] == []


def test_session_contract_matches_existing_frontend():
    session_id = APP.create_session("browser-a")
    response = APP.post_message(session_id, "Tôi chưa đặt lịch thì bắt đầu từ đâu?", "browser-a")
    assert response and "cây lấy số" in response
    session = APP.get_session(session_id, "browser-a")
    assert session and [item["Role"] for item in session["Context"]["Messages"]] == ["User", "Assistant"]
    assert APP.get_session(session_id, "browser-b") is None
    assert APP.list_sessions("browser-b") == []
    assert APP.delete_session(session_id, "browser-a")
