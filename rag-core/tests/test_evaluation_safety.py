from rag_core.citations import render_evidence, validate_citations
from rag_core.evaluation import evaluate_retriever
from rag_core.generation import abstention_answer, build_generation_prompt
from rag_core.ingestion import ingest_markdown
from rag_core.retrieval import HybridRetriever
from rag_core.routing import route_query
from rag_core.schemas import Answerability, DataRequirement, GoldenSample, RiskLevel


SOURCE = """# Hướng dẫn viện
## Giấy tờ BHYT
Khám bảo hiểm cần thẻ bảo hiểm y tế và căn cước công dân.
## Đặt lịch
Quy trình đặt lịch được thực hiện qua tổng đài.
"""
CONFIG = {"document_id": "doc_eval", "title": "Hướng dẫn viện", "source_file": "eval.md",
          "source_uri": "/eval.md", "version_number": 1}


def test_evaluation_metrics_are_reproducible():
    ingestion = ingest_markdown(SOURCE, CONFIG)
    target = next(chunk for chunk in ingestion.chunks if "căn cước" in chunk.content_text)
    sample = GoldenSample("q1", "khám bảo hiểm mang giấy tờ gì", "procedure_guidance", "low",
                          [target.document_id], [target.section_id], [target.chunk_id])
    report = evaluate_retriever(HybridRetriever(ingestion.chunks), [sample], "b4")
    assert report.recall_at_k[1] == 1.0
    assert report.mrr == 1.0
    assert report.document_hit_rate == report.section_hit_rate == 1.0


def test_router_separates_static_dynamic_personal_and_emergency():
    assert route_query("Khám tim cần mang gì?").answerability == Answerability.ANSWERABLE_FROM_RAG
    assert route_query("Bác sĩ nào còn lịch chiều nay?").data_requirement == DataRequirement.DYNAMIC_DATA
    assert route_query("Cho tôi xem kết quả xét nghiệm").data_requirement == DataRequirement.PERSONAL_DATA
    emergency = route_query("Tôi đau ngực và khó thở")
    assert emergency.risk_level == RiskLevel.EMERGENCY
    assert emergency.answerability == Answerability.REQUIRES_HUMAN_HANDOFF


def test_grounding_only_allows_retrieved_chunk_ids():
    ingestion = ingest_markdown(SOURCE, CONFIG)
    evidence = HybridRetriever(ingestion.chunks).retrieve("bảo hiểm")
    prompt = build_generation_prompt("Cần mang gì?", evidence)
    assert evidence[0].chunk.chunk_id in prompt
    assert "<evidence" in render_evidence(evidence)
    assert validate_citations([evidence[0].chunk.chunk_id], evidence) == (True, [])
    assert validate_citations(["invented"], evidence) == (False, ["invented"])


def test_abstention_is_safe_default():
    route = route_query("Tôi đau ngực và khó thở")
    answer = abstention_answer(route)
    assert answer.confidence == "low"
    assert answer.requires_handoff is True
    assert answer.citations == []

