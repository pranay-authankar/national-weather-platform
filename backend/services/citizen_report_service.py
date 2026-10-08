"""
Service for ingesting, normalizing, and storing citizen weather reports.

Designed modularly to support future additions:
- Automated reverse-geocoding (deriving city/district/state from coordinates)
- Spatio-temporal duplicate detection
- Multi-source AI & radar verification
"""

import logging
import uuid
from typing import Any, Dict, Optional

from database import sanitize_error_message
from schemas.reports import CitizenReportCreate
from services.duplicate_detection_service import detect_duplicate_report
from services.geocoding_service import reverse_geocode
from services.weather_event_classifier import normalize_event_type
from services.weather_event_service import insert_weather_event

logger = logging.getLogger(__name__)


def generate_citizen_source_record_id() -> str:
    """
    Generate a unique source_record_id for a citizen report submission.
    """
    return f"citizen_{uuid.uuid4()}"


def normalize_citizen_report(
    report: CitizenReportCreate,
    city: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    verification_status: str = "Unverified",
    duplicate_of: Optional[str] = None,
    confidence_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Normalize incoming citizen report payload into the standard weather_events row structure.

    Rules:
    - source is set to 'Citizen_Report'.
    - source_record_id is uniquely generated.
    - event_type is normalized against system canonical event types.
    - timestamp is mapped to event_timestamp.
    - image_url and video_url are stored when provided.
    - verification_status is set based on duplicate detection ('Duplicate' or 'Unverified').
    - confidence_score is populated if duplicate match occurs, else None.
    - city, district, state are populated from reverse geocoding if provided, else None.
    - meteorological measurements are NEVER invented (kept as None).
    - duplicate_of is set to matching event ID if duplicate, else None.
    """
    source_record_id = generate_citizen_source_record_id()
    canonical_event_type = normalize_event_type(report.event_type)

    return {
        "source": "Citizen_Report",
        "source_record_id": source_record_id,
        "event_type": canonical_event_type,
        "description": report.description,
        "event_timestamp": report.timestamp,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "location": None,
        "city": city,
        "district": district,
        "state": state,
        "temperature": None,
        "rainfall": None,
        "humidity": None,
        "wind_speed": None,
        "wind_direction": None,
        "pressure": None,
        "image_url": report.image_url,
        "video_url": report.video_url,
        "source_url": None,
        "verification_status": verification_status,
        "confidence_score": confidence_score,
        "duplicate_of": duplicate_of,
    }


async def check_duplicate_report(
    event_record: Dict[str, Any],
) -> Optional[str]:
    """
    Modular extension point for duplicate detection.
    
    Future implementation will query nearby events within a spatio-temporal
    radius (e.g., 5km and +/- 2 hours) and compute similarity scores.

    Returns:
        Optional[str]: UUID of original event if identified as duplicate, else None.
    """
    # Duplicate detection not yet enabled as per requirements
    return None


async def verify_citizen_report(
    event_record: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Modular extension point for evidence-based verification.

    Future implementation will cross-reference ground reports with:
    - IMD / Open-Meteo observational grids
    - Radar / satellite precipitation estimates
    - Social media and nearby citizen consensus

    Returns:
        Dict[str, Any]: Contains verification_status and confidence_score.
    """
    # Automated verification not yet enabled as per requirements
    return {
        "verification_status": "Unverified",
        "confidence_score": None,
    }


async def process_and_store_citizen_report(
    report: CitizenReportCreate,
) -> Dict[str, Any]:
    """
    Orchestrate processing and persisting a citizen report into PostgreSQL:
    1. Perform automated reverse-geocoding (deriving city/district/state from coordinates).
    2. Perform spatio-temporal duplicate detection against existing weather events.
    3. Normalize payload into public.weather_events schema.
    4. Verify evidence (modular hook, deferred).
    5. Safely persist record into Supabase PostgreSQL.

    Returns:
        Dict[str, Any]: Object containing event_id, status='received',
                        verification_status, duplicate_of, city, district, and state.

    Raises:
        RuntimeError: If database persistence fails (credentials sanitized).
    """
    # 1. Reverse-geocode coordinates to identify administrative location
    geocoded = await reverse_geocode(report.latitude, report.longitude)

    # 2. Automated duplicate detection
    dup_result = await detect_duplicate_report(
        latitude=report.latitude,
        longitude=report.longitude,
        event_timestamp=report.timestamp,
        event_type=report.event_type,
        description=report.description,
    )

    if dup_result.get("is_duplicate"):
        verification_status = "Duplicate"
        duplicate_of = dup_result.get("duplicate_of")
        confidence_score = dup_result.get("confidence_score")
    else:
        verification_status = "Unverified"
        duplicate_of = None
        confidence_score = None

    # 3. Normalize report with geocoded divisions and duplicate detection outcome
    record = normalize_citizen_report(
        report=report,
        city=geocoded.get("city"),
        district=geocoded.get("district"),
        state=geocoded.get("state"),
        verification_status=verification_status,
        duplicate_of=duplicate_of,
        confidence_score=confidence_score,
    )

    # 4. Verification hook (deferred to next milestone)
    # verification_result = await verify_citizen_report(record)
    # record.update(verification_result)

    # 5. Insert into database
    try:
        inserted = insert_weather_event(record)
        return {
            "event_id": inserted["event_id"],
            "status": "received",
            "verification_status": inserted["verification_status"],
            "duplicate_of": inserted["duplicate_of"],
            "confidence_score": inserted.get("confidence_score"),
            "city": inserted.get("city"),
            "district": inserted.get("district"),
            "state": inserted.get("state"),
        }
    except Exception as exc:
        sanitized_msg = sanitize_error_message(str(exc))
        logger.error("Failed to persist citizen weather report: %s", sanitized_msg)
        raise RuntimeError(f"Failed to persist citizen report: {sanitized_msg}") from None
