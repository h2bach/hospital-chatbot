from __future__ import annotations

from rag_core.citations import render_evidence
from rag_core.schemas import GroundedAnswer, QueryRoute, RetrievedChunk


SYSTEM_INSTRUCTION = """Bạn là trợ lý HeartCare AI. Chỉ trả lời bằng evidence được cung cấp.
Không bổ sung quy định bệnh viện từ kiến thức nội tại. Nếu evidence không đủ, hãy từ chối khẳng định.
Mỗi khẳng định thực tế phải có chunk_id hỗ trợ. Không chẩn đoán hoặc tự thay đổi điều trị.
Đầu ra JSON gồm answer, cited_chunk_ids, confidence, requires_handoff."""


def build_generation_prompt(query: str, evidence: list[RetrievedChunk]) -> str:
    return f"{SYSTEM_INSTRUCTION}\n\nCÂU HỎI:\n{query}\n\nEVIDENCE:\n{render_evidence(evidence)}"


def abstention_answer(route: QueryRoute | None = None) -> GroundedAnswer:
    return GroundedAnswer("Mình chưa tìm thấy thông tin đã được kiểm chứng đủ để trả lời câu hỏi này.", [], "low",
                          bool(route and route.answerability.value == "requires_human_handoff"), route)

