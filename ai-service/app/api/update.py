"""
POST /update — Update or delete data in vector store

This endpoint handles data changes (create, update, delete) and
keeps the vector store synchronized with the backend database.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_update_service
from app.schemas.request import UpdateDataRequest
from app.schemas.response import ErrorResponse, UpdateDataResponse
from app.services.base import IngestService

router = APIRouter(prefix="/update", tags=["Update"])


@router.post(
    "",
    response_model=UpdateDataResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Update error"},
    },
    summary="Update or delete data",
    description=(
        "Handle data changes in the vector store. Supports create, update, and delete "
        "operations. The service will synchronize changes with the vector database."
    ),
)
async def update_data(
    request: UpdateDataRequest,
    svc: IngestService = Depends(get_update_service),
) -> UpdateDataResponse:
    """
    Update or delete records in the vector store.
    
    Operations:
    - 'create': Add new records to the vector store
    - 'update': Fetch updated data and re-embed
    - 'delete': Remove records from the vector store
    """
    result = await svc.update(
        operation=request.operation,
        data_type=request.data_type,
        record_ids=request.record_ids,
        data_source_api=request.data_source_api,
        metadata=request.metadata,
    )
    
    return UpdateDataResponse(**result, operation=request.operation, data_type=request.data_type)
