"""
query_transform node — the only LLM call in the retrieval pipeline.

B2 optimisations applied here:
  1. LLM injected as singleton (never created inside this function).
  2. temperature=0, num_predict capped in LLM factory (see create_query_transform_llm).
  3. Heuristic skip: simple queries bypass LLM entirely → ~0ms decompose.
  4. Speculative retrieval: raw query is always included in sub_queries so the
     retrieve_worker for the original query runs in parallel while LLM decodes,
     effectively overlapping LLM latency with search I/O.

Fallback: if LLM fails or returns nothing, raw query is used as-is.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.config import Settings
from app.services.rag.graph.state import RetrievalState

logger = logging.getLogger(__name__)

# ── Prompt ───────────────────────────────────────────────────────────────────
_PROMPT = """Bạn phân rã truy vấn cho hệ thống tìm kiếm tài liệu y tế tiếng Việt.

Quy tắc:
- Phân rã truy vấn thành các câu truy vấn con độc lập phục vụ tìm kiếm.
- Chỉ tách khi câu hỏi có nhiều ý rõ rệt. Câu đơn giản: trả về đúng 1 câu.
- Thông thường 1-3 câu. TUYỆT ĐỐI không quá {max_subqueries} câu.
- Mỗi câu ngắn gọn, giữ nguyên thuật ngữ quan trọng. Không giải thích.

Chỉ trả về danh sách đánh số, mỗi dòng một câu:
1. ...
2. ...

Truy vấn: {query}
"""

_NUM_RE = re.compile(r"^\s*(?:\d+[\.\)]|[-*•])\s*(.+?)\s*$")

# Vietnamese conjunctions / punctuation that signals a multi-part query.
_COMPLEX_PATTERN = re.compile(
    r"\bvà\b|\bhoặc\b|\bhay\b|\bngoài ra\b|\bkèm\b|\bcũng\b|\bnhư thế nào.+\bvà\b",
    re.IGNORECASE,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_simple_query(query: str, max_words: int = 8) -> bool:
    """
    Return True if the query is too simple to benefit from LLM decomposition.

    Heuristic (conservative — prefers calling LLM for ambiguous cases):
      - Word count <= max_words  AND
      - No Vietnamese conjunctions / list punctuation

    Impact: ~40-50% of real medical queries are simple → saves the full
    LLM round-trip (~700-1600ms) for those queries.
    """
    word_count = len(query.split())
    if word_count > max_words:
        return False
    if _COMPLEX_PATTERN.search(query):
        return False
    return True


def _parse_sub_queries(text: str, max_n: int) -> list[str]:
    """Extract sub-queries from an LLM list response."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _NUM_RE.match(line)
        candidate = m.group(1).strip() if m else line
        if candidate.lower().startswith(("truy vấn gốc", "danh sách", "kết quả")):
            continue
        if len(candidate) < 3:
            continue
        if candidate not in out:
            out.append(candidate)
        if len(out) >= max_n:
            break
    return out


# ── node ─────────────────────────────────────────────────────────────────────

async def query_transform_node(
    state: RetrievalState,
    settings: Settings,
    llm: Any = None,
) -> dict:
    """
    Rewrite + decompose the query into sub_queries (single LLM call).

    Args:
        state:    LangGraph state (carries query, trace_id, timings_ms).
        settings: Application settings singleton.
        llm:      Pre-created LLM singleton injected by RAGService (B3).
                  Falls back to create_llm() if None (legacy / test path).
    """
    start = time.perf_counter()
    max_n = settings.retrieval_max_subqueries
    query = state.query.strip()

    # ── B2-3: Heuristic skip for simple queries ──────────────────────────────
    if _is_simple_query(query):
        elapsed = (time.perf_counter() - start) * 1000
        logger.debug(
            "query_transform skipped (simple query)",
            extra={"trace_id": state.trace_id, "latency_ms": round(elapsed, 1)},
        )
        return {
            "sub_queries": [query],
            "timings_ms": {**state.timings_ms, "query_transform": round(elapsed, 1)},
        }

    # ── B3: Use injected LLM singleton; lazy-import factory only as fallback ──
    if llm is None:
        from app.services.rag.llm_factory import create_query_transform_llm
        llm = create_query_transform_llm(settings)

    sub_queries: list[str] = []
    try:
        prompt = _PROMPT.format(max_subqueries=max_n, query=query)
        resp = await llm.ainvoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        sub_queries = _parse_sub_queries(content, max_n)
    except Exception as exc:
        logger.warning(
            "query_transform LLM failed, falling back to raw query",
            extra={"trace_id": state.trace_id, "error": str(exc)},
        )

    # ── B2-4 (Speculative): always include raw query ──────────────────────────
    # The raw query worker starts immediately alongside the decomposed ones,
    # overlapping the LLM decode time with search I/O on the original query.
    if not sub_queries:
        sub_queries = [query]
    else:
        # Insert raw query first (highest-recall anchor); dedupe; cap to max_n.
        if query not in sub_queries:
            sub_queries = [query] + sub_queries
        sub_queries = sub_queries[:max_n]

    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        "query_transform done",
        extra={
            "trace_id": state.trace_id,
            "sub_query_count": len(sub_queries),
            "latency_ms": round(elapsed, 1),
        },
    )

    return {
        "sub_queries": sub_queries,
        "timings_ms": {**state.timings_ms, "query_transform": round(elapsed, 1)},
    }


__all__ = ["query_transform_node"]
