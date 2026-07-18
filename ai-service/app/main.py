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
    import logging
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.debug = settings.debug

    logger = logging.getLogger(__name__)
    logger.info("AI Service starting — pre-initializing resources...")

    # 1. Pre-build RAG graph + compile LangGraph (heaviest op, ~3s)
    from app.core.dependencies import get_agent_service, get_ingest_service
    agent_svc = get_agent_service()
    logger.info("RAG graph pre-compiled")

    # 2. Warm up LLM tier cache: verify API keys and cache instances
    from app.services.rag.llm_factory import create_tier_llm
    for tier in ("strong", "middle"):
        try:
            create_tier_llm(settings, tier=tier)
            logger.info("LLM tier '%s' warmed up", tier)
        except Exception as exc:
            logger.warning("LLM tier '%s' warmup failed: %s", tier, exc)

    # 3. Pre-load storage backends (ChromaDB + BM25 deserialize from disk)
    ingest_svc = get_ingest_service()
    try:
        _ = ingest_svc._vector_store   # trigger ChromaDB init
        _ = ingest_svc._bm25_store     # trigger BM25 pickle load
        _ = ingest_svc._chunk_store    # trigger SQLite init
        logger.info("Storage backends loaded (ChromaDB, BM25, SQLite)")
    except Exception as exc:
        logger.warning("Storage backend warmup failed: %s", exc)

    logger.info("AI Service ready — all resources initialized")
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
        "- **POST /retrieve** — Run full RAG pipeline, return synthesized answer\n"
        "- **POST /ingest** — Ingest data from backend API into vector store\n"
        "- **POST /update** — Synchronize create/update/delete changes in vector store\n"
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
