"""
Global exception handlers.

Converts common AI/LLM exceptions into standardised JSON error responses
so the backend team always gets a predictable error shape.

Status codes:
    429 — RATE_LIMITED   (too many requests)
    500 — INTERNAL_ERROR (unhandled bug)
    502 — LLM_ERROR      (upstream LLM failure)
    504 — LLM_TIMEOUT    (model didn't respond in time)
"""

import logging
from asyncio import TimeoutError as AsyncTimeoutError

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.response import ErrorResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def timeout_handler(request: Request, exc: AsyncTimeoutError) -> JSONResponse:
    logger.error("LLM timeout: %s", exc)
    return JSONResponse(
        status_code=504,
        content=ErrorResponse(
            error="LLM_TIMEOUT",
            detail="AI model did not respond in time. Please try again.",
            request_id=_request_id(request),
        ).model_dump(mode="json"),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    debug = getattr(request.app.state, "debug", False)

    # Detect rate limit errors from any provider
    exc_str = str(exc).lower()
    if "rate" in exc_str and "limit" in exc_str:
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                error="RATE_LIMITED",
                detail="Too many requests to AI model. Please wait and retry.",
                request_id=_request_id(request),
            ).model_dump(mode="json"),
        )

    # Detect timeout errors
    if "timeout" in exc_str or isinstance(exc, (TimeoutError, AsyncTimeoutError)):
        return JSONResponse(
            status_code=504,
            content=ErrorResponse(
                error="LLM_TIMEOUT",
                detail="AI model did not respond in time. Please try again.",
                request_id=_request_id(request),
            ).model_dump(mode="json"),
        )

    # Generic error
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="INTERNAL_ERROR",
            detail=str(exc) if debug else "An unexpected error occurred.",
            request_id=_request_id(request),
        ).model_dump(mode="json"),
    )
