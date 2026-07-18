"""
Data Ingestion Module

Contains all logic for data ingestion and management:
- Ingest: Data fetching and processing
- Update: Data synchronization and updates
"""

from app.services.ingest_data.ingest.service import (
    DefaultIngestService,
    IngestService,
)

__all__ = ["DefaultIngestService", "IngestService"]
