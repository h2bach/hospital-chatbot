from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class Intent(StrEnum):
    KNOWLEDGE_LOOKUP = "knowledge_lookup"
    PROCEDURE_GUIDANCE = "procedure_guidance"
    SERVICE_DISCOVERY = "service_discovery"
    DOCTOR_DISCOVERY = "doctor_discovery"
    APPOINTMENT_ACTION = "appointment_action"
    PATIENT_RECORD = "patient_record"
    PAYMENT_OR_INSURANCE = "payment_or_insurance"
    CLINICAL_INFORMATION = "clinical_information"
    EMERGENCY = "emergency"
    COMPLAINT_OR_FEEDBACK = "complaint_or_feedback"
    SMALL_TALK = "small_talk"


class DataRequirement(StrEnum):
    STATIC_KNOWLEDGE = "static_knowledge"
    DYNAMIC_DATA = "dynamic_data"
    PERSONAL_DATA = "personal_data"
    EXTERNAL_KNOWLEDGE = "external_knowledge"
    MULTI_SOURCE = "multi_source"


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EMERGENCY = "emergency"


class Answerability(StrEnum):
    ANSWERABLE_FROM_RAG = "answerable_from_rag"
    REQUIRES_TOOL = "requires_tool"
    REQUIRES_CLARIFICATION = "requires_clarification"
    REQUIRES_HUMAN_HANDOFF = "requires_human_handoff"
    MUST_REFUSE = "must_refuse"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Document(Serializable):
    document_id: str
    title: str
    source_file: str
    source_uri: str
    document_type: str = "general"
    department_id: str | None = None
    hospital_id: str = "heartcare_hospital"
    language: str = "vi"
    authority_level: int = 1
    access_level: str = "public"
    status: str = DocumentStatus.ACTIVE
    effective_from: str | None = None
    effective_to: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    content_hash: str = ""
    latest_version_id: str | None = None

    def is_effective(self, on_date: date | None = None) -> bool:
        current = on_date or date.today()
        start = date.fromisoformat(self.effective_from) if self.effective_from else None
        end = date.fromisoformat(self.effective_to) if self.effective_to else None
        return self.status == DocumentStatus.ACTIVE and (not start or start <= current) and (not end or current <= end)


@dataclass(slots=True)
class DocumentVersion(Serializable):
    version_id: str
    document_id: str
    version_number: int
    status: str = "published"
    issued_date: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    supersedes_version_id: str | None = None
    parser_version: str = "parser-0.1.0"
    chunker_version: str = "chunker-0.1.0"
    embedding_model: str = "hashing-baseline-v1"
    content_hash: str = ""
    ingested_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Section(Serializable):
    section_id: str
    document_id: str
    version_id: str
    parent_section_id: str | None
    section_level: int
    section_order: int
    heading: str
    heading_path: list[str]
    page_start: int | None = None
    page_end: int | None = None
    offset_start: int = 0
    offset_end: int = 0


@dataclass(slots=True)
class Chunk(Serializable):
    chunk_id: str
    document_id: str
    version_id: str
    section_id: str
    chunk_index: int
    content_type: str
    content_text: str
    retrieval_text: str
    heading_path: list[str]
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    parent_chunk_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    offset_start: int = 0
    offset_end: int = 0
    token_count: int = 0
    content_hash: str = ""
    authority_level: int = 1
    effective_from: str | None = None
    effective_to: str | None = None
    is_active: bool = True


@dataclass(slots=True)
class CitationSpan(Serializable):
    citation_id: str
    chunk_id: str
    page: int | None
    section_id: str
    start_offset: int
    end_offset: int
    quote_text: str
    source_anchor: str


@dataclass(slots=True)
class RetrievedChunk(Serializable):
    chunk: Chunk
    score: float
    source: str
    rank: int = 0
    bm25_score: float | None = None
    dense_score: float | None = None
    rerank_score: float | None = None


@dataclass(slots=True)
class QueryRoute(Serializable):
    intent: Intent
    data_requirement: DataRequirement
    risk_level: RiskLevel
    answerability: Answerability
    reason: str


@dataclass(slots=True)
class GoldenSample(Serializable):
    query_id: str
    query: str
    intent: str
    risk_level: str
    expected_document_ids: list[str]
    expected_section_ids: list[str]
    expected_chunk_ids: list[str]
    reference_answer: str = ""
    required_facts: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    answerability: str = Answerability.ANSWERABLE_FROM_RAG


@dataclass(slots=True)
class GroundedAnswer(Serializable):
    answer: str
    citations: list[dict[str, Any]]
    confidence: str
    requires_handoff: bool
    route: QueryRoute | None = None

