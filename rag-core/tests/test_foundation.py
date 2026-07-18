import json

from rag_core.ingestion import ingest_markdown
from rag_core.parsing import parse_markdown
from rag_core.storage import CanonicalStore


SOURCE = """<!-- page: 3 -->
# Hướng dẫn BHYT
## Giấy tờ
<!-- source-offset: 100-180 -->
Người bệnh cần mang căn cước công dân và thẻ bảo hiểm y tế.

## Quy trình
1. Đăng ký.
2. Xuất trình giấy tờ.
"""

CONFIG = {
    "document_id": "doc_test",
    "title": "Hướng dẫn BHYT",
    "source_file": "test.md",
    "source_uri": "/test.md",
    "authority_level": 3,
    "effective_from": "2026-01-01",
    "version_number": 1,
}


def test_parser_preserves_structure_and_source_location():
    parsed = parse_markdown(SOURCE)
    paragraph = next(node for node in parsed.nodes if node.node_type == "paragraph")
    assert paragraph.heading_path == ["Hướng dẫn BHYT", "Giấy tờ"]
    assert paragraph.page_start == 3
    assert (paragraph.offset_start, paragraph.offset_end) == (100, 180)
    assert any(node.node_type == "list" for node in parsed.nodes)


def test_ingestion_is_deterministic_and_keeps_one_chunk_id_everywhere():
    first = ingest_markdown(SOURCE, CONFIG)
    second = ingest_markdown(SOURCE, CONFIG)
    assert first.document.document_id == second.document.document_id
    assert [item.chunk_id for item in first.chunks] == [item.chunk_id for item in second.chunks]
    assert {item.chunk_id for item in first.chunks} == {item.chunk_id for item in first.citations}
    assert first.chunks[0].content_text != first.chunks[0].retrieval_text


def test_canonical_store_upsert_and_deactivate(tmp_path):
    result = ingest_markdown(SOURCE, CONFIG)
    store = CanonicalStore(tmp_path / "rag.db")
    store.upsert_ingestion(result.document, result.version, result.sections, result.chunks, result.citations)
    store.upsert_ingestion(result.document, result.version, result.sections, result.chunks, result.citations)
    assert len(store.active_chunks()) == len(result.chunks)
    store.deactivate_document(result.document.document_id)
    assert store.active_chunks() == []
    store.close()

