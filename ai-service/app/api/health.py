"""
Liveness and readiness probes.

  GET /health — Liveness: 200 as soon as the process is up. Used by orchestrators
                to decide whether to RESTART the container.
  GET /ready  — Readiness: 200 only AFTER startup preload/warmup finished. Used by
                load balancers to decide whether to ROUTE traffic. Returns 503 while
                the graph/LLM/stores are still warming — this is what prevents the
                first real request from hitting a cold pipeline.
"""

from fastapi import APIRouter, Depends, Request, Response, status

from app.config import Settings, get_settings
from app.schemas.response import HealthResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 whenever the process is running.",
)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness — always ok while the process is alive."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        model=f"other:{settings.other_model}",
    )


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Returns 200 only after startup warmup completes; 503 otherwise.",
)
async def ready(request: Request, response: Response) -> dict:
    """
    Readiness — reflects app.state.ready set by the lifespan handler.

    Load balancers should gate traffic on this, NOT on /health.
    """
    is_ready = getattr(request.app.state, "ready", False)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "warming_up", "ready": False}
    return {"status": "ready", "ready": True}
