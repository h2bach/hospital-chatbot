"""
Data Ingestion Module

Contains all logic for data ingestion and management:
- Ingest: Data fetching and processing
- Update: Data synchronization and updates
"""

from app.services.ingest_data.ingest.service import IngestService
from app.services.ingest_data.update.service import UpdateService

__all__ = ["IngestService", "UpdateService"]
