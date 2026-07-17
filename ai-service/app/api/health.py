"""
GET /health — lightweight liveness / readiness probe.

Backend calls this to verify the AI service is running.
Returns 200 ``{"status": "ok", ...}`` when healthy.
"""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.schemas.response import HealthResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service status and version.",
)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """
    Health check endpoint.
    
    Returns service status and configured model for 'other' provider.
    """
    # Return default 'other' provider model as representative
    model_info = f"other:{settings.other_model}"
    
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        model=model_info,
    )
