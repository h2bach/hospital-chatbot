from __future__ import annotations

import argparse
import difflib
import json
import math
import mimetypes
import os
import re
import signal
import threading
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import unquote, urlparse


APPROXIMATE_DISCLOSURE = (
    "Thông tin bạn cung cấp chưa chính xác hoặc còn thiếu. "
    "Có phải ý của bạn là một trong các mục sau?"
)
MIN_APPROXIMATE_SIMILARITY = 0.80
PROCESS_OVERVIEW_TITLE = "Quy trình đón tiếp bệnh nhân và khám chữa bệnh ngoại trú tại khu TN1 - CS1"
INSUFFICIENT_RAG_MESSAGE = (
    "Hiện tôi chưa tìm thấy thông tin đủ căn cứ trong kho tri thức đã cung cấp để trả lời câu hỏi này. "
    "Anh/chị vui lòng liên hệ quầy tiếp đón hoặc kênh chính thức của bệnh viện."
)


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    section_id: str
    content_text: str
    retrieval_text: str
    heading_path: list[str]
    token_count: int
    page_start: int | None
    is_active: bool
    content_type: str = "paragraph"
    source_file: str = ""
    source_line_start: int | None = None
    source_line_end: int | None = None
    metadata: dict | None = None


@dataclass(slots=True)
class RetrievedChunk:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    terms = canonical_tokens(text)
    expanded = []
    for term in terms:
        expanded.append(term)
        folded = fold(term)
        if folded != term:
            expanded.append(folded)
    return expanded


def canonical_tokens(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", unicodedata.normalize("NFC", text.lower()), re.UNICODE)


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.chunks: list[Chunk] = []
        self.chunks_by_id: dict[str, Chunk] = {}
        self.tf: dict[str, Counter[str]] = {}
        self.df: Counter[str] = Counter()
        self.lengths: dict[str, int] = {}
        self.postings: dict[str, list[tuple[str, int]]] = defaultdict(list)
        self.average_length = 0.0

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self.tf.clear()
        self.df.clear()
        self.lengths.clear()
        self.postings.clear()
        lengths = []
        for chunk in chunks:
            terms = tokenize(chunk.retrieval_text)
            frequencies = Counter(terms)
            self.tf[chunk.chunk_id] = frequencies
            self.df.update(frequencies.keys())
            self.lengths[chunk.chunk_id] = len(terms)
            lengths.append(len(terms))
            for term, frequency in frequencies.items():
                self.postings[term].append((chunk.chunk_id, frequency))
        self.average_length = sum(lengths) / max(1, len(lengths))

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        terms, count = tokenize(query), len(self.chunks)
        scores: dict[str, float] = defaultdict(float)
        for term in terms:
            df = self.df[term]
            if not df:
                continue
            idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
            for chunk_id, frequency in self.postings[term]:
                length = self.lengths[chunk_id]
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / (self.average_length or 1))
                scores[chunk_id] += idf * frequency * (self.k1 + 1) / denominator
        results = [
            RetrievedChunk(self.chunks_by_id[chunk_id], score)
            for chunk_id, score in scores.items()
        ]
        return sorted(results, key=lambda item: (-item.score, item.chunk.chunk_id))[:top_k]


class DenseClient:
    """Internal dense retriever that can only return known canonical chunks."""

    def __init__(self, base_url: str, chunks_by_id: dict[str, Chunk], timeout: float = 8.0):
        self.base_url = base_url.rstrip("/")
        self.chunks_by_id = chunks_by_id
        self.timeout = timeout

    def search(self, query: str, top_k: int, content_types: set[str]) -> list[RetrievedChunk]:
        payload = json.dumps({
            "query": query,
            "top_k": max(1, min(top_k, 100)),
            "content_types": sorted(content_types),
        }, ensure_ascii=False).encode("utf-8")
        request = urllib_request.Request(
            self.base_url + "/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (OSError, TimeoutError, urllib_error.URLError, json.JSONDecodeError):
            return []
        retrieved = []
        for item in result.get("results", []):
            chunk = self.chunks_by_id.get(str(item.get("chunk_id", "")))
            if chunk is None or chunk.content_type not in content_types:
                continue
            try:
                score = float(item.get("score", 0.0))
            except (TypeError, ValueError):
                continue
            retrieved.append(RetrievedChunk(chunk, score))
        return retrieved


@dataclass(slots=True)
class CatalogAnswer:
    query: str
    answer: str
    chunk_ids: list[str]


def load_chunks(path: Path | str) -> list[Chunk]:
    if isinstance(path, str):
        path = Path(path)
    if not path.is_file() or path.read_text(encoding="utf-8").startswith("version https://git-lfs.github.com/spec/v1"):
        fallback = path.parent.parent / "data-rag" / "chunks.jsonl"
        if fallback.is_file():
            path = fallback

    text = path.read_text(encoding="utf-8")
    chunks = []
    for line in text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        chunks.append(Chunk(
            chunk_id=item["chunk_id"], document_id=item["document_id"], section_id=item["section_id"],
            content_text=item["content_text"], retrieval_text=item["retrieval_text"],
            heading_path=item.get("heading_path", []), token_count=item.get("token_count", 0),
            page_start=item.get("page_start"), is_active=item.get("is_active", True),
            content_type=item.get("content_type", "paragraph"), source_file=item.get("source_file", ""),
            source_line_start=item.get("source_line_start"), source_line_end=item.get("source_line_end"),
            metadata=item.get("metadata", {}),
        ))
    return chunks


def load_catalog(path: Path | str | None) -> list[CatalogAnswer]:
    if path is None:
        return []
    if isinstance(path, str):
        path = Path(path)
    if not path.is_file():
        return []
    source = path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## (?=\d+\.)", source)[1:]
    catalog = []
    for section in sections:
        lines = section.splitlines()
        query = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
        answer_match = re.search(r"(?ms)^\*\*Trả lời:\*\*\s*(.+?)(?=\n\*\*Confidence:)", section)
        if not answer_match:
            continue
        answer = answer_match.group(1).strip()
        chunk_ids = list(dict.fromkeys(re.findall(r"chk_[0-9a-f]{20}", section)))
        catalog.append(CatalogAnswer(query, answer, chunk_ids))
    return catalog


def load_documents(path: Path | str | None) -> list[dict]:
    if path is None:
        return []
    if isinstance(path, str):
        path = Path(path)
    if not path.is_file() or path.read_text(encoding="utf-8").startswith("version https://git-lfs.github.com/spec/v1"):
        fallback = path.parent.parent / "data-rag" / "documents.jsonl"
        if fallback.is_file():
            path = fallback
    if not path.is_file():
        return []
    documents = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            documents.append(json.loads(line))
    return documents


def load_knowledge_manifest(path: Path | None) -> list[dict]:
    if path is None or not path.is_file():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, list) else []


def is_searchable(chunk: Chunk) -> bool:
    value = chunk.content_text.strip()
    folded = fold(re.sub(r"<[^>]+>", " ", value))
    is_running_header = (
        folded.startswith("qt don tiep benh nhan va kham chua benh ngoai tru tai khu tn1 - cs1")
        and "qt.25.01" in value
    )
    return (
        chunk.is_active
        and chunk.token_count >= 5
        and value != "---"
        and not value.startswith("_QT đón tiếp bệnh nhân")
        and not is_running_header
        and "| Trách nhiệm | Các bước thực hiện |" not in value
    )


class RAGApplication:
    def __init__(
        self,
        chunks_path: Path,
        catalog_path: Path | None = None,
        documents_path: Path | None = None,
        knowledge_manifest_path: Path | None = None,
        dense_url: str | None = None,
    ):
        self.knowledge_manifest = load_knowledge_manifest(knowledge_manifest_path)
        published_ids = {
            item.get("document_id") for item in self.knowledge_manifest
            if item.get("status") == "published"
        }
        self.chunks = [
            chunk for chunk in load_chunks(chunks_path)
            if is_searchable(chunk) and (not self.knowledge_manifest or chunk.document_id in published_ids)
        ]
        self.by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        dense_url = dense_url if dense_url is not None else os.getenv("DENSE_RETRIEVAL_URL", "")
        self.dense_client = DenseClient(dense_url, self.by_id) if dense_url else None
        self.legal_chunks = [chunk for chunk in self.chunks if is_legal_document_chunk(chunk)]
        self.legal_index = BM25Index()
        self.legal_index.build(self.legal_chunks)
        self.process_index = BM25Index()
        self.process_index.build([
            chunk for chunk in self.chunks
            if not is_price_chunk(chunk)
        ])
        self.legacy_process_index = BM25Index()
        self.legacy_process_index.build([
            chunk for chunk in self.chunks
            if chunk.document_id == "doc_qt_25_01" and not is_price_chunk(chunk)
        ])
        self.policy_index = BM25Index()
        self.policy_index.build([
            chunk for chunk in self.chunks
            if chunk.content_type in {"bhyt_policy", "bhyt_update_alert"}
        ])
        self.process_vocabulary = set().union(
            *(set(tokenize(fold(chunk.retrieval_text))) for chunk in self.process_index.chunks)
        ) if self.process_index.chunks else set()
        self.process_canonical_vocabulary = set().union(
            *(set(canonical_tokens(chunk.retrieval_text)) for chunk in self.process_index.chunks)
        ) if self.process_index.chunks else set()
        self.price_chunks = [chunk for chunk in self.chunks if is_price_chunk(chunk)]
        self.legacy_price_index = BM25Index()
        self.legacy_price_index.build([
            chunk for chunk in self.chunks if chunk.content_type == "price_service"
        ])
        self.bhyt_price_index = BM25Index()
        self.bhyt_price_index.build([
            chunk for chunk in self.chunks if chunk.content_type == "bhyt_price_service"
        ])
        self.price_terms = {
            chunk.chunk_id: service_evidence_terms(chunk)
            for chunk in self.price_chunks
        }
        self.service_codes = {
            str((chunk.metadata or {}).get("service_code", ""))
            for chunk in self.price_chunks
            if (chunk.metadata or {}).get("service_code")
        }
        self.process_terms = {
            chunk.chunk_id: process_evidence_terms(chunk)
            for chunk in self.process_index.chunks
        }
        self.legal_terms = {
            chunk.chunk_id: process_evidence_terms(chunk)
            for chunk in self.legal_chunks
        }
        self.catalog = load_catalog(catalog_path)
        self.documents = load_documents(documents_path)
        self.sessions: dict[str, dict] = {}
        self.lock = threading.RLock()

    def health(self) -> dict:
        documents = sorted({chunk.document_id for chunk in self.chunks})
        return {
            "status": "ok",
            "service": "heartcare-rag-demo",
            "retriever": "bm25+bge-m3-hybrid" if self.dense_client else "bm25",
            "document_count": len(documents),
            "document_ids": documents,
            "indexed_chunks": len(self.chunks),
            "process_chunks": len(self.process_index.chunks),
            "bhyt_policy_chunks": len(self.policy_index.chunks),
            "legal_document_chunks": len(self.legal_chunks),
            "price_service_chunks": len(self.price_chunks),
            "catalog_answers": len(self.catalog),
            "knowledge_sources": len(self.knowledge_catalog()),
            "evidence_contract": "heartcare.rag.evidence.v1",
        }

    def knowledge_catalog(self) -> list[dict]:
        if self.knowledge_manifest:
            return [
                {
                    **item,
                    "approval_status": item.get("status", "draft"),
                    "content_types": sorted({
                        chunk.content_type
                        for chunk in self.chunks
                        if chunk.document_id == item.get("document_id")
                    }),
                }
                for item in self.knowledge_manifest
                if item.get("status") == "published"
            ]
        if self.documents:
            return [
                {
                    **document,
                    "approval_status": (
                        "published"
                        if document.get("status") in {"active", "reference_only", "published"}
                        else document.get("status", "draft")
                    ),
                    "content_types": sorted({
                        chunk.content_type
                        for chunk in self.chunks
                        if chunk.document_id == document.get("document_id")
                    }),
                }
                for document in self.documents
            ]

        result = []
        for document_id in sorted({chunk.document_id for chunk in self.chunks}):
            chunks = [chunk for chunk in self.chunks if chunk.document_id == document_id]
            first = min(chunks, key=lambda item: (item.source_line_start or 0, item.chunk_id))
            result.append({
                "document_id": document_id,
                "title": first.heading_path[0] if first.heading_path else document_id,
                "source_file": first.source_file,
                "status": "active",
                "approval_status": "published",
                "content_types": sorted({chunk.content_type for chunk in chunks}),
            })
        return result

    def expand_context(self, chunk_id: str, scope: str = "section", limit: int = 20) -> dict:
        anchor = self.by_id.get(chunk_id)
        if anchor is None:
            return {
                "schema_version": "heartcare.rag.context.v1",
                "status": "insufficient",
                "anchor_chunk_id": chunk_id,
                "chunks": [],
                "citations": [],
            }
        scope = scope if scope in {"section", "document"} else "section"
        limit = max(1, min(limit, 50))
        candidates = [
            chunk for chunk in self.chunks
            if chunk.document_id == anchor.document_id
            and (scope == "document" or chunk.section_id == anchor.section_id)
        ]
        candidates.sort(key=lambda item: (item.source_line_start or 0, item.chunk_id))
        if len(candidates) > limit:
            anchor_index = next(
                (index for index, chunk in enumerate(candidates) if chunk.chunk_id == chunk_id),
                0,
            )
            start = max(0, min(anchor_index - limit // 2, len(candidates) - limit))
            candidates = candidates[start:start + limit]
        chunks = [{
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "section_id": chunk.section_id,
            "content_type": chunk.content_type,
            "content_text": chunk.content_text,
            "heading_path": chunk.heading_path,
            "facts": chunk.metadata or {},
            "source_file": chunk.source_file,
            "line_start": chunk.source_line_start,
            "line_end": chunk.source_line_end,
        } for chunk in candidates]
        citations = [{
            "citation_id": f"CTX{index}",
            "chunk_id": chunk.chunk_id,
            "source_file": chunk.source_file,
            "source_uri": f"docs/data_rag/{chunk.source_file}" if chunk.source_file else "",
            "line_start": chunk.source_line_start,
            "line_end": chunk.source_line_end,
            "heading_path": chunk.heading_path,
        } for index, chunk in enumerate(candidates, 1)]
        return {
            "schema_version": "heartcare.rag.context.v1",
            "status": "exact",
            "anchor_chunk_id": chunk_id,
            "scope": scope,
            "chunks": chunks,
            "citations": citations,
        }

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        limit = max(1, min(top_k, 10))
        price_intent = is_price_query(query)
        process_anchor = has_process_knowledge_anchor(query)

        if is_legal_document_query(query):
            legal_lexical = self.legal_index.search(query, max(30, limit))
            legal_dense = self._dense_search(query, max(30, limit), {"bhyt_legal_document"})
            legal_initial = (
                reciprocal_rank_fusion(legal_lexical, legal_dense)
                if legal_dense else legal_lexical
            )
            return self._rerank_process(query, legal_initial)[:limit]

        # BHYT questions about entitlement, procedures, referrals or payment
        # must not be swallowed by the generic word "chi phí" and routed into
        # the 12k-row price catalog. A named service/code still uses price
        # retrieval and can later be paired with policy evidence by the Agent.
        if (
            is_bhyt_policy_query(query)
            and not has_specific_price_service_anchor(query)
            and not has_legacy_process_anchor(query)
        ):
            policy_initial = self.policy_index.search(expand_query(query), max(28, limit))
            dense_policy = self._dense_search(
                query, max(28, limit), {"bhyt_policy", "bhyt_update_alert"},
            )
            if dense_policy:
                policy_ranked = self._rerank_policy(
                    query,
                    reciprocal_rank_fusion(policy_initial, dense_policy),
                )
            else:
                policy_ranked = self._rerank_policy(query, policy_initial)
            if policy_ranked:
                return policy_ranked[:limit]

        # A service lookup does not always contain an explicit price word. Probe
        # BM25 first because it is fast and can retain enough correctly-spelled
        # anchors (for example SPECT/CT) even when another token is misspelled.
        price_probe_size = max(100, limit)
        price_initial = []
        if price_intent or not process_anchor:
            price_lexical = merge_retrieved(
                self.legacy_price_index.search(price_search_text(query), price_probe_size),
                self.bhyt_price_index.search(price_search_text(query), price_probe_size),
            )
            price_dense = self._dense_search(
                query, price_probe_size, {"price_service", "bhyt_price_service"},
            )
            price_initial = (
                reciprocal_rank_fusion(price_lexical, price_dense)
                if price_dense else price_lexical
            )
        price_ranked = self._rerank_prices(query, price_initial)
        if not process_anchor and price_ranked and price_target_coverage(query, price_ranked[0].chunk) >= 0.6:
            return price_ranked[:limit]

        # Explicit catalog questions that BM25 cannot resolve get a bounded
        # fuzzy fallback. Do not continue into the process corpus afterwards.
        if price_intent:
            fuzzy_prices = self._fuzzy_price_search(query, max(100, limit))
            return self._rerank_prices(query, merge_retrieved(price_initial, fuzzy_prices))[:limit]

        selected_process_index = self.legacy_process_index if has_legacy_process_anchor(query) else self.process_index
        process_lexical = selected_process_index.search(expand_query(query), max(50, limit))
        process_types = {"paragraph", "process_table_row"} if has_legacy_process_anchor(query) else {
            "paragraph", "process_table_row", "bhyt_policy", "bhyt_update_alert",
        }
        process_dense = self._dense_search(query, max(50, limit), process_types)
        process_initial = (
            reciprocal_rank_fusion(process_lexical, process_dense)
            if process_dense else process_lexical
        )
        reranked = self._rerank_process(query, process_initial)
        if reranked and process_target_coverage(query, reranked[0].chunk) >= 0.4:
            return reranked[:limit]

        # A short entity-only question such as "Tetrofomin" has no exact BM25
        # anchor. Search the catalog fuzzily before treating it as a process.
        if not process_anchor and len(price_target_terms(query)) <= 4:
            fuzzy_prices = self._fuzzy_price_search(query, max(100, limit))
            price_ranked = self._rerank_prices(query, merge_retrieved(price_initial, fuzzy_prices))
            if price_ranked and price_target_coverage(query, price_ranked[0].chunk) >= 0.6:
                return price_ranked[:limit]

        initial = merge_retrieved(
            process_initial,
            self._fuzzy_process_search(
                query,
                max(50, limit),
                selected_process_index.chunks,
            ),
        )
        return self._rerank_process(query, initial)[:limit]

    def _dense_search(self, query: str, top_k: int, content_types: set[str]) -> list[RetrievedChunk]:
        if self.dense_client is None:
            return []
        return self.dense_client.search(query, top_k, content_types)

    def _rerank_process(self, query: str, retrieved: list[RetrievedChunk]) -> list[RetrievedChunk]:
        reranked = [
            RetrievedChunk(item.chunk, item.score + 10.0 * evidence_coverage(query, item.chunk))
            for item in retrieved
        ]
        return sorted(reranked, key=lambda item: (-item.score, item.chunk.chunk_id))

    def _rerank_policy(self, query: str, retrieved: list[RetrievedChunk]) -> list[RetrievedChunk]:
        # RRF already combines lexical and semantic evidence. A small lexical
        # coverage tie-break avoids letting incidental legal words such as
        # "khoản 8" overwhelm the semantically correct policy chunk.
        reranked = [
            RetrievedChunk(
                item.chunk,
                item.score
                + evidence_coverage(query, item.chunk)
                + 20.0 * policy_question_similarity(query, item.chunk),
            )
            for item in retrieved
        ]
        return sorted(reranked, key=lambda item: (-item.score, item.chunk.chunk_id))

    def _fuzzy_price_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        target = price_target_terms(query)
        if not target:
            return []
        results = []
        for chunk in self.price_chunks:
            coverage, quality = fuzzy_match_stats(target, self.price_terms[chunk.chunk_id])
            if coverage < 0.5 or quality < 0.78:
                continue
            results.append(RetrievedChunk(chunk, 20.0 * coverage + 5.0 * quality))
        return sorted(results, key=lambda item: (-item.score, item.chunk.chunk_id))[:top_k]

    def _fuzzy_process_search(
        self,
        query: str,
        top_k: int,
        chunks: list[Chunk] | None = None,
    ) -> list[RetrievedChunk]:
        target = meaningful_terms(query)
        if not target:
            return []
        results = []
        for chunk in chunks if chunks is not None else self.process_index.chunks:
            coverage, quality = fuzzy_match_stats(target, self.process_terms[chunk.chunk_id])
            matched = round(coverage * len(target))
            if coverage < 0.35 or quality < 0.78 or (len(target) > 1 and matched < 2):
                continue
            results.append(RetrievedChunk(chunk, 15.0 * coverage + 5.0 * quality))
        return sorted(results, key=lambda item: (-item.score, item.chunk.chunk_id))[:top_k]

    def retrieve(self, query: str, top_k: int = 8) -> dict:
        """Return evidence for an external Agent; never generate model prose here."""
        request_id = str(uuid.uuid4())
        route = route_query(query)
        route_decision = {
            "emergency": "emergency",
            "requires_tool": "dynamic_tool",
            "human_handoff": "clinical_handoff",
        }.get(route, "rag_static")
        if route != "rag":
            return evidence_envelope(
                request_id=request_id,
                query=query,
                route_decision=route_decision,
                status="blocked",
                confidence=1.0,
                reason_codes=[route.upper()],
                evidence=[],
                fallback_action="fixed_safety_response" if route == "emergency" else "handoff",
                fallback_message=self.answer(query),
            )

        if has_unsupported_process_site(query):
            return evidence_envelope(
                request_id=request_id, query=query, route_decision="out_of_scope", status="insufficient",
                confidence=0.0, reason_codes=["UNSUPPORTED_PROCESS_SITE"], evidence=[],
                fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
            )

        requested_code = re.search(r"\b\d{2}\.\d{4}\.\d{4}\b", query)
        if requested_code and requested_code.group(0) not in self.service_codes:
            return evidence_envelope(
                request_id=request_id, query=query, route_decision="rag_static", status="insufficient",
                confidence=0.0, reason_codes=["SERVICE_CODE_NOT_FOUND"], evidence=[],
                fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
            )
        requested_legal_token = legal_code_token(query)
        if (
            is_legal_document_query(query)
            and requested_legal_token
            and not legal_document_code_in_query(query, self.legal_chunks)
        ):
            return evidence_envelope(
                request_id=request_id, query=query, route_decision="rag_static", status="insufficient",
                confidence=0.0, reason_codes=["LEGAL_DOCUMENT_CODE_NOT_FOUND"], evidence=[],
                fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
            )

        overview_similarity = process_overview_similarity(query)
        if is_process_overview_query(query):
            overview_chunks = []
            seen_lines = set()
            for chunk in sorted(self.process_index.chunks, key=lambda item: (item.source_line_start or 0, item.chunk_id)):
                metadata = chunk.metadata or {}
                if not metadata.get("process_step"):
                    continue
                key = (chunk.source_line_start, metadata.get("process_step"), metadata.get("process_detail"))
                if key in seen_lines:
                    continue
                seen_lines.add(key)
                overview_chunks.append(RetrievedChunk(chunk, 1.0))
            return self._build_evidence_envelope(
                request_id, query, overview_chunks, "exact", 0.98, ["PROCESS_OVERVIEW_MATCH"]
            )
        if overview_similarity >= MIN_APPROXIMATE_SIMILARITY:
            title_chunk = next(
                (
                    chunk for chunk in self.process_index.chunks
                    if (chunk.metadata or {}).get("document_code") == "QT.25.01"
                    and "QUY TRÌNH" in chunk.content_text.upper()
                ),
                None,
            )
            if title_chunk is not None:
                envelope = self._build_evidence_envelope(
                    request_id, query, [RetrievedChunk(title_chunk, overview_similarity)],
                    "approximate", overview_similarity, ["FUZZY_PROCESS_OVERVIEW_MATCH"],
                )
                envelope["clarification"]["options"] = [{
                    "id": "E1",
                    "rank": 1,
                    "label": PROCESS_OVERVIEW_TITLE,
                    "selection_query": PROCESS_OVERVIEW_TITLE,
                    "similarity": round(overview_similarity, 6),
                    "content_type": "process_overview",
                }]
                return envelope

        retrieved = self.search(query, max(1, min(top_k, 10)))
        if not retrieved:
            return evidence_envelope(
                request_id=request_id, query=query, route_decision="rag_static", status="insufficient",
                confidence=0.0, reason_codes=["NO_RETRIEVAL_MATCH"], evidence=[],
                fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
            )

        top = retrieved[0]
        code_match = requested_code
        is_price = is_price_chunk(top.chunk) or (is_price_query(query) and not is_bhyt_policy_query(query))
        is_legal = is_legal_document_chunk(top.chunk) and is_legal_document_query(query)

        if is_legal:
            requested_legal_code = legal_document_code_in_query(query, self.legal_chunks)
            if requested_legal_code:
                exact_code = [
                    item for item in retrieved
                    if fold(str((item.chunk.metadata or {}).get("document_code", "")))
                    == fold(requested_legal_code)
                ]
                if exact_code:
                    return self._build_evidence_envelope(
                        request_id, query, exact_code[:3], "exact", 1.0,
                        ["EXACT_LEGAL_DOCUMENT_CODE"],
                    )
            exact_coverage = process_exact_coverage(query, top.chunk)
            similarity = process_match_similarity(query, top.chunk)
            if exact_coverage >= 0.70:
                return self._build_evidence_envelope(
                    request_id, query, retrieved[:3], "exact",
                    min(0.96, 0.7 + 0.25 * exact_coverage),
                    ["LEGAL_DOCUMENT_EVIDENCE_COVERED"],
                )
            if similarity >= MIN_APPROXIMATE_SIMILARITY:
                candidates = [
                    item for item in retrieved
                    if process_match_similarity(query, item.chunk) >= MIN_APPROXIMATE_SIMILARITY
                ]
                return self._build_evidence_envelope(
                    request_id, query, candidates[:5], "approximate", similarity,
                    ["PARTIAL_LEGAL_DOCUMENT_MATCH"],
                )
            return evidence_envelope(
                request_id=request_id, query=query, route_decision="rag_static",
                status="insufficient", confidence=exact_coverage,
                reason_codes=["LEGAL_DOCUMENT_NOT_FOUND"], evidence=[],
                fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
            )

        # Dense retrieval always returns a nearest neighbour, even for a query
        # unrelated to the hospital corpus. Do not promote that neighbour into
        # approximate policy/process evidence without a supported domain anchor.
        # Named catalog items remain eligible and are checked by the price
        # matcher below.
        if not is_price and not has_process_knowledge_anchor(query):
            return evidence_envelope(
                request_id=request_id, query=query, route_decision="out_of_scope",
                status="insufficient", confidence=0.0,
                reason_codes=["QUERY_NOT_SUPPORTED_BY_CORPUS"], evidence=[],
                fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
            )

        if is_price and code_match:
            exact_code = [
                item for item in retrieved
                if str((item.chunk.metadata or {}).get("service_code", "")) == code_match.group(0)
            ]
            if not exact_code:
                return evidence_envelope(
                    request_id=request_id, query=query, route_decision="rag_static", status="insufficient",
                    confidence=0.0, reason_codes=["SERVICE_CODE_NOT_FOUND"], evidence=[],
                    fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
                )
            return self._build_evidence_envelope(
                request_id, query, exact_code[:1], "exact", 1.0, ["EXACT_SERVICE_CODE"]
            )

        if is_price:
            coverage = price_target_coverage(query, top.chunk)
            similarity = price_match_similarity(query, top.chunk)
            service_name = fold(str((top.chunk.metadata or {}).get("service_name", "")))
            exact_name = bool(service_name and service_name in fold(query))
            if exact_name:
                return self._build_evidence_envelope(
                    request_id, query, [top], "exact", 0.97, ["EXACT_SERVICE_NAME"]
                )
            if similarity >= MIN_APPROXIMATE_SIMILARITY:
                candidates = [
                    item for item in retrieved
                    if price_match_similarity(query, item.chunk) >= MIN_APPROXIMATE_SIMILARITY
                ]
                return self._build_evidence_envelope(
                    request_id, query, candidates[:5], "approximate", similarity,
                    ["AMBIGUOUS_OR_PARTIAL_SERVICE_MATCH"],
                )
            return evidence_envelope(
                request_id=request_id, query=query, route_decision="rag_static", status="insufficient",
                confidence=coverage, reason_codes=["TARGET_TERM_NOT_IN_PRICE_CORPUS"], evidence=[],
                fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
            )

        coverage = process_target_coverage(query, top.chunk)
        exact_coverage = process_exact_coverage(query, top.chunk)
        similarity = process_match_similarity(query, top.chunk)
        if exact_coverage >= 0.75:
            exact_items = retrieved[:1] if top.chunk.content_type in {"bhyt_policy", "bhyt_update_alert"} else retrieved[:3]
            return self._build_evidence_envelope(
                request_id, query, exact_items, "exact", min(0.96, 0.7 + 0.25 * exact_coverage),
                ["PROCESS_EVIDENCE_COVERED"],
            )
        if similarity >= MIN_APPROXIMATE_SIMILARITY:
            candidates = [
                item for item in retrieved
                if process_match_similarity(query, item.chunk) >= MIN_APPROXIMATE_SIMILARITY
            ]
            return self._build_evidence_envelope(
                request_id, query, candidates[:5], "approximate", similarity,
                ["PARTIAL_PROCESS_MATCH"],
            )
        return evidence_envelope(
            request_id=request_id, query=query, route_decision="out_of_scope", status="insufficient",
            confidence=coverage, reason_codes=["QUERY_NOT_SUPPORTED_BY_CORPUS"], evidence=[],
            fallback_action="abstain", fallback_message=INSUFFICIENT_RAG_MESSAGE,
        )

    def _build_evidence_envelope(
        self,
        request_id: str,
        query: str,
        retrieved: list[RetrievedChunk],
        status: str,
        confidence: float,
        reason_codes: list[str],
    ) -> dict:
        evidence = []
        citations = []
        for rank, item in enumerate(retrieved, 1):
            chunk = item.chunk
            metadata = chunk.metadata or {}
            evidence_id = f"E{rank}"
            citation_id = f"C{rank}"
            coverage = (
                price_target_coverage(query, chunk)
                if is_price_chunk(chunk)
                else process_target_coverage(query, chunk)
            )
            similarity = (
                price_match_similarity(query, chunk)
                if is_price_chunk(chunk)
                else process_match_similarity(query, chunk)
            )
            evidence.append({
                "evidence_id": evidence_id,
                "rank": rank,
                "match_type": "exact" if status == "exact" else "related_candidate",
                "scores": {
                    "retrieval_raw": round(item.score, 6),
                    "target_coverage": round(coverage, 6),
                    "match_similarity": round(similarity, 6),
                },
                "chunk": {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "content_type": chunk.content_type,
                    "content_text": chunk.content_text,
                    "heading_path": chunk.heading_path,
                    "facts": metadata,
                },
                "citation_id": citation_id,
            })
            citations.append({
                "citation_id": citation_id,
                "chunk_id": chunk.chunk_id,
                "source_file": chunk.source_file,
                "source_uri": f"docs/data_rag/{chunk.source_file}" if chunk.source_file else "",
                "line_start": chunk.source_line_start,
                "line_end": chunk.source_line_end,
                "page_start": chunk.page_start,
                "heading_path": chunk.heading_path,
                "legal_basis": metadata.get("legal_basis"),
            })
        envelope = evidence_envelope(
            request_id=request_id, query=query, route_decision="rag_static", status=status,
            confidence=confidence, reason_codes=reason_codes, evidence=evidence,
            fallback_action="ask_clarification" if status == "approximate" else "none",
            fallback_message=(
                "Anh/chị vui lòng xác nhận biến thể hoặc phạm vi thông tin cụ thể hơn."
                if status == "approximate" else ""
            ),
        )
        envelope["citations"] = citations
        if status == "approximate":
            envelope["clarification"]["options"] = build_clarification_options(evidence)
        return envelope

    def answer(self, query: str) -> str:
        route = route_query(query)
        if route == "emergency":
            return (
                "**Đây có thể là dấu hiệu cấp cứu.**\n\n"
                "- Gọi cấp cứu **115**, hoặc đến cơ sở cấp cứu gần nhất ngay lập tức.\n"
                "- Không chờ phản hồi từ chatbot và không tự điều trị dựa trên nội dung trực tuyến.\n\n"
                "Tôi không thể chẩn đoán hoặc tư vấn điều trị cho tình trạng này."
            )
        if route == "requires_tool":
            return (
                "Câu hỏi này cần dữ liệu vận hành hoặc dữ liệu cá nhân tại thời điểm hiện tại. "
                "Tài liệu RAG tĩnh không đủ để trả lời chính xác; anh/chị vui lòng dùng kênh chính thức "
                "của bệnh viện hoặc liên hệ nhân viên hỗ trợ."
            )
        if route == "human_handoff":
            return (
                "Câu hỏi này cần nhân viên y tế trực tiếp đánh giá. Tôi không thể chẩn đoán, kê đơn "
                "hoặc thay đổi điều trị. Anh/chị vui lòng liên hệ bệnh viện hoặc bác sĩ phụ trách."
            )

        if is_process_overview_query(query):
            overview = self._process_overview_answer()
            if overview:
                return overview

        if (
            is_legal_document_query(query)
            and legal_code_token(query)
            and not legal_document_code_in_query(query, self.legal_chunks)
        ):
            return INSUFFICIENT_RAG_MESSAGE

        retrieved = self.search(query, 5)
        catalog_answer = self._match_catalog(query, retrieved)
        if catalog_answer:
            valid_chunks = [self.by_id[chunk_id] for chunk_id in catalog_answer.chunk_ids if chunk_id in self.by_id]
            if valid_chunks:
                return catalog_answer.answer + "\n\n" + self._citations(valid_chunks)

        if retrieved and is_price_chunk(retrieved[0].chunk):
            if retrieved[0].chunk.content_type == "bhyt_price_service":
                return self._bhyt_price_answer(query, retrieved)
            return self._price_answer(query, retrieved)

        if retrieved and is_legal_document_chunk(retrieved[0].chunk) and is_legal_document_query(query):
            requested_code = legal_document_code_in_query(query, self.legal_chunks)
            evidence = [
                item.chunk for item in retrieved
                if not requested_code
                or fold(str((item.chunk.metadata or {}).get("document_code", ""))) == fold(requested_code)
            ][:3]
            if evidence:
                excerpts = [clean_excerpt(chunk.content_text) for chunk in evidence]
                return "**Thông tin văn bản trong kho dữ liệu:**\n\n" + "\n\n".join(excerpts) + "\n\n" + self._citations(evidence)

        # Non-price prose needs a hospital/BHYT/process domain anchor. Purely
        # lexical collisions such as "tổng thống Mỹ" must not be accepted just
        # because the larger policy corpus also contains words like "tổng".
        if not has_process_knowledge_anchor(query):
            return INSUFFICIENT_RAG_MESSAGE

        weak_ambiguous_process_match = (
            not is_price_query(query)
            and len(retrieved) > 1
            and retrieved[0].score < 6.0
            and retrieved[1].score > retrieved[0].score * 0.6
        )
        process_terms, process_vocabulary = scope_terms(query), self.process_vocabulary
        if has_vietnamese_diacritics(query):
            process_vocabulary = self.process_canonical_vocabulary
        process_vocabulary_coverage = (
            len(process_terms & process_vocabulary) / len(process_terms)
            if process_terms and not is_price_query(query) else 1.0
        )
        if (
            not retrieved
            or retrieved[0].score < 0.5
            or evidence_coverage(query, retrieved[0].chunk) < 0.45
            or weak_ambiguous_process_match
            or process_vocabulary_coverage < 0.75
        ):
            return (
                INSUFFICIENT_RAG_MESSAGE
            )
        evidence = [item.chunk for item in retrieved[:2]]
        excerpts = []
        for chunk in evidence:
            text = clean_excerpt(chunk.content_text)
            excerpts.append(text[:700] + ("…" if len(text) > 700 else ""))
        return "**Thông tin tìm thấy trong quy trình:**\n\n" + "\n\n".join(excerpts) + "\n\n" + self._citations(evidence)

    def _process_overview_answer(self) -> str | None:
        grouped: dict[str, dict] = {}
        process_chunks = sorted(
            (chunk for chunk in self.chunks if chunk.document_id == "doc_qt_25_01"),
            key=lambda chunk: (chunk.source_line_start or 0, chunk.chunk_id),
        )
        for chunk in process_chunks:
            metadata = chunk.metadata or {}
            step = str(metadata.get("process_step", "")).strip()
            detail = str(metadata.get("process_detail", "")).strip()
            if not step:
                continue
            item = grouped.setdefault(step, {
                "first_line": chunk.source_line_start or 0,
                "role": str(metadata.get("process_role", "")).strip(),
                "details": [],
                "detail_keys": set(),
                "chunks": [],
            })
            detail_key = (chunk.source_line_start, detail)
            if detail and detail_key not in item["detail_keys"]:
                item["detail_keys"].add(detail_key)
                item["details"].append(detail)
            if all(existing.chunk_id != chunk.chunk_id for existing in item["chunks"]):
                item["chunks"].append(chunk)

        if not grouped:
            return None

        ordered = sorted(grouped.items(), key=lambda pair: pair[1]["first_line"])
        lines = [
            "**Quy trình đón tiếp và khám chữa bệnh ngoại trú tại Khu Tự nguyện 1 – Cơ sở 1:**",
            "",
        ]
        citation_candidates = []
        for index, (step, item) in enumerate(ordered, 1):
            details = " ".join(compact_process_detail(detail, 300) for detail in item["details"])
            details = truncate_at_word(details, 560)
            role = item["role"]
            lines.append(f"{index}. **{step}**")
            if role:
                lines.append(f"   Phụ trách: {role}.")
            if details:
                lines.append(f"   {details}")
            citation_candidates.extend(item["chunks"])
            lines.append("")

        citations_by_page = []
        seen_pages = set()
        for chunk in citation_candidates:
            page = chunk.page_start
            if page not in seen_pages:
                seen_pages.add(page)
                citations_by_page.append(chunk)
        lines.append(self._citations(citations_by_page))
        return "\n".join(lines).strip()

    def _rerank_prices(self, query: str, retrieved: list[RetrievedChunk]) -> list[RetrievedChunk]:
        query_folded = fold(query)
        wants_bhyt_reference = has_bhyt_marker(query)
        code_match = re.search(r"\b\d{2}\.\d{4}\.\d{4}\b", query)
        query_terms = price_target_terms(query)
        if code_match:
            exact = [item for item in retrieved if (item.chunk.metadata or {}).get("service_code") == code_match.group(0)]
            if exact:
                exact.sort(key=lambda item: (
                    (item.chunk.content_type == "bhyt_price_service") != wants_bhyt_reference,
                    -item.score,
                    item.chunk.chunk_id,
                ))
                return exact + [item for item in retrieved if item not in exact]

        def score(item: RetrievedChunk) -> tuple[float, float, str]:
            metadata = item.chunk.metadata or {}
            name = fold(str(metadata.get("service_name", "")))
            name_terms = set(tokenize(name))
            recall, match_quality = fuzzy_match_stats(query_terms, name_terms)
            overlap = round(recall * len(query_terms))
            precision = overlap / max(1, len(name_terms))
            exact_phrase = 1.0 if name and name in query_folded else 0.0
            source_preference = (
                4.0 if (item.chunk.content_type == "bhyt_price_service") == wants_bhyt_reference else 0.0
            )
            combined = 2.5 * exact_phrase + 2.0 * recall + precision + match_quality + source_preference + 0.03 * item.score
            return (-combined, -item.score, item.chunk.chunk_id)

        return sorted(retrieved, key=score)

    def _price_answer(self, query: str, retrieved: list[RetrievedChunk]) -> str:
        first = retrieved[0].chunk
        first_name = fold(str((first.metadata or {}).get("service_name", "")))
        query_folded = fold(query)
        code_match = re.search(r"\b\d{2}\.\d{4}\.\d{4}\b", query)
        decisive = len(retrieved) == 1 or retrieved[0].score >= retrieved[1].score * 1.6
        code_is_exact = bool(code_match) and (first.metadata or {}).get("service_code") == code_match.group(0)
        if code_match and not code_is_exact:
            return INSUFFICIENT_RAG_MESSAGE
        if price_target_coverage(query, first) < 0.35:
            return INSUFFICIENT_RAG_MESSAGE
        exact = code_is_exact or (first_name and first_name in query_folded) or decisive
        evidence = [first] if exact else [item.chunk for item in retrieved[:3]]
        lines = ["**Giá tham khảo trong bảng giá được cung cấp:**"]
        if not exact:
            lines.insert(0, APPROXIMATE_DISCLOSURE)
            lines.append("Câu hỏi chưa chỉ rõ biến thể kỹ thuật; dưới đây là các kết quả gần nhất:")
        for chunk in evidence:
            metadata = chunk.metadata or {}
            code = metadata.get("service_code") or "không có mã"
            facility_1 = format_price(metadata.get("facility_1_price"))
            facility_2 = format_price(metadata.get("facility_2_price"))
            lines.append(
                f"- **{metadata.get('service_name', 'Dịch vụ')}** (mã {code}): "
                f"Cơ sở 1 **{facility_1}**; Cơ sở 2 **{facility_2}**."
            )
            if metadata.get("note"):
                lines.append(f"  Ghi chú: {metadata['note']}")
        lines.append(
            "\nBảng giá là tài liệu tham khảo theo Nghị quyết 45/2024; nếu cần giá đang áp dụng tại thời điểm khám, "
            "anh/chị nên xác nhận với kênh chính thức của bệnh viện."
        )
        return "\n".join(lines) + "\n\n" + self._citations(evidence)

    def _bhyt_price_answer(self, query: str, retrieved: list[RetrievedChunk]) -> str:
        first = retrieved[0].chunk
        metadata = first.metadata or {}
        code_match = re.search(r"\b\d{2}\.\d{4}\.\d{4}\b", query)
        service_name = fold(str(metadata.get("service_name", "")))
        exact = bool(code_match and metadata.get("service_code") == code_match.group(0)) or (
            bool(service_name) and service_name in fold(query)
        )
        evidence = [first] if exact else [item.chunk for item in retrieved[:3]]
        lines = ["**Mức giá tham chiếu trong biểu giá kỹ thuật của Hà Nội:**"]
        if not exact:
            lines.insert(0, APPROXIMATE_DISCLOSURE)
        for chunk in evidence:
            facts = chunk.metadata or {}
            price = format_vnd(facts.get("price_vnd"))
            code = facts.get("service_code") or "không có mã tương đương"
            lines.append(f"- **{facts.get('service_name', 'Dịch vụ')}** (mã {code}): **{price} đồng**.")
            if facts.get("coverage_category"):
                lines.append(f"  Phân loại: {facts['coverage_category']}")
            if facts.get("price_note"):
                lines.append(f"  Ghi chú giá: {facts['price_note']}")
        lines.append(
            "\n**Lưu ý bắt buộc:** Đây là biểu giá áp dụng cho cơ sở khám chữa bệnh Nhà nước thuộc Hà Nội, "
            "không tự động xác nhận Bệnh viện Tim Hà Nội đang cung cấp kỹ thuật. Mức giá không phải tổng hóa đơn "
            "hoặc số tiền BHYT/người bệnh chắc chắn thanh toán; cần đối chiếu chỉ định, phạm vi hưởng, thủ tục, "
            "thuốc/vật tư thực dùng và xác nhận của bệnh viện."
        )
        return "\n".join(lines) + "\n\n" + self._citations(evidence)

    def _match_catalog(self, query: str, retrieved: list[RetrievedChunk]) -> CatalogAnswer | None:
        query_terms = set(tokenize(query))
        ranks = {item.chunk.chunk_id: rank for rank, item in enumerate(retrieved, 1)}
        best: CatalogAnswer | None = None
        best_score = 0.0
        for item in self.catalog:
            reference_terms = set(tokenize(item.query))
            lexical = len(query_terms & reference_terms) / max(1, len(query_terms | reference_terms))
            evidence = max((1 / ranks[chunk_id] for chunk_id in item.chunk_ids if chunk_id in ranks), default=0.0)
            score = 0.65 * lexical + 0.35 * evidence
            if score > best_score:
                best, best_score = item, score
        return best if best_score >= 0.22 else None

    @staticmethod
    def _citations(chunks: list[Chunk]) -> str:
        seen = set()
        lines = ["**Nguồn:**"]
        for chunk in chunks:
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            section = " › ".join(chunk.heading_path[-2:])
            source = chunk.source_file or ("QT.25.01" if chunk.document_id == "doc_qt_25_01" else chunk.document_id)
            if chunk.page_start:
                location = f"trang {chunk.page_start}"
            elif chunk.source_line_start:
                end = chunk.source_line_end or chunk.source_line_start
                location = f"dòng {chunk.source_line_start}" + (f"–{end}" if end != chunk.source_line_start else "")
            else:
                location = "không có số trang"
            lines.append(f"- {source}, {location}, {section} — `{chunk.chunk_id}`")
        return "\n".join(lines)

    def create_session(self, owner_id: str = "test-client") -> str:
        session_id = str(uuid.uuid4())
        with self.lock:
            self.sessions[session_id] = {"ID": session_id, "Title": "", "OwnerID": owner_id, "Context": {"Messages": [], "Tools": []}}
        return session_id

    def list_sessions(self, owner_id: str = "test-client") -> list[dict]:
        with self.lock:
            return [{"id": value["ID"], "owner_id": owner_id, "title": value["Title"]}
                    for value in self.sessions.values() if value["OwnerID"] == owner_id]

    def get_session(self, session_id: str, owner_id: str = "test-client") -> dict | None:
        with self.lock:
            session = self.sessions.get(session_id)
            return session if session and session["OwnerID"] == owner_id else None

    def delete_session(self, session_id: str, owner_id: str = "test-client") -> bool:
        with self.lock:
            session = self.sessions.get(session_id)
            if not session or session["OwnerID"] != owner_id:
                return False
            del self.sessions[session_id]
            return True

    def post_message(self, session_id: str, message: str, owner_id: str = "test-client") -> str | None:
        with self.lock:
            session = self.sessions.get(session_id)
            if session is None or session["OwnerID"] != owner_id:
                return None
            session["Context"]["Messages"].append({"Role": "User", "Content": message})
        response = self.answer(message)
        with self.lock:
            session = self.sessions[session_id]
            session["Context"]["Messages"].append({"Role": "Assistant", "Content": response})
            if not session["Title"]:
                session["Title"] = message[:60]
        return response


def clean_excerpt(text: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    value = re.sub(r"\*\*|__|_", "", value)
    if value.lstrip().startswith("|"):
        cells = [cell.strip() for cell in value.strip().strip("|").split("|")]
        value = " — ".join(cell for cell in cells if cell and not set(cell) <= {"-", ":"})
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def fold(text: str) -> str:
    value = "".join(char for char in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(char) != "Mn")
    return value.replace("đ", "d")


STOPWORDS = {
    "a", "anh", "bao", "bi", "cac", "chi", "cho", "co", "cua", "duoc", "gi", "hay", "la", "lam",
    "luc", "minh", "mot", "nao", "nay", "neu", "nhieu", "nhung", "o", "toi", "trong", "tu", "va", "voi",
    "xin", "tai", "the", "thi", "ve", "dau", "can", "phai", "noi", "thong", "tin", "benh", "vien",
    "ha", "noi", "ai", "bang", "bat", "chua", "den", "dung", "khi", "khong", "mang", "sau", "thay",
    "khoan",
}
PRICE_INTENT_TERMS = ("gia", "chi phi", "vien phi", "bao nhieu tien", "muc thu", "bao nhieu")


def meaningful_terms(text: str) -> set[str]:
    return {term for term in tokenize(fold(text)) if len(term) > 1 and term not in STOPWORDS}


def has_vietnamese_diacritics(text: str) -> bool:
    return "đ" in text.lower() or any(unicodedata.combining(char) for char in unicodedata.normalize("NFD", text))


def scope_terms(text: str) -> set[str]:
    terms = canonical_tokens(text) if has_vietnamese_diacritics(text) else canonical_tokens(fold(text))
    return {term for term in terms if len(term) > 1 and fold(term) not in STOPWORDS}


def format_price(value: object) -> str:
    return f"{value} đồng" if value else "không niêm yết"


def format_vnd(value: object) -> str:
    if value is None or value == "":
        return "không có dữ liệu"
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value).strip()


def is_price_chunk(chunk: Chunk) -> bool:
    return chunk.content_type in {"price_service", "bhyt_price_service"}


def is_legal_document_chunk(chunk: Chunk) -> bool:
    if chunk.content_type in {"bhyt_legal_document", "bhyt_policy", "bhyt_update_alert"}:
        return True
    text = chunk.content_text
    return "Nghị quyết" in text or "Thông tư" in text or "Nghị định" in text or "Luật" in text or "Công văn" in text


def is_legal_document_query(query: str) -> bool:
    value = fold(query)
    if legal_code_token(query):
        return True
    document_cues = (
        "van ban", "cong van", "thong tu", "nghi dinh", "nghi quyet", "luat", "quyet dinh",
    )
    return any(cue in value for cue in document_cues)


def legal_code_token(query: str) -> str:
    match = re.search(r"\b\d{1,3}/\d{4}/[a-z0-9-]+\b", fold(query))
    return match.group(0) if match else ""


def legal_document_code_in_query(query: str, chunks: list[Chunk]) -> str:
    query_value = fold(query)
    matches = {
        str((chunk.metadata or {}).get("document_code", "")).strip()
        for chunk in chunks
        if (chunk.metadata or {}).get("document_code")
        and fold(str((chunk.metadata or {}).get("document_code", ""))) in query_value
    }
    return sorted(matches, key=lambda value: (-len(value), value))[0] if matches else ""


def price_target_terms(query: str) -> set[str]:
    generic = {
        "gia", "chi", "phi", "dich", "vu", "tien", "muc", "thu", "bao", "nhieu",
        "tai", "co", "so", "ma", "tham", "khao", "hien", "nay", "muon",
        "thong", "tin", "cu", "the", "noi", "dung", "su", "tra", "hoi",
        "bhyt", "bao", "hiem", "y", "te", "ha", "noi",
    }
    return meaningful_terms(query) - generic


def service_evidence_terms(chunk: Chunk) -> set[str]:
    metadata = chunk.metadata or {}
    return set(tokenize(fold(
        f"{metadata.get('service_code', '')} {metadata.get('service_name', '')} "
        f"{metadata.get('category', '')} {metadata.get('coverage_category', '')} {metadata.get('title', '')}"
    )))


def process_evidence_terms(chunk: Chunk) -> set[str]:
    metadata = chunk.metadata or {}
    evidence_text = " ".join((
        chunk.content_text,
        str(metadata.get("title", "")),
        " ".join(str(value) for value in metadata.get("question_variants", [])),
        " ".join(str(value) for value in metadata.get("keywords", [])),
        str(metadata.get("topic", "")),
        str(metadata.get("process_step", "")),
        str(metadata.get("process_role", "")),
        str(metadata.get("process_detail", "")),
    ))
    return set(tokenize(fold(evidence_text)))


def policy_question_similarity(query: str, chunk: Chunk) -> float:
    variants = (chunk.metadata or {}).get("question_variants", [])
    query_value = fold(query).strip(" ?.!")
    if not query_value or not isinstance(variants, list):
        return 0.0
    return max(
        (
            difflib.SequenceMatcher(None, query_value, fold(str(variant)).strip(" ?.!")).ratio()
            for variant in variants
            if str(variant).strip()
        ),
        default=0.0,
    )


@lru_cache(maxsize=200_000)
def fuzzy_term_similarity(left: str, right: str) -> float:
    left, right = fold(left), fold(right)
    if left == right:
        return 1.0
    shortest, longest = min(len(left), len(right)), max(len(left), len(right))
    if shortest <= 2:
        return 0.0
    if longest - shortest > max(2, math.ceil(longest * 0.3)):
        return 0.0
    ratio = difflib.SequenceMatcher(None, left, right).ratio()
    threshold = 0.84 if longest <= 5 else 0.78
    return ratio if ratio >= threshold else 0.0


def fuzzy_match_stats(target: set[str], evidence: set[str]) -> tuple[float, float]:
    if not target or not evidence:
        return 0.0, 0.0
    similarities = [
        max((fuzzy_term_similarity(term, candidate) for candidate in evidence), default=0.0)
        for term in target
    ]
    matched = [score for score in similarities if score > 0.0]
    return len(matched) / len(target), (sum(matched) / len(matched) if matched else 0.0)


def exact_term_coverage(target: set[str], evidence: set[str]) -> float:
    if not target:
        return 0.0
    return len(target & evidence) / len(target)


def price_target_coverage(query: str, chunk: Chunk) -> float:
    target = price_target_terms(query)
    if not target:
        return 0.0
    coverage, _ = fuzzy_match_stats(target, service_evidence_terms(chunk))
    return coverage


def price_match_similarity(query: str, chunk: Chunk) -> float:
    coverage, quality = fuzzy_match_stats(price_target_terms(query), service_evidence_terms(chunk))
    return coverage * quality


def price_search_text(query: str) -> str:
    """Remove conversational/price boilerplate before catalog BM25 lookup."""
    target = price_target_terms(query)
    code_match = re.search(r"\b\d{2}\.\d{4}\.\d{4}\b", query)
    parts = sorted(target)
    if code_match:
        parts.append(code_match.group(0))
    return " ".join(parts) or query


def process_target_coverage(query: str, chunk: Chunk) -> float:
    target = meaningful_terms(query)
    if not target:
        return 0.0
    coverage, _ = fuzzy_match_stats(target, process_evidence_terms(chunk))
    return coverage


def process_exact_coverage(query: str, chunk: Chunk) -> float:
    return exact_term_coverage(meaningful_terms(query), process_evidence_terms(chunk))


def process_match_similarity(query: str, chunk: Chunk) -> float:
    coverage, quality = fuzzy_match_stats(meaningful_terms(query), process_evidence_terms(chunk))
    return coverage * quality


def merge_retrieved(*groups: list[RetrievedChunk]) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}
    for group in groups:
        for item in group:
            current = merged.get(item.chunk.chunk_id)
            if current is None or item.score > current.score:
                merged[item.chunk.chunk_id] = item
    return sorted(merged.values(), key=lambda item: (-item.score, item.chunk.chunk_id))


def reciprocal_rank_fusion(
    *groups: list[RetrievedChunk],
    rank_constant: float = 20.0,
) -> list[RetrievedChunk]:
    fused: dict[str, tuple[Chunk, float]] = {}
    for group in groups:
        for rank, item in enumerate(group, 1):
            current_chunk, current_score = fused.get(item.chunk.chunk_id, (item.chunk, 0.0))
            fused[item.chunk.chunk_id] = (current_chunk, current_score + 100.0 / (rank_constant + rank))
    return sorted(
        (RetrievedChunk(chunk, score) for chunk, score in fused.values()),
        key=lambda item: (-item.score, item.chunk.chunk_id),
    )


def build_clarification_options(evidence: list[dict], top_k: int = 5) -> list[dict]:
    options = []
    seen = set()
    for item in evidence:
        chunk = item.get("chunk", {})
        facts = chunk.get("facts") or {}
        content_type = str(chunk.get("content_type", ""))
        if content_type in {"price_service", "bhyt_price_service"}:
            name = str(facts.get("service_name", "")).strip() or "Dịch vụ trong bảng giá"
            code = str(facts.get("service_code", "")).strip()
            label = f"{name} (Mã {code})" if code else name
            source_scope = " theo BHYT" if content_type == "bhyt_price_service" else ""
            selection_query = (
                f"Tra cứu chính xác{source_scope} dịch vụ mã {code}: {name}"
                if code else f"Tra cứu chính xác{source_scope}: {name}"
            )
        elif content_type == "bhyt_legal_document":
            code = str(facts.get("document_code", "")).strip()
            title = str(facts.get("title", "")).strip() or "Văn bản pháp lý"
            label = f"{code} — {title}" if code else title
            selection_query = f'Tra cứu chính xác văn bản {code}: "{title}"' if code else f'Tra cứu chính xác văn bản: "{title}"'
        else:
            step = str(facts.get("process_step", "")).strip()
            heading = " › ".join(chunk.get("heading_path") or [])
            label = step or heading or truncate_at_word(str(chunk.get("content_text", "")), 140)
            selection_query = f'Tra cứu chính xác nội dung quy trình: "{label}"'
        key = fold(label)
        if not label or key in seen:
            continue
        seen.add(key)
        options.append({
            "id": str(item.get("evidence_id", "")),
            "rank": len(options) + 1,
            "label": label,
            "selection_query": selection_query,
            "similarity": round(float((item.get("scores") or {}).get("match_similarity", 0.0)), 6),
            "content_type": content_type,
        })
        if len(options) >= top_k:
            break
    return options


def evidence_envelope(
    *,
    request_id: str,
    query: str,
    route_decision: str,
    status: str,
    confidence: float,
    reason_codes: list[str],
    evidence: list[dict],
    fallback_action: str,
    fallback_message: str,
) -> dict:
    approximate = status == "approximate"
    return {
        "schema_version": "heartcare.rag.evidence.v1",
        "request_id": request_id,
        "query": {"original": query, "normalized": fold(query)},
        "route": {
            "decision": route_decision,
            "safety_action": "block" if status == "blocked" else "allow",
            "reason_codes": reason_codes if status == "blocked" else [],
        },
        "answerability": {
            "status": status,
            "confidence": {
                "score": round(max(0.0, min(confidence, 1.0)), 6),
                "level": "high" if confidence >= 0.85 else "medium" if confidence >= 0.55 else "low",
                "method": "rule-calibrated-v1",
                "reason_codes": reason_codes,
            },
        },
        "generation_policy": {
            "mode": (
                "clarify_selection" if status == "approximate"
                else "grounded_synthesis" if status == "exact"
                else "abstain"
            ),
            "must_use_only_evidence": True,
            "must_cite": status in {"exact", "approximate"},
            "allowed_evidence_ids": [item["evidence_id"] for item in evidence],
            "disclosure": {
                "required": approximate,
                "position": "prefix",
                "text": APPROXIMATE_DISCLOSURE if approximate else "",
            },
            "forbidden_claims": [
                "unsupported_numbers", "unsupported_medical_advice", "claiming_approximate_is_exact",
            ],
        },
        "clarification": {
            "required": approximate,
            "prompt": APPROXIMATE_DISCLOSURE if approximate else "",
            "top_k": 5,
            "options": [],
        },
        "evidence": evidence,
        "citations": [],
        "fallback": {"action": fallback_action, "message": fallback_message},
    }


def truncate_at_word(text: str, max_chars: int) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    if len(value) <= max_chars:
        return value
    shortened = value[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return shortened + "…"


def compact_process_detail(text: str, max_chars: int) -> str:
    value = clean_excerpt(text)
    parts = []
    for raw_part in value.splitlines():
        part = re.sub(r"^[\s+*⇒↓-]+", "", raw_part).strip()
        if part and part not in parts:
            parts.append(part)
    return truncate_at_word(" ".join(parts), max_chars)


def is_process_overview_query(query: str) -> bool:
    value = fold(query)
    full_title_match = (
        "quy trinh" in value
        and "don tiep benh nhan" in value
        and ("ngoai tru" in value or "tn1" in value or "tu nguyen 1" in value)
    )
    # A user does not need to reproduce the administrative document title
    # word-for-word when the requested process and both site identifiers are
    # already unambiguous. Keep misspellings on the approximate/confirmation
    # path by requiring the correctly-spelled process cues here.
    unambiguous_short_title = (
        "quy trinh" in value
        and "kham" in value
        and "ngoai tru" in value
        and ("tn1" in value or "tu nguyen 1" in value)
        and ("cs1" in value or "co so 1" in value)
    )
    return full_title_match or unambiguous_short_title


def process_overview_similarity(query: str) -> float:
    """Match a misspelled process title without accepting a different site."""
    value = fold(query)
    requested_tn = set(re.findall(r"\btn\s*(\d+)\b", value))
    requested_cs = set(re.findall(r"\bcs\s*(\d+)\b", value))
    if (requested_tn and requested_tn != {"1"}) or (requested_cs and requested_cs != {"1"}):
        return 0.0
    target = meaningful_terms(query)
    reference = meaningful_terms(PROCESS_OVERVIEW_TITLE)
    if not target or not ({"tn1", "cs1"} & target or "tu nguyen" in value):
        return 0.0
    coverage, quality = fuzzy_match_stats(target, reference)
    return coverage * quality


def has_unsupported_process_site(query: str) -> bool:
    value = fold(query)
    process_cue = any(term in value for term in ("quy trinh", "quy trih", "ngoai tru", "don tiep", "kham"))
    if not process_cue:
        return False
    requested_tn = set(re.findall(r"\btn\s*(\d+)\b", value))
    requested_cs = set(re.findall(r"\bcs\s*(\d+)\b", value))
    return bool((requested_tn and requested_tn != {"1"}) or (requested_cs and requested_cs != {"1"}))


def is_price_query(query: str) -> bool:
    value = fold(query)
    return any(re.search(rf"\b{re.escape(term)}\b", value) for term in PRICE_INTENT_TERMS) or bool(
        re.search(r"\b\d{2}\.\d{4}\.\d{4}\b", query)
    )


def has_process_knowledge_anchor(query: str) -> bool:
    value = fold(query)
    return any(term in value for term in (
        "bhyt", "bao hiem y te", "the bao hiem", "vss id", "cccd",
        "quy trinh", "thu tuc", "don tiep", "tai kham", "lay so", "dat lich",
        "dau hieu sinh ton", "dhst", "huyet ap", "chieu cao", "can nang",
        "quyen loi", "muc huong", "dong chi tra", "chi tra", "thanh toan",
        "5 nam lien tuc", "chuyen tuyen", "trai tuyen", "thong tuyen", "dung tuyen",
        "giay to", "ho so", "cap cuu", "hen kham lai", "tam tru", "luu tru",
        "chuyen vien", "bhxh", "bang gia", "cap chuyen sau",
    ))


def has_legacy_process_anchor(query: str) -> bool:
    """Prefer QT.25.01 when the question explicitly targets its workflow."""
    value = fold(query)
    return any(term in value for term in (
        "bhyt giay",
        "the bao hiem giay",
        "vss id",
        "cccd gan chip",
        "tn1",
        "tu nguyen 1",
        "cs1",
        "don tiep",
        "lay so",
        "dat lich",
        "dau hieu sinh ton",
        "dhst",
    ))


def is_bhyt_policy_query(query: str) -> bool:
    value = fold(query)
    has_bhyt_context = any(marker in value for marker in (
        "bhyt", "bao hiem y te", "the bao hiem", "bhxh",
    ))
    has_hospital_context = "benh vien tim ha noi" in value
    if not has_bhyt_context and not has_hospital_context:
        return False
    return any(marker in value for marker in (
        "muc huong", "quyen loi", "chi tra", "thanh toan", "dong chi tra",
        "trai tuyen", "thong tuyen", "dung tuyen", "chuyen tuyen", "chuyen co so",
        "giay to", "thu tuc", "ho so", "5 nam", "nam nam", "cap cuu",
        "tam tru", "luu tru", "hen kham lai", "tu mua", "ngoai pham vi",
        "dich vu theo yeu cau", "dang ky ban dau", "benh hiem", "benh dac biet",
        "chi phi thap", "luong co so", "duoc huong", "phan tram", "the bhyt",
        "100%", "95%", "80%",
        "cap nao", "cap chuyen sau", "bang gia", "hieu luc",
    ))


def has_bhyt_marker(query: str) -> bool:
    value = fold(query)
    return any(marker in value for marker in ("bhyt", "bao hiem y te", "the bao hiem"))


def has_specific_price_service_anchor(query: str) -> bool:
    if re.search(r"\b\d{2}\.\d{4}\.\d{4}\b", query):
        return True
    policy_terms = {
        "bhyt", "huong", "quyen", "loi", "chi", "tra", "thanh", "toan",
        "dong", "trai", "tuyen", "dung", "thong", "thu", "tuc", "giay",
        "ho", "so", "nam", "cap", "cuu", "phan", "tram", "thap", "luong",
    }
    return len(price_target_terms(query) - policy_terms) >= 2


def expand_query(query: str) -> str:
    value = fold(query)
    additions = []
    if "chua dat lich" in value or "khong dat lich" in value:
        additions.append("không đặt lịch lấy số trực tiếp cây lấy số tự động")
    if "bhyt giay" in value or "the bao hiem giay" in value:
        additions.append("Vss ID CCCD gắn chíp tích hợp thẻ BHYT thay thế thẻ giấy")
    if "dau hieu sinh ton" in value:
        additions.append("đo huyết áp chiều cao cân nặng DHST")
    return " ".join([query, *additions])


def evidence_coverage(query: str, chunk: Chunk) -> float:
    query_terms = meaningful_terms(query)
    if is_price_query(query):
        query_terms -= {"gia", "chi", "phi", "tien", "muc", "thu", "so", "1", "2"}
    if not query_terms:
        return 0.0
    evidence_terms = set(tokenize(fold(chunk.retrieval_text)))
    return len(query_terms & evidence_terms) / len(query_terms)


def route_query(query: str) -> str:
    value = fold(query)
    if any(term in value for term in ("dau nguc", "kho tho", "ngat", "dot quy", "chay mau nhieu", "tu tu")):
        return "emergency"
    if is_legal_document_query(query):
        return "rag"
    if any(term in value for term in ("ho so cua toi", "ket qua xet nghiem", "benh an", "thanh toan cua toi")):
        return "requires_tool"
    if any(term in value for term in ("hom nay", "chieu nay", "con lich", "gia hien tai", "dang truc", "giuong trong", "trang thai")):
        return "requires_tool"
    if any(term in value for term in ("chan doan", "ke don", "doi thuoc", "lieu dung")):
        return "human_handoff"
    return "rag"


def make_handler(application: RAGApplication, static_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HeartCareRAG/0.1"
        client_cookie = "heartcare_demo_client"

        def log_message(self, fmt: str, *args) -> None:
            print(f"{self.address_string()} - {fmt % args}", flush=True)

        def send_json(self, value: object, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if getattr(self, "_client_id", ""):
                self.send_header("Set-Cookie", f"{self.client_cookie}={self._client_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # A browser can close the tab or cancel a long response after
                # headers were sent. The response is already abandoned; do not
                # turn that normal disconnect into a server traceback.
                return

        def client_id(self) -> str:
            if getattr(self, "_client_id", ""):
                return self._client_id
            cookies = {}
            for pair in self.headers.get("Cookie", "").split(";"):
                if "=" in pair:
                    key, value = pair.strip().split("=", 1)
                    cookies[key] = value
            candidate = cookies.get(self.client_cookie, "")
            self._client_id = candidate if re.fullmatch(r"[0-9a-f-]{36}", candidate) else str(uuid.uuid4())
            return self._client_id

        def read_json(self) -> dict | None:
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 64_000:
                    return None
                return json.loads(self.rfile.read(size))
            except (ValueError, json.JSONDecodeError):
                return None

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.send_json(application.health())
                return
            if parsed.path == "/api/v1/rag/catalog":
                self.send_json({
                    "schema_version": "heartcare.rag.catalog.v1",
                    "sources": application.knowledge_catalog(),
                })
                return
            if parsed.path == "/c":
                self.send_json({"sessions": application.list_sessions(self.client_id())})
                return
            if parsed.path.startswith("/c/"):
                session = application.get_session(unquote(parsed.path[3:]), self.client_id())
                self.send_json({"Session": session}, HTTPStatus.OK if session else HTTPStatus.NOT_FOUND)
                return
            self.serve_static(parsed.path)

        def do_HEAD(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                return
            target = static_dir / "index.html"
            if parsed.path != "/":
                candidate = (static_dir / parsed.path.lstrip("/")).resolve()
                if static_dir.resolve() in candidate.parents and candidate.is_file():
                    target = candidate
            if not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/rag/retrieve":
                payload = self.read_json()
                if not payload or not isinstance(payload.get("query"), str) or not payload["query"].strip():
                    self.send_json({"error": "query must be a non-empty string"}, HTTPStatus.BAD_REQUEST)
                    return
                requested_top_k = payload.get("top_k", 8)
                if not isinstance(requested_top_k, int):
                    self.send_json({"error": "top_k must be an integer"}, HTTPStatus.BAD_REQUEST)
                    return
                self.send_json(application.retrieve(payload["query"].strip(), requested_top_k))
                return
            if parsed.path == "/api/v1/rag/context":
                payload = self.read_json()
                if not payload or not isinstance(payload.get("chunk_id"), str) or not payload["chunk_id"].strip():
                    self.send_json({"error": "chunk_id must be a non-empty string"}, HTTPStatus.BAD_REQUEST)
                    return
                scope = payload.get("scope", "section")
                limit = payload.get("limit", 20)
                if scope not in {"section", "document"} or not isinstance(limit, int):
                    self.send_json({"error": "invalid context scope or limit"}, HTTPStatus.BAD_REQUEST)
                    return
                self.send_json(application.expand_context(payload["chunk_id"].strip(), scope, limit))
                return
            if parsed.path == "/c":
                self.send_json({"session_id": application.create_session(self.client_id())}, HTTPStatus.CREATED)
                return
            if parsed.path.startswith("/c/"):
                payload = self.read_json()
                if not payload or not isinstance(payload.get("message"), str) or not payload["message"].strip():
                    self.send_json({"error": "Tin nhắn không hợp lệ."}, HTTPStatus.BAD_REQUEST)
                    return
                response = application.post_message(unquote(parsed.path[3:]), payload["message"].strip(), self.client_id())
                self.send_json({"response": response} if response else {"error": "Không tìm thấy phiên."},
                               HTTPStatus.OK if response else HTTPStatus.NOT_FOUND)
                return
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/c/") and application.delete_session(unquote(parsed.path[3:]), self.client_id()):
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            self.send_json({"error": "Không tìm thấy phiên."}, HTTPStatus.NOT_FOUND)

        def serve_static(self, request_path: str) -> None:
            relative = request_path.lstrip("/") or "index.html"
            target = (static_dir / relative).resolve()
            if static_dir.resolve() not in target.parents and target != static_dir.resolve():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not target.is_file():
                target = static_dir / "index.html"
            if not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="HeartCare grounded RAG demo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6689)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--documents", type=Path)
    parser.add_argument("--knowledge-manifest", type=Path)
    parser.add_argument("--static", type=Path, required=True)
    args = parser.parse_args()
    application = RAGApplication(args.chunks, args.catalog, args.documents, args.knowledge_manifest)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(application, args.static))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print(json.dumps({"event": "started", "host": args.host, "port": args.port, **application.health()}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
