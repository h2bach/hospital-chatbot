"""
Synthesizer node — LCEL chain for final answer generation.

Responsibilities:
  1. Collect all successful BranchResult.content from MainState.
  2. Build a formatted passages block with source metadata.
  3. Call middle-tier LLM to generate the answer with citations.
  4. Return final_answer to MainState.

Chain:
    input_dict
        → ChatPromptTemplate (SYNTHESIZER_SYSTEM + SYNTHESIZER_HUMAN)
        → LLM (middle tier, temperature=0)
        → StrOutputParser
        → post-process: strip whitespace
"""

from __future__ import annotations

import logging
import time

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config import Settings
from app.services.rag.graph.main_state import MainState
from app.services.rag.graph.schemas import BranchResult, BranchError
from app.services.rag.llm_factory import create_tier_llm
from app.services.rag.graph.nodes.synthesizer.prompts import (
    SYNTHESIZER_HUMAN,
    SYNTHESIZER_SYSTEM,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Chain builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_synthesizer_chain(settings: Settings):
    """
    Build the synthesizer LCEL chain.

    Pipeline:
        input_dict
            → ChatPromptTemplate
            → LLM (middle, temp=0)
            → StrOutputParser
    """
    llm = create_tier_llm(settings, tier="middle", temperature=0.0)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYNTHESIZER_SYSTEM),
        ("human", SYNTHESIZER_HUMAN),
    ])

    chain = prompt | llm | StrOutputParser()
    return chain


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_passages_block(branch_results: list[BranchResult]) -> str:
    """
    Concatenate content from successful branches into a numbered passage block.

    Each result's content already contains numbered sub-passages from the
    Type1 subgraph (e.g. [1] (p.3 | Section > Sub)).
    We prefix each result block with the branch label for clarity.
    """
    if not branch_results:
        return "(No retrieved passages)"

    successful = [r for r in branch_results if r.status == "success" and r.content.strip()]
    if not successful:
        return "(No successful retrieval results)"

    blocks: list[str] = []
    for r in successful:
        blocks.append(
            f"### Source: {r.data_type} | task={r.task_id}\n{r.content}"
        )
    return "\n\n".join(blocks)


def _build_failed_summary(errors: list[BranchError]) -> str:
    if not errors:
        return "(none)"
    lines = [
        f"- {e.data_type} (task={e.task_id}): {e.error_message} "
        f"[{e.retry_count} retries]"
        for e in errors
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Public node function
# ─────────────────────────────────────────────────────────────────────────────

async def run_synthesizer_node(state: MainState, settings: Settings) -> dict:
    """
    LangGraph node function for the synthesizer.

    Returns a state-update dict with:
        - final_answer: str
    """
    trace_id = state.trace_id
    start = time.perf_counter()

    logger.info(
        "Synthesizer node started",
        extra={
            "trace_id": trace_id,
            "branch_results": len(state.branch_results),
            "errors": len(state.errors),
            "iteration": state.iteration,
        },
    )

    passages = _build_passages_block(state.branch_results)
    failed_summary = _build_failed_summary(state.errors)

    logger.debug(
        "Synthesizer: input prepared",
        extra={
            "trace_id": trace_id,
            "passages_len": len(passages),
            "failed_count": len(state.errors),
        },
    )

    try:
        chain = _build_synthesizer_chain(settings)

        answer: str = await chain.ainvoke({
            "query": state.query,
            "passages": passages,
            "failed_summary": failed_summary,
        })

        answer = answer.strip()
        elapsed = time.perf_counter() - start

        logger.info(
            "Synthesizer node done",
            extra={
                "trace_id": trace_id,
                "answer_len": len(answer),
                "latency_s": f"{elapsed:.2f}",
            },
        )

        return {"final_answer": answer}

    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            "Synthesizer node error",
            extra={
                "trace_id": trace_id,
                "error": str(exc),
                "latency_s": f"{elapsed:.2f}",
            },
            exc_info=True,
        )
        # Graceful degradation: return whatever context we have
        fallback = (
            f"Xin lỗi, đã xảy ra lỗi khi tổng hợp câu trả lời.\n\n"
            f"Thông tin tìm được:\n{passages[:2000]}"
        )
        return {"final_answer": fallback}
