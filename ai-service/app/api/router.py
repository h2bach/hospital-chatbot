"""
Central router — collects all sub-routers in one place.
"""

from fastapi import APIRouter

from app.api import ingest, health, retrieve, update

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(retrieve.router)
api_router.include_router(ingest.router)
api_router.include_router(update.router)