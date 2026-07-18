"""
Ingest Module

Markdown ingestion into the hybrid search stores (vector + BM25 + chunk store).
"""

from app.services.ingest_data.ingest.service import (
    DefaultIngestService,
    IngestService,
)

__all__ = ["DefaultIngestService", "IngestService"]
