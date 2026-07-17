"""
Type2State - State for Vector search subgraph.

Placeholder - to be implemented later.
"""

from pydantic import BaseModel, Field


class Type2State(BaseModel):
    """
    State for Type2 subgraph - Vector similarity search.
    
    Placeholder implementation. Full implementation will include:
    1. Query embedding
    2. Vector search
    3. Reranking (optional)
    4. Result formatting
    
    TODO: Implement when Type2 subgraph is needed
    """
    
    # ========================================================================
    # General Fields
    # ========================================================================
    
    task_id: str = Field(
        ...,
        description="Task ID from planner"
    )
    
    graph_id: str = Field(
        default="type2",
        description="Fixed graph identifier"
    )
    
    status: str = Field(
        default="none",
        description="Execution status: none | running | success | failed"
    )
    
    error: str | None = Field(
        default=None,
        description="Error message if execution failed"
    )
    
    retry_count: int = Field(
        default=0,
        description="Number of retries attempted (max 3)"
    )
    
    latency: float = Field(
        default=0.0,
        description="Execution time in seconds"
    )
    
    token_usage: int = Field(
        default=0,
        description="Total LLM tokens used"
    )
    
    # ========================================================================
    # Type2-Specific Fields (Placeholder)
    # ========================================================================
    
    query: str = Field(
        default="",
        description="Query from planner"
    )
    
    parameters: dict = Field(
        default_factory=dict,
        description="Parameters from Task.parameters"
    )
    
    documents: list[dict] = Field(
        default_factory=list,
        description="Retrieved documents with scores"
    )
    
    content: str = Field(
        default="",
        description="Formatted content for final answer"
    )
