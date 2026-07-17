"""
Type3State - State for Graph/Knowledge Graph subgraph.

Placeholder - to be implemented later.
"""

from pydantic import BaseModel, Field


class Type3State(BaseModel):
    """
    State for Type3 subgraph - Graph/Knowledge graph traversal.
    
    Placeholder implementation. Full implementation will include:
    1. Graph query building (Cypher/SPARQL)
    2. Graph traversal
    3. Node/edge extraction
    4. Result formatting
    
    TODO: Implement when Type3 subgraph is needed
    """
    
    # ========================================================================
    # General Fields
    # ========================================================================
    
    task_id: str = Field(
        ...,
        description="Task ID from planner"
    )
    
    graph_id: str = Field(
        default="type3",
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
    # Type3-Specific Fields (Placeholder)
    # ========================================================================
    
    query: str = Field(
        default="",
        description="Query from planner"
    )
    
    parameters: dict = Field(
        default_factory=dict,
        description="Parameters from Task.parameters"
    )
    
    nodes: list[dict] = Field(
        default_factory=list,
        description="Retrieved graph nodes"
    )
    
    edges: list[dict] = Field(
        default_factory=list,
        description="Retrieved graph edges/relationships"
    )
    
    content: str = Field(
        default="",
        description="Formatted content for final answer"
    )
