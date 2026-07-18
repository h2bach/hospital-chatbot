"""
Main RAG Graph — Correctly wired with Send() as conditional edge.

LangGraph v1.x rule: Send() MUST come from a conditional edge function,
NOT from a regular node.

Flow:
    START
      │
      ▼
    planner  (Chain1 on iter=0 / Chain2 on iter>0)
      │
      └── conditional edge: dispatch_tasks()
              │
              ├── "synthesizer"    when is_finished=True
              │
              ├── list[Send]       fan-out to subgraph nodes
              │         │
              │   ┌─────┴──────┐
              │   ▼            ▼
              │ type1_subgraph  …(future typeN)
              │         │
              │         ▼
              │       merge  ──► planner  (loop)
              │
              └── "merge"          fallback when all tasks blocked

Extensibility:
  1. Implement new subgraph → build_typeN_subgraph(settings)
  2. builder.add_node("typeN_subgraph", ...)
  3. builder.add_edge("typeN_subgraph", "merge")
  4. SUBGRAPH_NODE_MAP["typeN"] = "typeN_subgraph"  (router/node.py)
  No other changes required.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.services.rag.graph.main_state import MainState

# ── Node implementations ──────────────────────────────────────────────────────
from app.services.rag.graph.nodes.planner.node import run_planner_node
from app.services.rag.graph.nodes.merge.node import run_merge_node
from app.services.rag.graph.nodes.synthesizer.node import run_synthesizer_node

# ── Conditional edge (Send dispatcher) ───────────────────────────────────────
from app.services.rag.graph.nodes.router.node import dispatch_tasks, SUBGRAPH_NODE_MAP

# ── Subgraph builders ─────────────────────────────────────────────────────────
from app.services.rag.type1.graph import build_type1_subgraph

logger = logging.getLogger(__name__)


# =============================================================================
# Graph construction
# =============================================================================

def build_rag_graph(settings: Settings) -> StateGraph:
    """
    Build the RAG StateGraph (not compiled yet).

    All nodes are bound to `settings` via closures — the API layer only
    needs to call graph.ainvoke(state).
    """
    logger.info("Building RAG graph")

    # ── Bind settings to nodes ────────────────────────────────────────────
    async def planner_node(state: MainState) -> dict:
        return await run_planner_node(state, settings)

    async def merge_node(state: MainState) -> dict:
        return await run_merge_node(state, settings)

    async def synthesizer_node(state: MainState) -> dict:
        return await run_synthesizer_node(state, settings)

    # ── Build subgraphs ───────────────────────────────────────────────────
    type1_subgraph = build_type1_subgraph(settings)

    # ── Assemble graph ────────────────────────────────────────────────────
    builder = StateGraph(MainState)

    # Core nodes
    builder.add_node("planner", planner_node)
    builder.add_node("merge", merge_node)
    builder.add_node("synthesizer", synthesizer_node)

    # Subgraph nodes — name MUST match SUBGRAPH_NODE_MAP values
    builder.add_node("type1_subgraph", type1_subgraph)
    # builder.add_node("type2_subgraph", build_type2_subgraph(settings))

    # ── Edges ─────────────────────────────────────────────────────────────

    # Entry point
    builder.add_edge(START, "planner")

    # Planner → conditional edge (Send fan-out OR string routing)
    # dispatch_tasks() returns either list[Send] or a string key.
    builder.add_conditional_edges(
        "planner",
        dispatch_tasks,
        # Map string keys to node names; Send() objects bypass this map.
        {
            "synthesizer": "synthesizer",
            "merge": "merge",
        },
    )

    # Each subgraph converges to merge after completion
    builder.add_edge("type1_subgraph", "merge")
    # builder.add_edge("type2_subgraph", "merge")

    # Merge loops back to planner (Chain 2 decision)
    builder.add_edge("merge", "planner")

    # Terminal
    builder.add_edge("synthesizer", END)

    logger.info("RAG graph built — nodes: %s", list(builder.nodes))
    return builder


def compile_rag_graph(builder: StateGraph) -> Any:
    """Compile the StateGraph into an executable graph."""
    logger.info("Compiling RAG graph")
    compiled = builder.compile()
    logger.info("RAG graph compiled")
    return compiled
