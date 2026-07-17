"""
Type1State - State for SQL/structured data subgraph.

Following ARCHITECTURE.md Section 4.3.
"""

from pydantic import BaseModel, Field


class Type1State(BaseModel):
    """
    State for Type1 subgraph - SQL/Structured data retrieval.
    
    Flow:
    1. Receive query + parameters from planner
    2. Generate/receive SQL query
    3. Execute SQL via backend API
    4. Validate and format results
    5. Return content
    """
    
    # ========================================================================
    # General Fields (common across all DType states)
    # ========================================================================
    
    task_id: str = Field(
        ...,
        description="Task ID from planner"
    )
    
    graph_id: str = Field(
        default="type1",
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
    # Type1-Specific Fields
    # ========================================================================
    
    query: str = Field(
        default="",
        description="Query from planner"
    )
    
    parameters: dict = Field(
        default_factory=dict,
        description="Parameters from Task.parameters"
    )
    
    sql_query: str = Field(
        default="",
        description="Generated SQL query"
    )
    
    raw_results: list[dict] = Field(
        default_factory=list,
        description="Raw data from SQL execution"
    )
    
    content: str = Field(
        default="",
        description="Formatted content for final answer"
    )
