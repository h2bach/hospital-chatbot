"""
MainState - Main state for the RAG system.

This is the Single Source of Truth, checkpointed by LangGraph.
Following ARCHITECTURE.md Section 4.4.
"""

from typing import Annotated
from operator import add
from pydantic import BaseModel, Field

from .schemas import Task, BranchResult, BranchError


class MainState(BaseModel):
    """
    Main state for RAG Multi-Agent System.
    
    Lifecycle:
    1. User input → query
    2. Planner → tasks, is_finished
    3. Router → dispatch tasks to subgraphs
    4. Subgraphs → branch_results (merged via reducer)
    5. Merge → aggregate results
    6. Planner → check is_finished or replan
    7. Loop until finished or max_iterations
    8. Synthesizer → final_answer
    """
    
    # ========================================================================
    # Observability & Tracing
    # ========================================================================
    
    trace_id: str = Field(
        ...,
        description="Unique ID for this request (UUID). Used for logging/tracing"
    )
    
    session_id: str | None = Field(
        default=None,
        description="Session ID for multi-turn conversations"
    )
    
    # ========================================================================
    # Input
    # ========================================================================
    
    query: str = Field(
        ...,
        description="Original query from user"
    )
    
    rewritten_query: str = Field(
        default="",
        description="Query after rewriter normalization"
    )
    
    # ========================================================================
    # Planner Control
    # ========================================================================
    
    tasks: list[Task] = Field(
        default_factory=list,
        description=(
            "List of tasks from planner (DAG). "
            "Overwritten each iteration when planner replans"
        )
    )
    
    iteration: int = Field(
        default=0,
        description="Current iteration (0-indexed). Max = max_iterations"
    )
    
    max_iterations: int = Field(
        default=5,
        description="Maximum iterations before force stop"
    )
    
    is_finished: bool = Field(
        default=False,
        description="True when planner decides there's enough information"
    )
    
    # ========================================================================
    # Results & Errors (Merged from Branches)
    # ========================================================================
    
    branch_results: Annotated[list[BranchResult], add] = Field(
        default_factory=list,
        description=(
            "Results from subgraph branches. "
            "REDUCER: Uses add to merge when multiple Send return concurrently"
        )
    )
    
    errors: Annotated[list[BranchError], add] = Field(
        default_factory=list,
        description=(
            "Errors from branches that exceeded retry. "
            "REDUCER: Uses add to merge"
        )
    )
    
    # ========================================================================
    # Output
    # ========================================================================
    
    final_answer: str = Field(
        default="",
        description="Final answer from synthesizer"
    )
    
    # ========================================================================
    # Config
    # ========================================================================
    
    class Config:
        arbitrary_types_allowed = True  # Allow Annotated types


# ============================================================================
# Helper Functions
# ============================================================================

def build_planner_view(state: MainState) -> dict:
    """
    Build minimal view for planner node.
    
    Planner doesn't see full state to avoid token bloat.
    Only extracts necessary fields.
    
    Args:
        state: Current MainState
        
    Returns:
        dict with: query, rewritten_query, iteration, completed_tasks, errors
    """
    
    return {
        "query": state.query,
        "rewritten_query": state.rewritten_query,
        "iteration": state.iteration,
        "max_iterations": state.max_iterations,
        "completed_tasks": [
            {
                "task_id": r.task_id,
                "data_type": r.data_type,
                "status": r.status,
            }
            for r in state.branch_results
        ],
        "errors": [
            {
                "task_id": e.task_id,
                "data_type": e.data_type,
                "error": e.error_message,
                "retry_count": e.retry_count,
            }
            for e in state.errors
        ],
    }
