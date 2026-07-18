"""
Service abstractions — the ONLY thing the API layer depends on.

Rules:
    - API layer imports ONLY from this file (AgentService, IngestService).
    - Concrete implementations live in services/agents/ and services/ingest.py.
    - DI layer (core/dependencies.py) wires concrete → abstraction.

SOLID compliance:
    - S: Each ABC defines a single responsibility.
    - O: New agents extend AgentService — no existing code changes.
    - L: Any AgentService subclass is substitutable via DI.
    - I: invoke() and stream() are the minimal interface.
    - D: API layer depends on abstractions, not concretions.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from app.config import Settings


class AgentService(ABC):
    """
    Abstract base for all AI agents.

    Every agent (chatbot, RAG, multi-agent, ...) MUST implement:
        - invoke()  → full response
        - stream()  → token-by-token (SSE-ready)

    API layer calls ONLY these 2 methods — it never knows
    what framework or model runs inside.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    async def invoke(self, message: str, **kwargs: Any) -> dict:
        """
        Process a message and return the complete result.

        Returns:
            dict with keys: answer (str), model (str),
                            usage (dict | None), latency_ms (float)
        """
        ...

    async def retrieve(
        self, query: str, top_k: int | None = None, **kwargs: Any
    ) -> dict:
        """
        Retrieve relevant context for a query (retrieval-only services).

        Default implementation delegates to invoke(); retrieval services
        override this to return contexts + citations + timings.
        """
        return await self.invoke(query, top_k=top_k, **kwargs)

    @abstractmethod
    async def stream(self, message: str, **kwargs: Any) -> AsyncIterator[str]:
        """
        Process a message and yield tokens one-by-one.

        Yields:
            str — individual text tokens / chunks
        """
        ...
        # Trick: must have a yield in body for AsyncIterator type hint
        yield  # pragma: no cover


class IngestService(ABC):
    """
    Abstract base for data ingestion services.

    Handles fetching data from backend APIs, processing,
    and storing in the vector database or search index.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    async def ingest(
        self,
        data_source_api: str,
        data_type: str,
        auth_token: str | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Ingest data from a backend API.

        Args:
            data_source_api: Backend API endpoint to fetch data from
            data_type: Type of data being ingested
            auth_token: Optional authentication token
            metadata: Additional metadata for processing

        Returns:
            dict with keys: status (str), records_fetched (int),
                            records_processed (int), job_id (str | None),
                            message (str | None), latency_ms (float)
        """
        ...

    @abstractmethod
    async def update(
        self,
        operation: str,
        data_type: str,
        record_ids: list[str],
        data_source_api: str | None = None,
        metadata: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """
        Update or delete existing records in the vector store.

        Args:
            operation: 'create', 'update', or 'delete'
            data_type: Type of data being updated
            record_ids: List of record IDs to update/delete
            data_source_api: Optional API to fetch updated data
            metadata: Additional context

        Returns:
            dict with keys: status (str), records_affected (int),
                            records_updated (int), records_failed (int),
                            failed_ids (list[str]), message (str | None),
                            latency_ms (float)
        """
        ...
