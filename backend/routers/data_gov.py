"""
API Router for Data.gov.in integration.
Provides endpoints for connector configuration status, manual ingestion triggers,
and querying district rainfall dataset records.
"""

from datetime import date
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from database import sanitize_error_message
from schemas.data_gov import (
    DataGovConfigStatusResponse,
    DataGovIngestRequest,
    DataGovIngestResponse,
    DataGovRainfallListResponse,
)
from services.data_gov_service import (
    DataGovAPIError,
    DataGovConfigError,
    DataGovNetworkError,
    DataGovResponseError,
    DataGovTimeoutError,
    get_data_gov_config,
    get_data_gov_rainfall_records,
    get_data_gov_status,
    ingest_data_gov_rainfall,
    sanitize_data_gov_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-gov", tags=["Data.gov.in Integration"])


@router.get(
    "/status",
    response_model=DataGovConfigStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Data.gov.in Connector Status",
    description="Inspect whether Data.gov.in API credentials and resource ID are configured without leaking secrets.",
)
async def get_connector_status() -> DataGovConfigStatusResponse:
    """
    Returns current configuration status of the Data.gov.in connector.
    """
    status_dict = get_data_gov_status()
    return DataGovConfigStatusResponse(**status_dict)


@router.get(
    "/records",
    response_model=DataGovRainfallListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Data.gov.in Rainfall Records",
    description="Retrieve paginated rainfall observation records stored in the dedicated dataset table.",
)
async def list_data_gov_records(
    state: Optional[str] = Query(None, description="Case-insensitive State filter."),
    district: Optional[str] = Query(None, description="Case-insensitive District filter."),
    start_date: Optional[date] = Query(None, description="Filter records on or after this date (YYYY-MM-DD)."),
    end_date: Optional[date] = Query(None, description="Filter records on or before this date (YYYY-MM-DD)."),
    limit: int = Query(50, ge=1, le=1000, description="Page size limit."),
    offset: int = Query(0, ge=0, description="Offset pagination index."),
) -> DataGovRainfallListResponse:
    """
    Query records stored in public.data_gov_rainfall_records table.
    """
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be less than or equal to end_date.",
        )

    try:
        results = get_data_gov_rainfall_records(
            state=state,
            district=district,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return DataGovRainfallListResponse(**results)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


@router.post(
    "/ingest",
    response_model=DataGovIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Manual Data.gov.in Rainfall Ingestion",
    description=(
        "Trigger fetching, validating, and persisting daily rainfall data from Data.gov.in. "
        "Supports dry-run validation and duplicate prevention."
    ),
)
async def trigger_data_gov_ingestion(
    request: DataGovIngestRequest,
) -> DataGovIngestResponse:
    """
    Execute on-demand ingestion cycle for Data.gov.in rainfall data.
    """
    if request.target_table not in ("data_gov_rainfall_records", "weather_events"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid target_table '{request.target_table}'. "
                "Allowed options: 'data_gov_rainfall_records', 'weather_events'."
            ),
        )

    try:
        result = await ingest_data_gov_rainfall(
            resource_id=request.resource_id,
            limit=request.limit,
            offset=request.offset,
            filters=request.filters,
            target_table=request.target_table,
            skip_if_exists=request.skip_if_exists,
            dry_run=request.dry_run,
        )
        return DataGovIngestResponse(**result)

    except DataGovConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except DataGovTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        )
    except (DataGovNetworkError, DataGovAPIError, DataGovResponseError) as exc:
        sanitized = sanitize_data_gov_message(str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=sanitized,
        )
    except Exception as exc:
        sanitized = sanitize_data_gov_message(str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during Data.gov.in ingestion: {sanitized}",
        )
