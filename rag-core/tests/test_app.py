from pathlib import Path

import pytest

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


def test_cpu_mode_forces_bm25_even_when_dense_url_is_present():
    application = RAGApplication(
        ROOT / "rag-core/artifacts/data-rag/chunks.jsonl",
        dense_url="http://dense-retrieval:6690",
        retrieval_mode="cpu",
    )
    health = application.health()
    assert health["retrieval_mode"] == "cpu"
    assert health["retriever"] == "bm25"
    assert application.dense_client is None


def test_gpu_mode_requires_dense_service_url():
    with pytest.raises(ValueError, match="DENSE_RETRIEVAL_URL"):
        RAGApplication(
            ROOT / "rag-core/artifacts/data-rag/chunks.jsonl",
            dense_url="",
            retrieval_mode="gpu",
        )


def test_gpu_mode_reports_hybrid_retrieval_when_configured():
    application = RAGApplication(
        ROOT / "rag-core/artifacts/data-rag/chunks.jsonl",
        dense_url="http://dense-retrieval:6690",
        retrieval_mode="gpu",
    )
    health = application.health()
    assert health["retrieval_mode"] == "gpu"
    assert health["retriever"] == "bm25+bge-m3-hybrid"


def test_invalid_retrieval_mode_is_rejected():
    with pytest.raises(ValueError, match="auto, cpu hoặc gpu"):
        RAGApplication(
            ROOT / "rag-core/artifacts/data-rag/chunks.jsonl",
            retrieval_mode="tpu",
        )


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


def test_session_contract_matches_existing_frontend():
    session_id = APP.create_session("browser-a")
    response = APP.post_message(session_id, "Tôi chưa đặt lịch thì bắt đầu từ đâu?", "browser-a")
    assert response and "cây lấy số" in response
    session = APP.get_session(session_id, "browser-a")
    assert session and [item["Role"] for item in session["Context"]["Messages"]] == ["User", "Assistant"]
    assert APP.get_session(session_id, "browser-b") is None
    assert APP.list_sessions("browser-b") == []
    assert APP.delete_session(session_id, "browser-a")
