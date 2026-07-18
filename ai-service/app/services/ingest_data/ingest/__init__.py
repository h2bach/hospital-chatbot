"""
Ingest Module

Handles data fetching from backend APIs and processing for vector storage.
"""

from app.services.ingest_data.ingest.service import DefaultIngestService as IngestService

__all__ = ["IngestService"]
