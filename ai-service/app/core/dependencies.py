"""
Dependency Injection — the ONLY place that decides which concrete class to use.

When adding a new agent:
    1. Create a class inheriting AgentService in services/rag/
    2. Change get_agent_service() below → return YourNewAgent(get_settings())
    3. DONE. No other file is affected.

This is the single point of change for the entire service.
"""

from functools import lru_cache

from app.config import get_settings
from app.services.base import AgentService, IngestService


@lru_cache
def get_agent_service() -> AgentService:
    """
    Singleton agent service.

    LLM models are selected via tier-based system (cheap/middle/strong)
    configured in .env (LLM_CHEAP_TIER, LLM_MIDDLE_TIER, LLM_STRONG_TIER).
    Handled inside RAGService via create_llm() factory with automatic fallback.
    """
    from app.services.rag import RAGService

    return RAGService(get_settings())


@lru_cache
def get_ingest_service() -> IngestService:
    """
    Singleton ingest service.
    
    Returns the default implementation.
    Can be extended with different implementations based on config.
    """
    from app.services.ingest_data.ingest import IngestService as DefaultIngestService

    return DefaultIngestService(get_settings())


@lru_cache
def get_update_service() -> IngestService:
    """
    Singleton update service.
    
    Handles data synchronization operations.
    """
    from app.services.ingest_data.update import UpdateService

    return UpdateService(get_settings())
