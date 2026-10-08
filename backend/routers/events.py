"""
API Router for Weather Events.
Provides production-ready endpoints for listing, filtering, and retrieving weather events
from PostgreSQL (Supabase) adhering to docs/api-contract.md.
"""

from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
import psycopg

from database import get_db_connection, sanitize_error_message
from schemas.events import (
    VALID_CREDIBILITY_STATUSES,
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    VALID_VERIFICATION_STATUSES,
    PaginatedEventsResponse,
    PaginationMetadata,
    WeatherEventResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["Weather Events"])

# Common column list for SELECT queries
EVENT_COLUMNS = """
    event_id,
    source,
    event_type,
    description,
    event_timestamp,
    latitude,
    longitude,
    city,
    district,
    state,
    temperature,
    rainfall,
    humidity,
    wind_speed,
    wind_direction,
    pressure,
    image_url,
    video_url,
    source_url,
    verification_status,
    confidence_score,
    duplicate_of,
    created_at,
    credibility_score,
    credibility_status,
    credibility_reasons,
    source_trust_score
"""



def map_row_to_event(row: tuple) -> WeatherEventResponse:
    """
    Map a PostgreSQL tuple from EVENT_COLUMNS to a validated WeatherEventResponse.
    """
    return WeatherEventResponse(
        event_id=str(row[0]),
        source=row[1],
        event_type=row[2],
        description=row[3],
        event_timestamp=row[4],
        latitude=float(row[5]) if row[5] is not None else None,
        longitude=float(row[6]) if row[6] is not None else None,
        city=row[7],
        district=row[8],
        state=row[9],
        temperature=float(row[10]) if row[10] is not None else None,
        rainfall=float(row[11]) if row[11] is not None else None,
        humidity=float(row[12]) if row[12] is not None else None,
        wind_speed=float(row[13]) if row[13] is not None else None,
        wind_direction=float(row[14]) if row[14] is not None else None,
        pressure=float(row[15]) if row[15] is not None else None,
        image_url=row[16],
        video_url=row[17],
        source_url=row[18],
        verification_status=row[19],
        confidence_score=float(row[20]) if row[20] is not None else None,
        duplicate_of=str(row[21]) if row[21] is not None else None,
        created_at=row[22],
        credibility_score=float(row[23]) if row[23] is not None else None,
        credibility_status=str(row[24]) if row[24] is not None else None,
        credibility_reasons=list(row[25]) if row[25] is not None else None,
        source_trust_score=float(row[26]) if row[26] is not None else None,
    )


@router.get(
    "",
    response_model=PaginatedEventsResponse,
    status_code=status.HTTP_200_OK,
    summary="List Weather Events",
    description=(
        "Retrieve paginated weather events collected from real data sources (Open-Meteo, Citizen Reports, etc.). "
        "Supports filtering by event_type, source, verification_status, credibility_status, state, district, city, "
        "and observation time windows. Orders results newest first."
    ),
)
async def list_weather_events(
    event_type: Optional[str] = Query(None, description="Exact match on weather event type"),
    source: Optional[str] = Query(None, description="Exact match on data source"),
    verification_status: Optional[str] = Query(None, description="Exact match on verification status"),
    credibility_status: Optional[str] = Query(None, description="Exact match on credibility status"),
    state: Optional[str] = Query(None, description="Case-insensitive match on state name"),
    district: Optional[str] = Query(None, description="Case-insensitive match on district name"),
    city: Optional[str] = Query(None, description="Case-insensitive match on city name"),
    start_time: Optional[datetime] = Query(None, description="Inclusive start boundary for event_timestamp (ISO-8601)"),
    end_time: Optional[datetime] = Query(None, description="Inclusive end boundary for event_timestamp (ISO-8601)"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed, minimum 1)"),

    page_size: int = Query(default=50, ge=1, le=100, description="Records per page (minimum 1, maximum 100)"),
) -> PaginatedEventsResponse:
    """
    Handle GET /api/events with server-side filtering, sorting, and pagination.
    """
    # 1. Validate categorical filters against known system constants
    if event_type is not None:
        trimmed_type = event_type.strip()
        if trimmed_type not in VALID_EVENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event_type '{event_type}'. Allowed values: {', '.join(sorted(VALID_EVENT_TYPES))}",
            )
        event_type = trimmed_type

    if source is not None:
        trimmed_source = source.strip()
        if trimmed_source not in VALID_SOURCES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source '{source}'. Allowed values: {', '.join(sorted(VALID_SOURCES))}",
            )
        source = trimmed_source

    if verification_status is not None:
        trimmed_status = verification_status.strip()
        if trimmed_status not in VALID_VERIFICATION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid verification_status '{verification_status}'. Allowed values: {', '.join(sorted(VALID_VERIFICATION_STATUSES))}",
            )
        verification_status = trimmed_status

    if credibility_status is not None:
        trimmed_cred = credibility_status.strip()
        if trimmed_cred not in VALID_CREDIBILITY_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid credibility_status '{credibility_status}'. Allowed values: {', '.join(sorted(VALID_CREDIBILITY_STATUSES))}",
            )
        credibility_status = trimmed_cred

    # 2. Validate time range boundaries
    if start_time is not None and end_time is not None:
        # Normalize naive timestamps to UTC for safe comparison
        norm_start = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
        norm_end = end_time if end_time.tzinfo else end_time.replace(tzinfo=timezone.utc)
        if norm_start > norm_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_time cannot be greater than end_time.",
            )

    # 3. Construct parameterized SQL query
    where_clauses: List[str] = []
    params: Dict[str, Any] = {}

    if event_type is not None:
        where_clauses.append("event_type = %(event_type)s")
        params["event_type"] = event_type

    if source is not None:
        where_clauses.append("source = %(source)s")
        params["source"] = source

    if verification_status is not None:
        where_clauses.append("verification_status = %(verification_status)s")
        params["verification_status"] = verification_status

    if credibility_status is not None:
        where_clauses.append("credibility_status = %(credibility_status)s")
        params["credibility_status"] = credibility_status


    if state is not None and state.strip():
        where_clauses.append("LOWER(state) = LOWER(%(state)s)")
        params["state"] = state.strip()

    if district is not None and district.strip():
        where_clauses.append("LOWER(district) = LOWER(%(district)s)")
        params["district"] = district.strip()

    if city is not None and city.strip():
        where_clauses.append("LOWER(city) = LOWER(%(city)s)")
        params["city"] = city.strip()

    if start_time is not None:
        where_clauses.append("event_timestamp >= %(start_time)s")
        params["start_time"] = start_time

    if end_time is not None:
        where_clauses.append("event_timestamp <= %(end_time)s")
        params["end_time"] = end_time

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_sql = f"SELECT COUNT(*) FROM public.weather_events {where_sql};"

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT {EVENT_COLUMNS}
        FROM public.weather_events
        {where_sql}
        ORDER BY event_timestamp DESC, event_id DESC
        LIMIT %(limit)s OFFSET %(offset)s;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Execute COUNT query
                cur.execute(count_sql, params)
                total_row = cur.fetchone()
                total = total_row[0] if total_row else 0

                # Execute paginated data query
                query_params = {**params, "limit": page_size, "offset": offset}
                cur.execute(data_sql, query_params)
                rows = cur.fetchall()

        events_data = [map_row_to_event(r) for r in rows]
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return PaginatedEventsResponse(
            data=events_data,
            pagination=PaginationMetadata(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )

    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Database error in list_weather_events: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Failed to fetch weather events.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Unexpected error in list_weather_events: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving weather events.",
        )


@router.get(
    "/{event_id}",
    response_model=WeatherEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Single Weather Event",
    description="Retrieve the complete record for a single weather event by its unique UUID.",
)
async def get_weather_event_by_id(event_id: str) -> WeatherEventResponse:
    """
    Handle GET /api/events/{event_id}:
    - Validates UUID syntax.
    - Queries public.weather_events by event_id.
    - Returns HTTP 404 if not found.
    """
    # Validate UUID format
    try:
        parsed_uuid = uuid.UUID(event_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Weather event with ID '{event_id}' not found.",
        )

    query_sql = f"""
        SELECT {EVENT_COLUMNS}
        FROM public.weather_events
        WHERE event_id = %(event_id)s;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_sql, {"event_id": str(parsed_uuid)})
                row = cur.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Weather event with ID '{event_id}' not found.",
            )

        return map_row_to_event(row)

    except HTTPException:
        raise
    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Database error in get_weather_event_by_id: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Failed to fetch weather event.",
        )
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Unexpected error in get_weather_event_by_id: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving the weather event.",
        )
