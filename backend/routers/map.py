"""
API Router for Weather Events Map Visualization.
Provides lightweight geospatial endpoints specifically optimized for rendering weather event
markers on the frontend map.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
import psycopg

from database import get_db_connection, sanitize_error_message
from schemas.events import (
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    VALID_VERIFICATION_STATUSES,
)
from schemas.map import MapEvent, MapEventResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["Weather Events Map"])


def map_row_to_map_event(row: tuple) -> MapEvent:
    """
    Map a PostgreSQL tuple from map query to a validated MapEvent.
    """
    (
        event_id,
        latitude,
        longitude,
        event_type,
        source,
        event_timestamp,
        city,
        district,
        state,
        verification_status,
        confidence_score,
    ) = row

    return MapEvent(
        event_id=str(event_id),
        latitude=float(latitude),
        longitude=float(longitude),
        event_type=str(event_type),
        source=str(source),
        event_timestamp=event_timestamp,
        city=city if city is not None else None,
        district=district if district is not None else None,
        state=state if state is not None else None,
        verification_status=str(verification_status),
        confidence_score=float(confidence_score) if confidence_score is not None else None,
    )


@router.get(
    "/map",
    response_model=MapEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Weather Events for Map Visualization",
    description=(
        "Retrieve lightweight geospatial weather events for frontend map marker visualization. "
        "Only returns records with valid non-null coordinates within geographic boundaries (-90 to 90 lat, -180 to 180 lon). "
        "Supports filtering by event type, source, verification status, location (state/district/city), "
        "time range, and an optional 2D geographic bounding box (min_lat, max_lat, min_lon, max_lon). "
        "Results are ordered newest first (event_timestamp DESC, event_id DESC) with a configurable limit (default 1000, max 5000)."
    ),
)
async def get_weather_events_map(
    event_type: Optional[str] = Query(None, description="Exact match filter by event type."),
    source: Optional[str] = Query(None, description="Exact match filter by data source origin."),
    verification_status: Optional[str] = Query(None, description="Exact match filter by verification status."),
    state: Optional[str] = Query(None, description="Case-insensitive filter by state."),
    district: Optional[str] = Query(None, description="Case-insensitive filter by district."),
    city: Optional[str] = Query(None, description="Case-insensitive filter by city."),
    start_time: Optional[datetime] = Query(None, description="Filter events on or after this ISO-8601 timestamp."),
    end_time: Optional[datetime] = Query(None, description="Filter events on or before this ISO-8601 timestamp."),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Minimum latitude bounding box boundary (-90 to 90)."),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Maximum latitude bounding box boundary (-90 to 90)."),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Minimum longitude bounding box boundary (-180 to 180)."),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Maximum longitude bounding box boundary (-180 to 180)."),
    limit: int = Query(default=1000, ge=1, le=5000, description="Maximum number of markers to return (1-5000, default: 1000)."),
) -> MapEventResponse:
    """
    Handle GET /api/events/map:
    - Strictly enforces valid coordinate ranges in SQL.
    - Validates categorical parameters against known taxonomy.
    - Validates bounding-box coordinates (all 4 required when used, min < max).
    - Validates time window (start_time <= end_time).
    - Executes parameterized SQL and returns lightweight MapEventResponse.
    """
    # 1. Categorical parameter validation
    if event_type is not None and event_type not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event_type '{event_type}'. Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}",
        )

    if source is not None and source not in VALID_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source '{source}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}",
        )

    if verification_status is not None and verification_status not in VALID_VERIFICATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification_status '{verification_status}'. Must be one of: {', '.join(sorted(VALID_VERIFICATION_STATUSES))}",
        )

    # 2. Time range validation
    if start_time is not None and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time is not None and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid time range: start_time cannot be greater than end_time.",
        )

    # 3. Bounding box validation
    bbox_coords = [min_lat, max_lat, min_lon, max_lon]
    num_bbox_provided = sum(1 for c in bbox_coords if c is not None)
    if 0 < num_bbox_provided < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bounding box filter requires all four coordinates: min_lat, max_lat, min_lon, and max_lon.",
        )

    if num_bbox_provided == 4:
        if min_lat >= max_lat:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid bounding box: min_lat must be strictly less than max_lat.",
            )
        if min_lon >= max_lon:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid bounding box: min_lon must be strictly less than max_lon.",
            )

    # If caller explicitly filters by 'Rejected', return empty response as rejected reports are excluded from map
    if verification_status == "Rejected":
        return MapEventResponse(data=[], count=0)

    # 4. Construct parameterized SQL query
    where_clauses: List[str] = [
        "latitude IS NOT NULL",
        "longitude IS NOT NULL",
        "latitude BETWEEN -90.0 AND 90.0",
        "longitude BETWEEN -180.0 AND 180.0",
        "(verification_status IS NULL OR verification_status != 'Rejected')",
    ]
    params: Dict[str, Any] = {"limit": limit}

    if event_type is not None:
        where_clauses.append("event_type = %(event_type)s")
        params["event_type"] = event_type

    if source is not None:
        where_clauses.append("source = %(source)s")
        params["source"] = source

    if verification_status is not None:
        where_clauses.append("verification_status = %(verification_status)s")
        params["verification_status"] = verification_status

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

    if num_bbox_provided == 4:
        where_clauses.append("latitude >= %(min_lat)s")
        where_clauses.append("latitude <= %(max_lat)s")
        where_clauses.append("longitude >= %(min_lon)s")
        where_clauses.append("longitude <= %(max_lon)s")
        params["min_lat"] = min_lat
        params["max_lat"] = max_lat
        params["min_lon"] = min_lon
        params["max_lon"] = max_lon

    data_sql = f"""
        SELECT
            event_id,
            latitude,
            longitude,
            event_type,
            source,
            event_timestamp,
            city,
            district,
            state,
            verification_status,
            confidence_score
        FROM public.weather_events
        WHERE {' AND '.join(where_clauses)}
        ORDER BY event_timestamp DESC, event_id DESC
        LIMIT %(limit)s;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(data_sql, params)
                rows = cur.fetchall()

        events = [map_row_to_map_event(row) for row in rows]
        return MapEventResponse(data=events, count=len(events))

    except HTTPException:
        raise
    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Database error in get_weather_events_map: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Failed to fetch map weather events.",
        )
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Unexpected error in get_weather_events_map: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving map weather events.",
        )
