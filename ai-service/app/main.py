"""
FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload

Swagger UI:
    http://localhost:8000/docs
"""

import asyncio
import logging
import time
from asyncio import TimeoutError as AsyncTimeoutError
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.core.exceptions import general_exception_handler, timeout_handler
from app.core.middleware import RequestLoggingMiddleware
from app.utils.logger import setup_logging

logger = logging.getLogger(__name__)


# ── Startup helpers ──────────────────────────────────────────────────────────

async def _preload_stores(settings) -> None:
    """Create and warm all storage singletons (Chroma, BM25, SQLite, embedder)."""
    from app.services.ingest_data.stores import get_stores
    t = time.perf_counter()
    stores = get_stores(settings)
    # Warm httpx connection pool + load nomic into Ollama VRAM
    await asyncio.to_thread(stores.embedder.warmup)
    logger.info("Stores ready in %.0fms", (time.perf_counter() - t) * 1000)


async def _preload_rag_service(settings) -> None:
    """
    Build + compile LangGraph, create LLM singleton, run one real warm request.

    This moves ALL cold-start work to startup:
      - Graph StateGraph.compile()        (~50-200ms)
      - create_query_transform_llm()      (object creation, ~0ms)
      - RAGService.warmup() ainvoke       (loads qwen into VRAM, ~2-4s first time)
    After this, every request hits only warm paths.
    """
    from app.core.dependencies import get_agent_service
    t = time.perf_counter()
    svc = get_agent_service()          # triggers lru_cache → RAGService.__init__
    await svc.warmup()                 # one real LLM + search round-trip
    logger.info("RAGService ready in %.0fms", (time.perf_counter() - t) * 1000)


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Production startup sequence — ALL heavy work runs BEFORE yield.

    Order matters:
      1. Config + logging          (cheap, synchronous)
      2. Stores + embedder warmup  (opens httpx pool, loads nomic into VRAM)
      3. RAGService + graph + LLM  (compiles graph, loads qwen into VRAM)
      4. Set ready flag            (only now does /ready return 200)

    Steps 2 and 3 run concurrently (asyncio.gather) to overlap:
      - nomic-embed-text loading
      - graph compilation + LLM object construction
    The warmup ainvoke in step 3 starts AFTER nomic is ready (sequential within
    step 3) to avoid GPU contention between two model loads.
    """
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.debug = settings.debug
    app.state.ready = False

    startup_start = time.perf_counter()
    logger.info("Server startup — preloading all singletons...")

    try:
        # Stores (embed warmup) and RAGService (graph compile + LLM build) in parallel.
        await asyncio.gather(
            _preload_stores(settings),
            _preload_rag_service(settings),
        )
    except Exception as exc:
        # Startup failure: log and re-raise so uvicorn marks the process unhealthy.
        logger.error("Startup preload failed: %s", exc, exc_info=True)
        raise

    app.state.ready = True
    logger.info(
        "Server READY — total startup %.0fms",
        (time.perf_counter() - startup_start) * 1000,
    )

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Server shutting down")
    app.state.ready = False
    try:
        from app.services.ingest_data.stores import get_stores
        stores = get_stores(settings)
        # Persist BM25 index if it was modified during this session.
        await asyncio.to_thread(stores.bm25_store.save)
        # Close persistent httpx connection pool cleanly.
        stores.embedder._client and stores.embedder._client.close()
    except Exception as exc:
        logger.warning("Shutdown cleanup error (non-fatal): %s", exc)


# ── App ──────────────────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "RAG Service API — Production-ready data ingestion and retrieval service.\n\n"
        "Endpoints:\n"
        "- **GET /health** — Liveness probe (always 200 when process is up)\n"
        "- **GET /ready**  — Readiness probe (200 only after full startup warmup)\n"
        "- **POST /retrieve** — Retrieve context from vector store\n"
        "- **POST /ingest** — Ingest data from backend API\n"
        "- **POST /update** — Update or delete data in vector store\n"
    ),
    lifespan=lifespan,
)


# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


# ── Exception Handlers ───────────────────────────────────────────────────────

app.add_exception_handler(AsyncTimeoutError, timeout_handler)
app.add_exception_handler(Exception, general_exception_handler)


# ── Routes ───────────────────────────────────────────────────────────────────

app.include_router(api_router)

