"""
Planner node — Two LCEL chains for planning and decision making.

Chain 1  (plan_chain):
    - Runs on FIRST iteration or when replanning is triggered.
    - Uses strong model, temperature=0.
    - Structured output → PlannerPlanOutput (tasks list).
    - Dispatches up to MAX_PARALLEL_TASKS tasks per iteration.

Chain 2  (decision_chain):
    - Runs AFTER merge (every iteration after branches complete).
    - Uses middle model, temperature=0.
    - Structured output → PlannerDecisionOutput (is_finished, new_tasks).
    - If is_finished=False, appends new_tasks and loops back to router.

Public interface:
    run_planner_node(state, settings) → dict   (LangGraph node function)
"""

from __future__ import annotations
import logging
import time

from langchain_core.prompts import ChatPromptTemplate

from app.config import Settings
from app.services.rag.graph.main_state import MainState
from app.services.rag.graph.schemas import (
    MAX_PARALLEL_TASKS,
    MAX_TASK_RETRY,
    BranchError,
    PlannerDecisionOutput,
    PlannerPlanOutput,
    Task,
    TaskStatus,
)
from app.services.rag.llm_factory import create_tier_llm
from app.services.rag.graph.nodes.planner.prompts import (
    DECISION_HUMAN,
    DECISION_SYSTEM,
    PLAN_HUMAN,
    PLAN_SYSTEM,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build human-readable summaries passed to prompts
# ─────────────────────────────────────────────────────────────────────────────

def _format_task_summary(tasks: list[Task]) -> str:
    if not tasks:
        return "(none)"
    lines = []
    for t in tasks:
        lines.append(
            f"- {t.task_id} [{t.data_type}] status={t.status} "
            f"retries={t.retry_count}/{MAX_TASK_RETRY}  query={t.query!r}"
        )
    return "\n".join(lines)


def _format_branch_results(branch_results: list) -> str:
    if not branch_results:
        return "(no results yet)"
    lines = []
    for r in branch_results:
        snippet = (r.content[:200] + "...") if len(r.content) > 200 else r.content
        lines.append(
            f"- task_id={r.task_id}  type={r.data_type}  "
            f"status={r.status}  latency={r.latency:.2f}s\n  content: {snippet}"
        )
    return "\n".join(lines)


def _format_errors(errors: list) -> str:
    if not errors:
        return "(none)"
    lines = []
    for e in errors:
        lines.append(
            f"- task_id={e.task_id}  type={e.data_type}  "
            f"retries={e.retry_count}  error={e.error_message!r}"
        )
    return "\n".join(lines)


def _format_completed_tasks(branch_results: list) -> str:
    if not branch_results:
        return "(none)"
    lines = []
    for r in branch_results:
        lines.append(
            f"- task_id={r.task_id}  type={r.data_type}  status={r.status}"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Chain 1 — Plan chain (strong model, structured output)
# ─────────────────────────────────────────────────────────────────────────────

def _build_plan_chain(settings: Settings):
    """
    Build the planning LCEL chain.

    Pipeline:
        input_dict
            → ChatPromptTemplate   (format PLAN_SYSTEM + PLAN_HUMAN)
            → LLM.with_structured_output(PlannerPlanOutput)
    """
    llm = create_tier_llm(settings, tier="strong", temperature=0.0)
    structured_llm = llm.with_structured_output(PlannerPlanOutput, method="function_calling")

    prompt = ChatPromptTemplate.from_messages([
        ("system", PLAN_SYSTEM),
        ("human", PLAN_HUMAN),
    ])

    chain = prompt | structured_llm
    return chain


# ─────────────────────────────────────────────────────────────────────────────
# Chain 2 — Decision chain (middle model, structured output)
# ─────────────────────────────────────────────────────────────────────────────

def _build_decision_chain(settings: Settings):
    """
    Build the decision/replan LCEL chain.

    Pipeline:
        input_dict
            → ChatPromptTemplate   (format DECISION_SYSTEM + DECISION_HUMAN)
            → LLM.with_structured_output(PlannerDecisionOutput)
    """
    llm = create_tier_llm(settings, tier="middle", temperature=0.0)
    structured_llm = llm.with_structured_output(PlannerDecisionOutput, method="function_calling")

    prompt = ChatPromptTemplate.from_messages([
        ("system", DECISION_SYSTEM),
        ("human", DECISION_HUMAN),
    ])

    chain = prompt | structured_llm
    return chain


# ─────────────────────────────────────────────────────────────────────────────
# Task scheduling helpers
# ─────────────────────────────────────────────────────────────────────────────

def _select_ready_tasks(tasks: list[Task], max_parallel: int) -> list[Task]:
    """
    Return up to `max_parallel` tasks that are ready to dispatch.

    A task is ready when:
      - status is "pending" or "failed" (can_retry)
      - all tasks in depends_on are done (status in success|exhausted)
    """
    done_ids = {t.task_id for t in tasks if t.is_done()}
    ready: list[Task] = []

    for task in tasks:
        if len(ready) >= max_parallel:
            break
        if task.status == "pending" or task.can_retry():
            # Check dependencies
            if all(dep in done_ids for dep in task.depends_on):
                ready.append(task)

    return ready


def _all_tasks_terminal(tasks: list[Task]) -> bool:
    """True when every task is in a terminal state (success or exhausted)."""
    return bool(tasks) and all(t.is_done() for t in tasks)


# ─────────────────────────────────────────────────────────────────────────────
# Public node function
# ─────────────────────────────────────────────────────────────────────────────

async def run_planner_node(state: MainState, settings: Settings) -> dict:
    """
    LangGraph node function for the planner.

    Behaviour:
      - iteration == 0  →  run Chain 1 to generate initial task plan.
      - iteration  > 0  →  run Chain 2 to decide finish vs replan.
        * If Chain 2 says is_finished=True → set is_finished flag.
        * If Chain 2 says is_finished=False → append new_tasks, continue loop.

    Returns a dict that LangGraph merges into MainState.
    """
    trace_id = state.trace_id
    iteration = state.iteration
    start = time.perf_counter()

    logger.info(
        "Planner node started",
        extra={"trace_id": trace_id, "iteration": iteration, "query": state.query[:80]},
    )

    try:
        # ── Branch: initial plan vs decision ─────────────────────────────
        if iteration == 0:
            result_dict = await _run_plan_chain(state, settings)
        else:
            result_dict = await _run_decision_chain(state, settings)

        elapsed = time.perf_counter() - start
        logger.info(
            "Planner node finished",
            extra={
                "trace_id": trace_id,
                "iteration": iteration,
                "is_finished": result_dict.get("is_finished"),
                "task_count": len(result_dict.get("tasks", state.tasks)),
                "latency_s": f"{elapsed:.2f}",
            },
        )
        return result_dict

    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            "Planner node error — forcing finish to avoid stuck loop",
            extra={"trace_id": trace_id, "error": str(exc), "latency_s": f"{elapsed:.2f}"},
            exc_info=True,
        )
        # On planner failure, surface error and stop the loop gracefully
        return {
            "is_finished": True,
            "iteration": iteration + 1,
            "errors": state.errors + [
                BranchError(
                    task_id="planner",
                    data_type="type1",  # placeholder
                    error_message=f"Planner error at iteration {iteration}: {exc}",
                    retry_count=0,
                )
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers for each chain
# ─────────────────────────────────────────────────────────────────────────────

async def _run_plan_chain(state: MainState, settings: Settings) -> dict:
    """
    Execute Chain 1 (initial planning).

    Returns a state-update dict with:
      - tasks: list[Task] — all planned tasks with status=pending
      - iteration: incremented
      - is_finished: False (always — we just planned, nothing executed yet)
    """
    logger.info(
        "Planner [Chain1] — generating initial plan",
        extra={"trace_id": state.trace_id},
    )

    chain = _build_plan_chain(settings)

    plan_input = {
        "query": state.query,
        "iteration": state.iteration,
        "max_iterations": state.max_iterations,
        "completed_tasks": _format_completed_tasks(state.branch_results),
        "errors": _format_errors(state.errors),
    }

    plan: PlannerPlanOutput = await chain.ainvoke(plan_input)

    logger.info(
        "Planner [Chain1] done",
        extra={
            "trace_id": state.trace_id,
            "reasoning_snippet": plan.reasoning[:120],
            "task_count": len(plan.tasks),
            "tasks": [f"{t.task_id}:{t.data_type}" for t in plan.tasks],
        },
    )

    if not plan.tasks:
        # No retrieval needed — skip straight to synthesizer
        logger.info(
            "Planner [Chain1]: no tasks generated, finishing immediately",
            extra={"trace_id": state.trace_id},
        )
        return {
            "tasks": [],
            "is_finished": True,
            "iteration": state.iteration + 1,
        }

    # Cap to MAX_PARALLEL_TASKS for first batch; extras remain pending
    return {
        "tasks": plan.tasks,
        "is_finished": False,
        "iteration": state.iteration + 1,
    }


async def _run_decision_chain(state: MainState, settings: Settings) -> dict:
    """
    Execute Chain 2 (decision after merge).

    Checks terminal conditions BEFORE calling the LLM to avoid unnecessary
    token usage when the answer is obvious.

    Returns a state-update dict with is_finished, iteration, and optionally
    appended tasks.
    """
    tasks = state.tasks

    # ── Fast-path: all tasks terminal ────────────────────────────────────
    if _all_tasks_terminal(tasks):
        logger.info(
            "Planner [Chain2] fast-path: all tasks terminal, finishing",
            extra={"trace_id": state.trace_id},
        )
        return {
            "is_finished": True,
            "iteration": state.iteration + 1,
        }

    # ── Fast-path: max iterations hit ────────────────────────────────────
    if state.iteration >= state.max_iterations:
        logger.warning(
            "Planner [Chain2] fast-path: max_iterations reached, forcing finish",
            extra={"trace_id": state.trace_id, "iteration": state.iteration},
        )
        return {
            "is_finished": True,
            "iteration": state.iteration + 1,
        }

    # ── LLM decision ─────────────────────────────────────────────────────
    logger.info(
        "Planner [Chain2] — invoking decision LLM",
        extra={"trace_id": state.trace_id, "iteration": state.iteration},
    )

    chain = _build_decision_chain(settings)

    decision_input = {
        "query": state.query,
        "iteration": state.iteration,
        "max_iterations": state.max_iterations,
        "task_summary": _format_task_summary(tasks),
        "branch_results_summary": _format_branch_results(state.branch_results),
        "errors": _format_errors(state.errors),
    }

    decision: PlannerDecisionOutput = await chain.ainvoke(decision_input)

    logger.info(
        "Planner [Chain2] done",
        extra={
            "trace_id": state.trace_id,
            "is_finished": decision.is_finished,
            "new_task_count": len(decision.new_tasks),
            "reasoning_snippet": decision.reasoning[:120],
        },
    )

    if decision.is_finished:
        return {
            "is_finished": True,
            "iteration": state.iteration + 1,
        }

    # Append new tasks (with status=pending) for the next router pass
    updated_tasks = list(tasks) + [
        t.model_copy(update={"status": "pending"}) for t in decision.new_tasks
    ]
    return {
        "tasks": updated_tasks,
        "is_finished": False,
        "iteration": state.iteration + 1,
    }
