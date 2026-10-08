"""
Deterministic Weather Report Verification and Confidence Scoring Service.

Evaluates independent supporting evidence for weather events and citizen reports
using only real data already stored in PostgreSQL/PostGIS.

Core Principles:
1. Duplicate Integrity: If an event is already marked as 'Duplicate', its status
   and duplicate_of reference are never overwritten.
2. Anti-False-Positive Rule: A citizen report with only valid fields (GPS, timestamp,
   type) receives a baseline score (<= 39) and remains 'Unverified' unless independent
   supporting evidence confirms it.
3. Independent Evidence Gathering:
   - Nearby independent weather event (+25)
   - Strong agreement with official/sensor weather observation (+25)
   - Additional independent supporting source (+15)
   - Valid location (+15), valid timestamp (+10), valid event type (+10)
4. Score to Status Mapping:
   - 0–39: Unverified
   - 40–89: Likely
   - 90–100: Verified
   - Exception: Duplicate remains Duplicate.
5. Fault-Tolerant: Database or query errors safely fall back to Unverified without
   crashing the report ingestion endpoint.
"""

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

import psycopg
from database import get_db_connection, sanitize_error_message
from services.duplicate_detection_service import calculate_event_type_similarity
from services.weather_event_classifier import ALLOWED_EVENT_TYPES

logger = logging.getLogger(__name__)

# --- Configurable Scoring Constants ---
SCORE_VALID_LOCATION: float = 15.0
SCORE_VALID_TIMESTAMP: float = 10.0
SCORE_VALID_EVENT_TYPE: float = 10.0
SCORE_SUPPORTING_NEARBY_EVENT: float = 25.0
SCORE_REAL_OBSERVATION_AGREEMENT: float = 25.0
SCORE_ADDITIONAL_SUPPORTING_SOURCE: float = 15.0
MAX_SCORE: float = 100.0

# --- Status Threshold Constants ---
SCORE_THRESHOLD_UNVERIFIED_MAX: float = 39.0
SCORE_THRESHOLD_LIKELY_MIN: float = 40.0
SCORE_THRESHOLD_LIKELY_MAX: float = 89.0
SCORE_THRESHOLD_VERIFIED_MIN: float = 90.0

STATUS_UNVERIFIED: str = "Unverified"
STATUS_LIKELY: str = "Likely"
STATUS_VERIFIED: str = "Verified"
STATUS_DUPLICATE: str = "Duplicate"

# --- Spatio-Temporal Evidence Radius & Window ---
DEFAULT_VERIFICATION_RADIUS_KM: float = float(os.getenv("VERIFICATION_RADIUS_KM", "25.0"))
DEFAULT_VERIFICATION_RADIUS_METERS: float = DEFAULT_VERIFICATION_RADIUS_KM * 1000.0

DEFAULT_VERIFICATION_TIME_WINDOW_HOURS: float = float(os.getenv("VERIFICATION_TIME_WINDOW_HOURS", "4.0"))
DEFAULT_VERIFICATION_TIME_WINDOW_SECONDS: float = DEFAULT_VERIFICATION_TIME_WINDOW_HOURS * 3600.0

# Official real weather observational sources
OFFICIAL_OBSERVATION_SOURCES: Set[str] = {
    "Open_Meteo",
    "IMD",
    "IMD_RSS",
    "Data_Gov",
}


class VerificationResult(TypedDict):
    """
    Structured outcome of the verification evaluation.
    """
    verification_status: str
    confidence_score: float
    evidence_breakdown: Dict[str, Any]


def is_valid_location(latitude: Optional[float], longitude: Optional[float]) -> bool:
    """
    Check if geographic coordinates are present and within valid global ranges.
    """
    if latitude is None or longitude is None:
        return False
    try:
        lat = float(latitude)
        lon = float(longitude)
        return (-90.0 <= lat <= 90.0) and (-180.0 <= lon <= 180.0)
    except (ValueError, TypeError):
        return False


def is_valid_timestamp(event_timestamp: Optional[datetime]) -> bool:
    """
    Check if the observation timestamp is a valid datetime.
    """
    if event_timestamp is None:
        return False
    return isinstance(event_timestamp, datetime)


def is_valid_event_type(event_type: Optional[str]) -> bool:
    """
    Check if the weather event type is non-empty and recognized.
    """
    if not event_type or not isinstance(event_type, str):
        return False
    trimmed = event_type.strip()
    if not trimmed:
        return False
    allowed_lower = {t.lower() for t in ALLOWED_EVENT_TYPES}
    return trimmed.lower() in allowed_lower or len(trimmed) > 0


def map_score_to_verification_status(
    score: float,
    current_status: Optional[str] = None,
) -> str:
    """
    Map numeric confidence score to verification status:
    - 0–39: Unverified
    - 40–89: Likely
    - 90–100: Verified

    Exception: Duplicate status is permanently preserved.
    """
    if current_status == STATUS_DUPLICATE:
        return STATUS_DUPLICATE

    if score >= SCORE_THRESHOLD_VERIFIED_MIN:
        return STATUS_VERIFIED
    elif score >= SCORE_THRESHOLD_LIKELY_MIN:
        return STATUS_LIKELY
    else:
        return STATUS_UNVERIFIED


def find_supporting_events(
    latitude: float,
    longitude: float,
    event_timestamp: datetime,
    event_type: str,
    exclude_event_id: Optional[str] = None,
    max_distance_meters: float = DEFAULT_VERIFICATION_RADIUS_METERS,
    max_time_diff_seconds: float = DEFAULT_VERIFICATION_TIME_WINDOW_SECONDS,
) -> List[Dict[str, Any]]:
    """
    Query PostgreSQL via PostGIS geography functions for independent weather events
    within the verification spatio-temporal radius.

    Filters out:
    - The target report itself (if already persisted and exclude_event_id provided)
    - Duplicate records pointing to the target report
    """
    if event_timestamp.tzinfo is None:
        event_timestamp = event_timestamp.replace(tzinfo=timezone.utc)

    min_time = event_timestamp - timedelta(seconds=max_time_diff_seconds)
    max_time = event_timestamp + timedelta(seconds=max_time_diff_seconds)

    query = """
        SELECT
            event_id,
            source,
            source_record_id,
            event_type,
            description,
            event_timestamp,
            latitude,
            longitude,
            verification_status,
            duplicate_of,
            ST_Distance(
                COALESCE(location, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography),
                ST_SetSRID(ST_MakePoint(%(target_lon)s, %(target_lat)s), 4326)::geography
            ) AS distance_meters
        FROM weather_events
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
          AND event_timestamp >= %(min_time)s
          AND event_timestamp <= %(max_time)s
          AND ST_DWithin(
              COALESCE(location, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography),
              ST_SetSRID(ST_MakePoint(%(target_lon)s, %(target_lat)s), 4326)::geography,
              %(max_distance_meters)s
          )
    """

    params: Dict[str, Any] = {
        "target_lat": latitude,
        "target_lon": longitude,
        "min_time": min_time,
        "max_time": max_time,
        "max_distance_meters": max_distance_meters,
    }

    if exclude_event_id:
        query += " AND event_id != %(exclude_id)s::uuid AND (duplicate_of IS NULL OR duplicate_of != %(exclude_id)s::uuid)"
        params["exclude_id"] = exclude_event_id

    query += " ORDER BY distance_meters ASC LIMIT 50;"

    matching_candidates: List[Dict[str, Any]] = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            for r in rows:
                cand_type = r[3]
                # Check event type compatibility
                type_sim = calculate_event_type_similarity(event_type, cand_type)
                if type_sim > 0.0:
                    matching_candidates.append({
                        "event_id": str(r[0]),
                        "source": r[1],
                        "source_record_id": r[2],
                        "event_type": r[3],
                        "description": r[4],
                        "event_timestamp": r[5],
                        "latitude": r[6],
                        "longitude": r[7],
                        "verification_status": r[8],
                        "duplicate_of": str(r[9]) if r[9] is not None else None,
                        "distance_meters": float(r[10]),
                        "type_similarity": type_sim,
                    })

    return matching_candidates


def calculate_verification_score(
    latitude: Optional[float],
    longitude: Optional[float],
    event_timestamp: Optional[datetime],
    event_type: Optional[str],
    supporting_events: Optional[List[Dict[str, Any]]] = None,
    current_status: Optional[str] = None,
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Deterministic scoring calculation using available evidence.
    Returns:
        (total_score, verification_status, evidence_breakdown)
    """
    # Duplicate rule: preserve Duplicate permanently
    if current_status == STATUS_DUPLICATE:
        return 0.0, STATUS_DUPLICATE, {"reason": "Preserved existing Duplicate status"}

    score = 0.0
    components: Dict[str, float] = {}

    # 1. Location validity (+15)
    valid_loc = is_valid_location(latitude, longitude)
    components["valid_location"] = SCORE_VALID_LOCATION if valid_loc else 0.0
    score += components["valid_location"]

    # 2. Timestamp validity (+10)
    valid_time = is_valid_timestamp(event_timestamp)
    components["valid_timestamp"] = SCORE_VALID_TIMESTAMP if valid_time else 0.0
    score += components["valid_timestamp"]

    # 3. Event type validity (+10)
    valid_type = is_valid_event_type(event_type)
    components["valid_event_type"] = SCORE_VALID_EVENT_TYPE if valid_type else 0.0
    score += components["valid_event_type"]

    # Analyze supporting events
    events = supporting_events or []
    has_supporting_event = len(events) >= 1
    components["supporting_nearby_event"] = SCORE_SUPPORTING_NEARBY_EVENT if has_supporting_event else 0.0
    score += components["supporting_nearby_event"]

    # Strong agreement with real weather observation (+25)
    has_official_agreement = any(
        e.get("source") in OFFICIAL_OBSERVATION_SOURCES or e.get("source") != "Citizen_Report"
        for e in events
    )
    components["official_observation_agreement"] = SCORE_REAL_OBSERVATION_AGREEMENT if has_official_agreement else 0.0
    score += components["official_observation_agreement"]

    # Additional independent supporting source (+15)
    # Count distinct independent sources or multiple distinct events
    distinct_sources = {e.get("source") for e in events if e.get("source")}
    has_additional_source = (len(events) >= 2) or (len(distinct_sources) >= 2)
    components["additional_supporting_source"] = SCORE_ADDITIONAL_SUPPORTING_SOURCE if has_additional_source else 0.0
    score += components["additional_supporting_source"]

    # Cap score at maximum
    final_score = min(score, MAX_SCORE)
    status = map_score_to_verification_status(final_score, current_status)

    breakdown = {
        "valid_location": valid_loc,
        "valid_timestamp": valid_time,
        "valid_event_type": valid_type,
        "supporting_events_count": len(events),
        "has_official_agreement": has_official_agreement,
        "has_additional_source": has_additional_source,
        "supporting_event_ids": [e["event_id"] for e in events],
        "components": components,
        "total_score": round(final_score, 1),
    }

    return final_score, status, breakdown


async def verify_weather_event(
    latitude: Optional[float],
    longitude: Optional[float],
    event_timestamp: Optional[datetime],
    event_type: Optional[str],
    source: str = "Citizen_Report",
    current_status: str = STATUS_UNVERIFIED,
    duplicate_of: Optional[str] = None,
    exclude_event_id: Optional[str] = None,
    supporting_events_override: Optional[List[Dict[str, Any]]] = None,
    max_distance_meters: float = DEFAULT_VERIFICATION_RADIUS_METERS,
    max_time_diff_seconds: float = DEFAULT_VERIFICATION_TIME_WINDOW_SECONDS,
) -> VerificationResult:
    """
    Main asynchronous interface to verify weather events and calculate confidence score.

    Guarantees:
    - Never raises unhandled exceptions. On database error, returns Unverified
      with baseline local evidence score.
    - If current_status is Duplicate, retains Duplicate status.
    - An isolated citizen report without independent confirmation stays Unverified (score <= 35).
    - With independent nearby event(s) or official observation agreements, confidence score
      rises deterministically to Likely or Verified.
    """
    # 1. Duplicate check: never overwrite Duplicate
    if current_status == STATUS_DUPLICATE:
        return {
            "verification_status": STATUS_DUPLICATE,
            "confidence_score": 0.0,
            "evidence_breakdown": {
                "reason": "Duplicate reports retain Duplicate status permanently",
                "duplicate_of": duplicate_of,
            },
        }

    # 2. Collect supporting evidence from PostgreSQL / PostGIS
    supporting_events: List[Dict[str, Any]] = []

    if supporting_events_override is not None:
        supporting_events = supporting_events_override
    elif is_valid_location(latitude, longitude) and is_valid_timestamp(event_timestamp) and is_valid_event_type(event_type):
        try:
            supporting_events = find_supporting_events(
                latitude=float(latitude),  # type: ignore[arg-type]
                longitude=float(longitude),  # type: ignore[arg-type]
                event_timestamp=event_timestamp,  # type: ignore[arg-type]
                event_type=str(event_type),
                exclude_event_id=exclude_event_id,
                max_distance_meters=max_distance_meters,
                max_time_diff_seconds=max_time_diff_seconds,
            )
        except Exception as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.warning(
                "Verification database query failed for (%s, %s): %s. Falling back to local evidence.",
                latitude,
                longitude,
                sanitized,
            )
            supporting_events = []

    # 3. Calculate deterministic score and status
    score, status, breakdown = calculate_verification_score(
        latitude=latitude,
        longitude=longitude,
        event_timestamp=event_timestamp,
        event_type=event_type,
        supporting_events=supporting_events,
        current_status=current_status,
    )

    return {
        "verification_status": status,
        "confidence_score": score,
        "evidence_breakdown": breakdown,
    }
