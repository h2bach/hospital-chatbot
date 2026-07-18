from rag_core.ingestion import ingest_markdown
from rag_core.retrieval import HybridRetriever, RetrievalConfig, reciprocal_rank_fusion


SOURCE = """# Hướng dẫn bệnh viện
## Bảo hiểm y tế
Người bệnh khám bảo hiểm cần mang thẻ bảo hiểm y tế và căn cước công dân.
## Đặt lịch khám
Người bệnh có thể đặt lịch khám tim qua tổng đài của bệnh viện.
## Xét nghiệm
Người bệnh cần nhịn ăn trước xét nghiệm đường huyết theo chỉ dẫn.
"""

CONFIG = {"document_id": "doc_retrieval", "title": "Hướng dẫn bệnh viện", "source_file": "test.md",
          "source_uri": "/test.md", "version_number": 1}


def build_retriever():
    result = ingest_markdown(SOURCE, CONFIG)
    return HybridRetriever(result.chunks), result


def test_all_baselines_return_traceable_chunks():
    retriever, result = build_retriever()
    ids = {chunk.chunk_id for chunk in result.chunks}
    for mode in ("b0", "b1", "b2", "b3", "b4"):
        found = retriever.retrieve("khám bảo hiểm mang giấy tờ gì", RetrievalConfig(mode=mode, final_k=2))
        assert found, mode
        assert all(item.chunk.chunk_id in ids for item in found)


def test_bm25_prefers_exact_hospital_terms():
    retriever, _ = build_retriever()
    result = retriever.retrieve("thẻ bảo hiểm y tế căn cước công dân", RetrievalConfig(mode="b0", final_k=1))
    assert "căn cước công dân" in result[0].chunk.content_text


def test_rrf_deduplicates_and_combines_scores():
    retriever, _ = build_retriever()
    bm25 = retriever.bm25.search("bảo hiểm", 3)
    dense = retriever.dense.search("bảo hiểm", 3)
    fused = reciprocal_rank_fusion([bm25, dense])
    assert len({item.chunk.chunk_id for item in fused}) == len(fused)
    assert fused[0].source == "hybrid"


def test_metadata_filter_excludes_non_matching_document():
    retriever, _ = build_retriever()
    result = retriever.retrieve("bảo hiểm", RetrievalConfig(mode="b2"), filters={"document_id": "missing"})
    assert result == []


def test_context_expansion_respects_budget_and_document_order():
    retriever, _ = build_retriever()
    result = retriever.retrieve("bảo hiểm", RetrievalConfig(mode="b4", final_k=1, max_context_tokens=100))
    assert sum(item.chunk.token_count for item in result) <= 100
    assert [item.chunk.chunk_index for item in result] == sorted(item.chunk.chunk_index for item in result)

