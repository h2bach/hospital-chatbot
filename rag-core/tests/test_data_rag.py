import json
from pathlib import Path

from rag_core.app import APPROXIMATE_DISCLOSURE, RAGApplication
from rag_core.indexing import build_index


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/data_rag"
ARTIFACT = ROOT / "rag-core/artifacts/data-rag"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_index_covers_all_documents_and_normalizes_split_price_rows(tmp_path):
    report = build_index(SOURCE, tmp_path)
    assert report["document_count"] == 3
    assert report["chunks_by_document"] == {
        "doc_qt_25_01": 61,
        "doc_gia_dvbv_tim_hn": 2946,
        "doc_bhyt_benh_vien_tim_hn": 9731,
    }
    assert report["price_diagnostics"]["parsed_entries"] == 2946
    assert report["price_diagnostics"]["continuation_rows_merged"] == 132
    assert report["price_diagnostics"]["orphan_continuations"] == 0
    assert report["price_diagnostics"]["malformed_numbered_rows"] == 0
    assert report["duplicate_chunk_ids"] == 0
    assert report["max_token_count"] <= 384
    assert report["bhyt_diagnostics"]["parsed_chunks"] == 9731
    assert report["bhyt_diagnostics"]["missing_source_line_count"] == 0

    chunks = load_jsonl(tmp_path / "chunks.jsonl")
    process_chunks = [chunk for chunk in chunks if chunk["document_id"] == "doc_qt_25_01"]
    assert not any("float:right" in chunk["content_text"] for chunk in process_chunks)
    assert sum(bool((chunk.get("metadata") or {}).get("process_step")) for chunk in process_chunks) >= 14
    split_row = next(
        chunk for chunk in chunks
        if (chunk.get("metadata") or {}).get("service_code") == "18.0069.0010"
    )
    assert "mặt thấp hoặc mặt cao" in split_row["metadata"]["service_name"]
    assert split_row["source_line_start"] == 151
    assert split_row["source_line_end"] == 154


def test_index_is_deterministic_except_for_report_timestamp(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_index(SOURCE, first)
    build_index(SOURCE, second)
    for filename in (
        "documents.jsonl", "sections.jsonl", "chunks.jsonl", "citations.jsonl", "normalized-price-list.md",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_bound_rag_answers_exact_price_and_process_questions():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    price = app.answer("Dịch vụ mã 02.0446.0008 giá bao nhiêu?")
    assert "Siêu âm doppler màu tim 3D/4D qua thực quản" in price
    assert "834.300 đồng" in price
    assert "dòng 124" in price

    process = app.answer("Không mang thẻ BHYT giấy thì dùng gì thay thế?")
    assert "Vss - ID" in process
    assert "CCCD gắn chíp" in process
    assert "trang 4" in process


def test_bound_rag_handles_ambiguity_scope_and_safety():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    ambiguous = app.answer("Giá siêu âm tim?")
    assert "chưa chỉ rõ biến thể kỹ thuật" in ambiguous
    assert ambiguous.count("Cơ sở 1") == 3

    outside = app.answer("Bệnh viện có chữa ung thư bằng proton không?")
    assert "chưa tìm thấy thông tin đủ căn cứ" in outside
    assert "**Nguồn:**" not in outside

    dynamic = app.answer("Giá hiện tại là bao nhiêu?")
    assert "dữ liệu vận hành" in dynamic

    emergency = app.answer("Tôi đang đau ngực dữ dội và khó thở")
    assert "115" in emergency
    assert "không thể chẩn đoán" in emergency.lower()


def test_unrelated_query_is_insufficient_in_evidence_contract():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")

    response = app.retrieve("Ai là tổng thống Mỹ?", top_k=5)

    assert response["answerability"]["status"] == "insufficient"
    assert response["evidence"] == []
    assert response["route"]["decision"] == "out_of_scope"


def test_unaccented_queries_are_retrievable():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    answer = app.answer("gia sieu am tim qua thuc quan cap cuu tai giuong?")
    assert "02.0443.0008" in answer
    assert "834.300 đồng" in answer


def test_process_title_query_returns_concrete_multi_step_overview():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    answer = app.answer(
        "quy trình đón tiếp bệnh nhân và khám chữa bệnh ngoại trú tại khu TN1 - CS1"
    )
    assert "Nhận đặt lịch khám Tự nguyện 1" in answer
    assert "cây lấy số tự động" in answer
    assert "Tiếp nhận thông tin đăng ký khám" in answer
    assert "Vss - ID" in answer
    assert "Thực hiện đo dấu hiệu sinh tồn" in answer
    assert "chỉ định CLS" in answer
    assert "Khám bệnh và kê đơn" in answer
    assert "lĩnh thuốc" in answer
    assert "trang 4" in answer and "trang 8" in answer
    assert "float:right" not in answer


def test_structured_retrieval_finds_service_entity_without_price_keyword():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    result = app.retrieve("Tôi muốn tìm thông tin cụ thể về SPECT/CT Tetrofosmin")

    assert result["schema_version"] == "heartcare.rag.evidence.v1"
    assert result["answerability"]["status"] == "approximate"
    assert result["generation_policy"]["disclosure"]["text"] == APPROXIMATE_DISCLOSURE
    assert result["evidence"][0]["chunk"]["facts"]["service_code"] == "19.0069.1829"
    assert result["evidence"][0]["chunk"]["facts"]["facility_1_price"] == "969.800"
    assert "Chưa bao gồm dược chất phóng xạ" in result["evidence"][0]["chunk"]["facts"]["note"]


def test_structured_retrieval_exact_service_code_and_name():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    by_code = app.retrieve("Mã 19.0069.1829 có thông tin gì?")
    by_name = app.retrieve("Thông tin về SPECT/CT tưới máu cơ tim gắng sức với Tetrofosmin")

    for result in (by_code, by_name):
        assert result["answerability"]["status"] == "exact"
        assert len(result["evidence"]) == 1
        assert result["evidence"][0]["chunk"]["facts"]["service_code"] == "19.0069.1829"
        assert result["citations"][0]["line_start"] == 3395


def test_structured_retrieval_abstains_for_missing_service_hard_negatives():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    missing_code = app.retrieve("Mã 99.9999.9999 giá bao nhiêu?")
    missing_entity = app.retrieve("Giá dịch vụ proton bao nhiêu?")

    for result in (missing_code, missing_entity):
        assert result["answerability"]["status"] == "insufficient"
        assert result["evidence"] == []
        assert result["citations"] == []


def test_structured_retrieval_marks_underspecified_price_as_approximate():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    result = app.retrieve("Giá siêu âm tim?")

    assert result["answerability"]["status"] == "approximate"
    assert result["generation_policy"]["disclosure"]["required"] is True
    assert len(result["evidence"]) >= 2
    assert all("Siêu âm" in item["chunk"]["facts"]["service_name"] for item in result["evidence"])


def test_valve_surgery_category_clarifies_top_five_then_selected_service_is_exact():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    approximate = app.retrieve("Tôi muốn tham khảo chi phí phẫu thuật van tim", top_k=5)

    assert approximate["answerability"]["status"] == "approximate"
    options = approximate["clarification"]["options"]
    assert len(options) == 5
    assert all(option["similarity"] >= 0.80 for option in options)
    assert all(
        "van" in option["label"].lower() and "tim" in option["label"].lower()
        for option in options
    )

    selected = next(option for option in options if "10.0227.0403" in option["label"])
    exact = app.retrieve(selected["selection_query"], top_k=5)
    assert exact["answerability"]["status"] == "exact"
    assert len(exact["evidence"]) == 1
    facts = exact["evidence"][0]["chunk"]["facts"]
    assert facts["service_name"] == "Phẫu thuật thay lại 1 van tim"
    assert facts["facility_1_price"] == "18.650.800"
    assert "van tim nhân tạo" in facts["note"]


def test_fuzzy_typo_returns_only_verified_top_five_clarification_choices():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    result = app.retrieve("Tôi muốn tìm thông tin về SPECT/CT sử dụng Terofomin", top_k=5)

    assert result["answerability"]["status"] == "approximate"
    assert result["generation_policy"]["mode"] == "clarify_selection"
    assert result["clarification"]["required"] is True
    assert 1 <= len(result["clarification"]["options"]) <= 5
    assert all(option["similarity"] >= 0.80 for option in result["clarification"]["options"])
    assert [option["label"] for option in result["clarification"]["options"]] == [
        "SPECT/CT tưới máu cơ tim gắng sức với Tetrofosmin (Mã 19.0069.1829)",
        "SPECT/CT tưới máu cơ tim không gắng sức với Tetrofosmin (Mã 19.0071.1829)",
    ]


def test_fuzzy_entity_only_query_returns_top_five_and_selection_becomes_exact():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    approximate = app.retrieve("Tetrofomin", top_k=5)

    assert approximate["answerability"]["status"] == "approximate"
    assert len(approximate["clarification"]["options"]) == 5
    selected_query = approximate["clarification"]["options"][0]["selection_query"]
    exact = app.retrieve(selected_query, top_k=5)
    assert exact["answerability"]["status"] == "exact"
    assert len(exact["evidence"]) == 1


def test_misspelled_process_title_requires_confirmation_but_wrong_site_abstains():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    typo = app.retrieve("quy trih don tiep benh nhn ngoai tru TN1 CS1", top_k=5)
    wrong_site = app.retrieve("quy trình khám ngoại trú tại khu TN9 - CS3", top_k=5)

    assert typo["answerability"]["status"] == "approximate"
    assert typo["clarification"]["options"][0]["label"].startswith("Quy trình đón tiếp bệnh nhân")
    assert typo["clarification"]["options"][0]["similarity"] >= 0.80
    assert wrong_site["answerability"]["status"] == "insufficient"
    assert wrong_site["evidence"] == []


def test_structured_process_overview_contains_concrete_step_evidence():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    result = app.retrieve("quy trình đón tiếp bệnh nhân và khám chữa bệnh ngoại trú tại khu TN1 - CS1")

    assert result["answerability"]["status"] == "exact"
    steps = [item["chunk"]["facts"].get("process_step", "") for item in result["evidence"]]
    assert any("Nhận đặt lịch khám Tự nguyện 1" in step for step in steps)
    assert any("Tiếp nhận thông tin đăng ký khám" in step for step in steps)
    assert any("Khám bệnh và kê đơn" in step for step in steps)


def test_unambiguous_short_process_query_is_exact_but_typo_still_clarifies():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")

    exact = app.retrieve("Cho tôi quy trình khám ngoại trú tại khu TN1 CS1", top_k=5)
    typo = app.retrieve("Cho tôi quy trih khám ngoại trú tại khu TN1 CS1", top_k=5)

    assert exact["answerability"]["status"] == "exact"
    assert any(
        "Khám bệnh và kê đơn" in item["chunk"]["facts"].get("process_step", "")
        for item in exact["evidence"]
    )
    assert typo["answerability"]["status"] == "approximate"
    assert typo["clarification"]["options"][0]["similarity"] >= 0.80


def test_bhyt_policy_questions_return_exact_atomic_evidence():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")

    entitlement = app.retrieve("Thẻ BHYT được hưởng bao nhiêu phần trăm?", top_k=5)
    scope = app.retrieve("BHYT chi trả những khoản nào?", top_k=5)

    assert entitlement["answerability"]["status"] == "exact"
    assert len(entitlement["evidence"]) == 1
    assert entitlement["evidence"][0]["chunk"]["content_type"] == "bhyt_policy"
    assert entitlement["evidence"][0]["chunk"]["facts"]["source_chunk_id"] == "POL_BASE_RATE_001"
    assert scope["answerability"]["status"] == "exact"
    assert len(scope["evidence"]) == 1
    assert scope["evidence"][0]["chunk"]["facts"]["source_chunk_id"] == "POL_SCOPE_001"


def test_bhyt_price_lookup_is_grounded_but_does_not_claim_hospital_availability():
    app = RAGApplication(ARTIFACT / "chunks.jsonl")
    result = app.retrieve("Mã 01.0303.0001 theo BHYT có giá bao nhiêu?", top_k=5)

    assert result["answerability"]["status"] == "exact"
    assert len(result["evidence"]) == 1
    chunk = result["evidence"][0]["chunk"]
    assert chunk["content_type"] == "bhyt_price_service"
    assert chunk["facts"]["service_code"] == "01.0303.0001"
    assert chunk["facts"]["hospital_current_availability_confirmed"] is False
    assert "Chưa xác nhận kỹ thuật này hiện được Bệnh viện Tim Hà Nội cung cấp" in chunk["content_text"]

    answer = app.answer("Mã 01.0303.0001 theo BHYT có giá bao nhiêu?")
    assert "không tự động xác nhận Bệnh viện Tim Hà Nội đang cung cấp" in answer
    assert "không phải tổng hóa đơn" in answer

    approximate = app.retrieve("Tôi muốn tham khảo chi phí phẫu thuật van tim theo BHYT", top_k=5)
    assert approximate["answerability"]["status"] == "approximate"
    assert all(
        "theo BHYT" in option["selection_query"]
        for option in approximate["clarification"]["options"]
    )
