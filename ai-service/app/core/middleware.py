"""
Custom middleware.

RequestLoggingMiddleware
  • Assigns a short request-id to every request.
  • Logs incoming request and outgoing response with latency.
  • Adds ``X-Request-ID`` header to the response.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request/response with a unique request-id and latency."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id

        start = time.perf_counter()

        logger.info(
            "→ %s %s",
            request.method,
            request.url.path,
            extra={"request_id": request_id},
        )

        try:
            response: Response = await call_next(request)

            latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "← %s %s [%s] %dms",
                request.method,
                request.url.path,
                response.status_code,
                latency_ms,
                extra={"request_id": request_id, "latency_ms": latency_ms},
            )

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "✗ %s %s ERROR %dms — %s",
                request.method,
                request.url.path,
                latency_ms,
                exc,
                extra={"request_id": request_id},
            )
            raise
