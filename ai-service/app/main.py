"""
FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload

Swagger UI:
    http://localhost:8000/docs
"""

from asyncio import TimeoutError as AsyncTimeoutError
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.core.exceptions import general_exception_handler, timeout_handler
from app.core.middleware import RequestLoggingMiddleware
from app.utils.logger import setup_logging


# ── Lifespan (startup / shutdown) ────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run once on startup, yield, then run on shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.debug = settings.debug
    yield
    # Cleanup resources here if needed


# ── App ──────────────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "RAG Service API — Production-ready data ingestion and retrieval service.\n\n"
        "Endpoints:\n"
        "- **GET /health** — Service status\n"
        "- **POST /retrieve** — Retrieve context from vector store\n"
        "- **POST /ingest** — Ingest data from backend API\n"
        "- **POST /update** — Update or delete data in vector store\n"
    ),
    lifespan=lifespan,
)


# ── Middleware ───────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hackathon: allow all. Production: restrict.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


# ── Exception Handlers ──────────────────────────────────────────────────

app.add_exception_handler(AsyncTimeoutError, timeout_handler)
app.add_exception_handler(Exception, general_exception_handler)


# ── Routes ───────────────────────────────────────────────────────────────

app.include_router(api_router)
