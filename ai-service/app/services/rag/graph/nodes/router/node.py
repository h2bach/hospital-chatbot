"""
Router — conditional edge function that returns list[Send].

In LangGraph v1.x, Send() MUST be returned from a conditional edge function,
NOT from a regular node.  This module provides:

  dispatch_tasks(state, settings) → list[Send] | str

which is registered with add_conditional_edges() on the planner node.

When is_finished=True  → returns "synthesizer" (string routing)
When is_finished=False → returns list[Send] to fan out to subgraphs

Extensibility:
  Adding a new data_type: add one entry to SUBGRAPH_NODE_MAP.
  No other changes required.
"""

from __future__ import annotations

import logging
from typing import Union

from langgraph.types import Send

from app.config import Settings
from app.services.rag.graph.main_state import MainState
from app.services.rag.graph.schemas import MAX_PARALLEL_TASKS, Task

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Registry: data_type → subgraph node name in the main graph.
# To add a new subgraph: add entry here AND add_node() in main_graph.py.
# ─────────────────────────────────────────────────────────────────────────────

SUBGRAPH_NODE_MAP: dict[str, str] = {
    "type1": "type1_subgraph",
    # "type2": "type2_subgraph",
    # "type3": "type3_subgraph",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _select_ready_tasks(tasks: list[Task], max_parallel: int) -> list[Task]:
    """
    Return up to `max_parallel` tasks ready to dispatch.

    Ready = (pending OR can_retry) AND all depends_on are terminal.
    """
    done_ids = {t.task_id for t in tasks if t.is_done()}
    ready: list[Task] = []
    for task in tasks:
        if len(ready) >= max_parallel:
            break
        is_actionable = task.status == "pending" or task.can_retry()
        deps_met = all(dep in done_ids for dep in task.depends_on)
        if is_actionable and deps_met:
            ready.append(task)
    return ready


def _build_subgraph_input(task: Task, state: MainState) -> dict:
    """Build the initial state dict for the target subgraph."""
    if task.data_type == "type1":
        return {
            "task_id": task.task_id,
            "query": task.query,
            "parameters": task.parameters,
            "status": "running",
            "retry_count": task.retry_count,
        }
    # Future: add elif task.data_type == "type2": ...
    raise ValueError(f"No subgraph input builder for data_type={task.data_type!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Public: conditional edge function
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_tasks(state: MainState) -> Union[list[Send], str]:
    """
    Conditional edge function called after planner node.

    Returns:
      - "synthesizer"   when is_finished=True or max_iterations reached
      - list[Send]      fan-out to subgraph nodes (one Send per ready task)
      - "merge"         fallback when tasks exist but none are ready yet
                        (all blocked on dependencies or exhausted)
    """
    trace_id = state.trace_id

    # ── Terminal conditions ────────────────────────────────────────────
    if state.is_finished or state.iteration >= state.max_iterations:
        logger.info(
            "Router edge: → synthesizer",
            extra={
                "trace_id": trace_id,
                "is_finished": state.is_finished,
                "iteration": state.iteration,
            },
        )
        return "synthesizer"

    tasks = state.tasks

    if not tasks:
        # Planner generated no tasks — go straight to synthesizer
        logger.info(
            "Router edge: no tasks → synthesizer",
            extra={"trace_id": trace_id},
        )
        return "synthesizer"

    ready = _select_ready_tasks(tasks, MAX_PARALLEL_TASKS)

    if not ready:
        # All tasks blocked or exhausted; let merge+planner decide
        logger.warning(
            "Router edge: no ready tasks → merge (all blocked/exhausted)",
            extra={
                "trace_id": trace_id,
                "task_statuses": [(t.task_id, t.status) for t in tasks],
            },
        )
        return "merge"

    sends: list[Send] = []
    for task in ready:
        node_name = SUBGRAPH_NODE_MAP.get(task.data_type)
        if node_name is None:
            logger.error(
                "Router edge: unknown data_type — task skipped",
                extra={
                    "trace_id": trace_id,
                    "task_id": task.task_id,
                    "data_type": task.data_type,
                },
            )
            continue
        payload = _build_subgraph_input(task, state)
        sends.append(Send(node_name, payload))
        logger.info(
            "Router edge: Send() → %s",
            node_name,
            extra={"trace_id": trace_id, "task_id": task.task_id},
        )

    if not sends:
        logger.warning(
            "Router edge: all ready tasks had unknown data_type → merge",
            extra={"trace_id": trace_id},
        )
        return "merge"

    return sends
