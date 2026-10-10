"""
API Router for Weather Analytics.
Provides production-ready endpoints for real-data aggregated metrics, verification distributions,
source/type/state breakdowns, and daily time-series analysis directly calculated in PostgreSQL.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
import psycopg

from database import get_db_connection, sanitize_error_message
from schemas.analytics import (
    AnalyticsSummaryResponse,
    DateCountItem,
    EventTypeCountItem,
    SourceCountItem,
    StateCountItem,
    VerificationSummary,
)
from schemas.events import (
    VALID_EVENT_TYPES,
    VALID_SOURCES,
    VALID_VERIFICATION_STATUSES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Weather Analytics"])


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Weather Analytics Summary",
    description=(
        "Calculate real-data aggregate analytics for weather events directly in PostgreSQL. "
        "Returns total matching events, a comprehensive 5-status verification breakdown "
        "(Verified, Likely, Unverified, Rejected, Duplicate), events grouped by type, source, "
        "and state, and a daily time series. Supports optional filtering by event type, "
        "data source, verification status, location (state/district/city), and observation time range."
    ),
)
async def get_analytics_summary(
    event_type: Optional[str] = Query(None, description="Exact match filter by event type."),
    source: Optional[str] = Query(None, description="Exact match filter by origin source."),
    verification_status: Optional[str] = Query(None, description="Exact match filter by verification status."),
    state: Optional[str] = Query(None, description="Case-insensitive filter by state."),
    district: Optional[str] = Query(None, description="Case-insensitive filter by district."),
    city: Optional[str] = Query(None, description="Case-insensitive filter by city."),
    start_time: Optional[datetime] = Query(None, description="Filter events on or after this ISO-8601 timestamp."),
    end_time: Optional[datetime] = Query(None, description="Filter events on or before this ISO-8601 timestamp."),
) -> AnalyticsSummaryResponse:
    """
    Handle GET /api/analytics/summary:
    - Validates categorical parameters and date ranges.
    - Constructs parameterized SQL WHERE clauses.
    - Executes SQL aggregations (COUNT, GROUP BY, DATE) in PostgreSQL.
    - Returns structured summary response.
    """
    # 1. Parameter validation
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

    # Time range validation
    if start_time is not None and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time is not None and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid time range: start_time cannot be greater than end_time.",
        )

    # If caller explicitly filters by 'Rejected', return zeroed summary as rejected reports are excluded from analytics
    if verification_status == "Rejected":
        return AnalyticsSummaryResponse(
            total_events=0,
            verified_events=0,
            likely_events=0,
            unverified_events=0,
            rejected_events=0,
            duplicate_events=0,
            verification_breakdown=[
                VerificationSummary(status="Verified", count=0),
                VerificationSummary(status="Likely", count=0),
                VerificationSummary(status="Unverified", count=0),
                VerificationSummary(status="Rejected", count=0),
                VerificationSummary(status="Duplicate", count=0),
            ],
            events_by_type=[],
            events_by_source=[],
            events_by_state=[],
            events_over_time=[],
        )

    # 2. Construct parameterized SQL query filters
    where_clauses: List[str] = [
        "(verification_status IS NULL OR verification_status != 'Rejected')",
    ]
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

    # 3. Define SQL queries with database aggregation
    summary_sql = f"""
        SELECT
            COUNT(*) AS total_events,
            COUNT(*) FILTER (WHERE verification_status = 'Verified') AS verified_events,
            COUNT(*) FILTER (WHERE verification_status = 'Likely') AS likely_events,
            COUNT(*) FILTER (WHERE verification_status = 'Unverified') AS unverified_events,
            0 AS rejected_events,
            COUNT(*) FILTER (WHERE verification_status = 'Duplicate') AS duplicate_events
        FROM public.weather_events
        {where_sql};
    """


    type_sql = f"""
        SELECT
            event_type,
            COUNT(*) AS count
        FROM public.weather_events
        {where_sql}
        GROUP BY event_type
        ORDER BY count DESC, event_type ASC;
    """

    source_sql = f"""
        SELECT
            source,
            COUNT(*) AS count
        FROM public.weather_events
        {where_sql}
        GROUP BY source
        ORDER BY count DESC, source ASC;
    """

    state_sql = f"""
        SELECT
            COALESCE(state, 'Unknown') AS state_name,
            COUNT(*) AS count
        FROM public.weather_events
        {where_sql}
        GROUP BY COALESCE(state, 'Unknown')
        ORDER BY count DESC, state_name ASC;
    """

    time_sql = f"""
        SELECT
            DATE(event_timestamp)::text AS event_date,
            COUNT(*) AS count
        FROM public.weather_events
        {where_sql}
        GROUP BY DATE(event_timestamp)
        ORDER BY DATE(event_timestamp) ASC;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. Total and verification counts
                cur.execute(summary_sql, params)
                summary_row = cur.fetchone()
                if summary_row:
                    total_events = summary_row[0] or 0
                    verified_events = summary_row[1] or 0
                    likely_events = summary_row[2] or 0
                    unverified_events = summary_row[3] or 0
                    rejected_events = summary_row[4] or 0
                    duplicate_events = summary_row[5] or 0
                else:
                    total_events = verified_events = likely_events = unverified_events = rejected_events = duplicate_events = 0

                # 2. Events by type
                cur.execute(type_sql, params)
                type_rows = cur.fetchall()
                events_by_type = [
                    EventTypeCountItem(event_type=str(r[0]), count=int(r[1]))
                    for r in type_rows
                ]

                # 3. Events by source
                cur.execute(source_sql, params)
                source_rows = cur.fetchall()
                events_by_source = [
                    SourceCountItem(source=str(r[0]), count=int(r[1]))
                    for r in source_rows
                ]

                # 4. Events by state
                cur.execute(state_sql, params)
                state_rows = cur.fetchall()
                events_by_state = [
                    StateCountItem(state=str(r[0]), count=int(r[1]))
                    for r in state_rows
                ]

                # 5. Events over time
                cur.execute(time_sql, params)
                time_rows = cur.fetchall()
                events_over_time = [
                    DateCountItem(date=str(r[0]), count=int(r[1]))
                    for r in time_rows
                ]

        # Always include all 5 canonical verification categories in breakdown
        canonical_breakdown = [
            VerificationSummary(status="Verified", count=verified_events),
            VerificationSummary(status="Likely", count=likely_events),
            VerificationSummary(status="Unverified", count=unverified_events),
            VerificationSummary(status="Rejected", count=rejected_events),
            VerificationSummary(status="Duplicate", count=duplicate_events),
        ]

        return AnalyticsSummaryResponse(
            total_events=total_events,
            verified_events=verified_events,
            likely_events=likely_events,
            unverified_events=unverified_events,
            rejected_events=rejected_events,
            duplicate_events=duplicate_events,
            verification_breakdown=canonical_breakdown,
            events_by_verification=canonical_breakdown,
            events_by_type=events_by_type,
            events_by_source=events_by_source,
            events_by_state=events_by_state,
            events_over_time=events_over_time,
        )

    except HTTPException:
        raise
    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Database error in get_analytics_summary: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Failed to compute weather analytics.",
        )
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Unexpected error in get_analytics_summary: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while computing weather analytics.",
        )
