"""
API Router for Citizen Weather Reports.
Implements POST /api/reports following docs/api-contract.md.
"""

import logging
from fastapi import APIRouter, HTTPException, status

from database import sanitize_error_message
from schemas.reports import CitizenReportCreate, CitizenReportResponse
from services.citizen_report_service import process_and_store_citizen_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["Citizen Reports"])


@router.post(
    "",
    response_model=CitizenReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Citizen Weather Report",
    description=(
        "Allows citizens to submit ground-level weather observations. "
        "Validates coordinates and required fields, reverse-geocodes administrative location "
        "(city, district, state), evaluates spatio-temporal duplicates, and stores the report safely in PostgreSQL."
    ),
)
async def submit_citizen_report(report: CitizenReportCreate) -> CitizenReportResponse:
    """
    Handle POST /api/reports:
    - Validates latitude (-90 to 90) and longitude (-180 to 180) via Pydantic.
    - Validates event_type and description are non-empty strings.
    - Reverse geocodes coordinates to automatically determine city, district, and state.
    - Evaluates geographic and temporal duplicate criteria against existing events.
    - Persists report to public.weather_events with source='Citizen_Report'.
    - Returns event_id and status='received'.
    """
    try:
        result = await process_and_store_citizen_report(report)
        return CitizenReportResponse(
            event_id=result["event_id"],
            status=result["status"],
        )
    except RuntimeError as exc:
        sanitized_msg = sanitize_error_message(str(exc))
        logger.error("Database failure while handling citizen report: %s", sanitized_msg)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Failed to store citizen weather report.",
        )
    except Exception as exc:
        sanitized_msg = sanitize_error_message(str(exc))
        logger.error("Unexpected error in submit_citizen_report: %s", sanitized_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the report.",
        )
