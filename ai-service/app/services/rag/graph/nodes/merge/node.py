"""
Merge node — aggregates subgraph results back into MainState.

Responsibilities:
  1. Read branch_results accumulated by the `add` reducer in MainState.
  2. Sync task statuses: mark tasks success/failed based on BranchResult.status.
  3. Promote failed+exhausted tasks to BranchError in MainState.errors.
  4. Log aggregated stats for observability.

This node does NOT call any LLM — it is pure state manipulation.
After merge, control returns to the planner (Chain 2) for the decision.
"""

from __future__ import annotations

import logging
import time

from app.config import Settings
from app.services.rag.graph.main_state import MainState
from app.services.rag.graph.schemas import (
    MAX_TASK_RETRY,
    BranchError,
    BranchResult,
    Task,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sync_task_statuses(
    tasks: list[Task],
    branch_results: list[BranchResult],
) -> tuple[list[Task], list[BranchError]]:
    """
    Walk branch_results and update corresponding task statuses.

    Rules:
      - BranchResult.status == "success"  → task.mark_success()
      - BranchResult.status == "failed"   → task.mark_failed()
          * if retry_count reaches MAX_TASK_RETRY → task becomes "exhausted"
            and a BranchError is appended.

    Returns (updated_tasks, new_errors).
    """
    # Index results by task_id (last result wins if duplicates exist)
    result_by_id: dict[str, BranchResult] = {}
    for r in branch_results:
        result_by_id[r.task_id] = r

    updated: list[Task] = []
    new_errors: list[BranchError] = []

    for task in tasks:
        result = result_by_id.get(task.task_id)

        if result is None:
            # No result yet → keep as-is
            updated.append(task)
            continue

        if result.status == "success":
            updated.append(task.mark_success())

        elif result.status == "failed":
            failed_task = task.mark_failed()
            updated.append(failed_task)

            if failed_task.status == "exhausted":
                new_errors.append(
                    BranchError(
                        task_id=task.task_id,
                        data_type=task.data_type,
                        error_message=result.content or "Branch failed with no error message",
                        retry_count=failed_task.retry_count,
                    )
                )
                logger.warning(
                    "Merge: task exhausted (max retries reached)",
                    extra={
                        "task_id": task.task_id,
                        "data_type": task.data_type,
                        "retry_count": failed_task.retry_count,
                    },
                )
        else:
            # status "none" or "running" — shouldn't normally happen at merge time
            updated.append(task)

    return updated, new_errors


# ─────────────────────────────────────────────────────────────────────────────
# Public node function
# ─────────────────────────────────────────────────────────────────────────────

async def run_merge_node(state: MainState, settings: Settings) -> dict:
    """
    LangGraph node function for the merge step.

    Returns a state-update dict with:
      - tasks: updated task list (statuses synced from branch_results)
      - errors: new BranchError entries for exhausted tasks (appended via reducer)
    """
    trace_id = state.trace_id
    start = time.perf_counter()

    result_count = len(state.branch_results)
    error_count = len(state.errors)

    logger.info(
        "Merge node started",
        extra={
            "trace_id": trace_id,
            "branch_results": result_count,
            "existing_errors": error_count,
            "iteration": state.iteration,
        },
    )

    updated_tasks, new_errors = _sync_task_statuses(
        state.tasks, state.branch_results
    )

    # Build a concise summary for debugging
    status_summary = {
        t.status: sum(1 for x in updated_tasks if x.status == t.status)
        for t in updated_tasks
    }

    elapsed = time.perf_counter() - start

    logger.info(
        "Merge node done",
        extra={
            "trace_id": trace_id,
            "task_status_summary": status_summary,
            "new_errors": len(new_errors),
            "latency_s": f"{elapsed:.3f}",
        },
    )

    update: dict = {"tasks": updated_tasks}

    # errors field uses `add` reducer — we append only the new errors
    if new_errors:
        update["errors"] = new_errors

    return update
