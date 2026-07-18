from __future__ import annotations

import unicodedata

from rag_core.schemas import Answerability, DataRequirement, Intent, QueryRoute, RiskLevel


def _fold(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(char) != "Mn")


def route_query(query: str) -> QueryRoute:
    value = _fold(query)
    emergency = ("dau nguc", "kho tho", "ngat", "dot quy", "chay mau nhieu", "tu tu")
    if any(term in value for term in emergency):
        return QueryRoute(Intent.EMERGENCY, DataRequirement.EXTERNAL_KNOWLEDGE, RiskLevel.EMERGENCY,
                          Answerability.REQUIRES_HUMAN_HANDOFF, "Detected emergency symptom or safety phrase")
    personal = ("ho so cua toi", "ket qua xet nghiem", "benh an", "thanh toan cua toi")
    if any(term in value for term in personal):
        return QueryRoute(Intent.PATIENT_RECORD, DataRequirement.PERSONAL_DATA, RiskLevel.HIGH,
                          Answerability.REQUIRES_TOOL, "Personal health/transaction data must come from an authenticated tool")
    dynamic = ("hom nay", "chieu nay", "con lich", "gia hien tai", "dang truc", "giuong trong", "trang thai")
    if any(term in value for term in dynamic):
        intent = Intent.DOCTOR_DISCOVERY if "bac si" in value or "lich" in value else Intent.SERVICE_DISCOVERY
        return QueryRoute(intent, DataRequirement.DYNAMIC_DATA, RiskLevel.LOW, Answerability.REQUIRES_TOOL,
                          "Time-sensitive operational data must come from an API")
    if any(term in value for term in ("chan doan", "ke don", "doi thuoc", "lieu dung")):
        return QueryRoute(Intent.CLINICAL_INFORMATION, DataRequirement.EXTERNAL_KNOWLEDGE, RiskLevel.HIGH,
                          Answerability.REQUIRES_HUMAN_HANDOFF, "Diagnosis or treatment request requires clinical oversight")
    intent = Intent.PAYMENT_OR_INSURANCE if "bao hiem" in value or "thanh toan" in value else Intent.PROCEDURE_GUIDANCE
    return QueryRoute(intent, DataRequirement.STATIC_KNOWLEDGE, RiskLevel.LOW,
                      Answerability.ANSWERABLE_FROM_RAG, "Static hospital knowledge query")

