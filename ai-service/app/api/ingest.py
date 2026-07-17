"""
POST /ingest — Ingest data from backend API

This endpoint receives a message from backend to start data ingestion.
It fetches data from the backend's data storage API and processes it.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_ingest_service
from app.schemas.request import IngestRequest
from app.schemas.response import ErrorResponse, IngestResponse
from app.services.base import IngestService

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


@router.post(
    "",
    response_model=IngestResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Ingestion error"},
        502: {"model": ErrorResponse, "description": "Backend API error"},
    },
    summary="Ingest data from backend",
    description=(
        "Start a data ingestion job. The service will fetch data from the provided "
        "backend API endpoint, process it, and store it in the vector database."
    ),
)
async def ingest_data(
    request: IngestRequest,
    svc: IngestService = Depends(get_ingest_service),
) -> IngestResponse:
    """
    Ingest data from backend API.
    
    The service will:
    1. Call the backend API to fetch data
    2. Process and chunk the data based on data_type
    3. Store in vector database
    """
    result = await svc.ingest(
        data_source_api=request.data_source_api,
        data_type=request.data_type,
        auth_token=request.auth_token,
        metadata=request.metadata,
    )
    
    return IngestResponse(**result, data_type=request.data_type)
