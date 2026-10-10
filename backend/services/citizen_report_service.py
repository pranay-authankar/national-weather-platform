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

from datetime import datetime, timezone
from database import sanitize_error_message
from schemas.reports import CitizenReportCreate
from services.duplicate_detection_service import detect_duplicate_report
from services.geocoding_service import reverse_geocode
from services.location_service import resolve_district_coordinates
from services.report_credibility_service import evaluate_and_score_citizen_report
from services.verification_service import verify_weather_event
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
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    city: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    verification_status: str = "Unverified",
    duplicate_of: Optional[str] = None,
    confidence_score: Optional[float] = None,
    credibility_score: Optional[float] = None,
    credibility_status: Optional[str] = None,
    credibility_reasons: Optional[list] = None,
    source_trust_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Normalize incoming citizen report payload into the standard weather_events row structure.

    Rules:
    - source is set to 'Citizen_Report'.
    - source_record_id is uniquely generated.
    - event_type is normalized against system canonical event types.
    - timestamp is mapped to event_timestamp (defaults to UTC now if omitted).
    - image_url and video_url are stored when provided.
    - verification_status is set based on duplicate detection ('Duplicate' or 'Unverified').
    - confidence_score is populated if duplicate match occurs, else None.
    - city, district, state are populated from authoritative dropdown or reverse geocoding.
    - meteorological measurements are NEVER invented (kept as None).
    - duplicate_of is set to matching event ID if duplicate, else None.
    - credibility_score, credibility_status, credibility_reasons, source_trust_score populated.
    """
    source_record_id = generate_citizen_source_record_id()
    canonical_event_type = normalize_event_type(report.event_type)
    final_lat = latitude if latitude is not None else report.latitude
    final_lon = longitude if longitude is not None else report.longitude
    final_timestamp = report.timestamp if report.timestamp is not None else datetime.now(timezone.utc)

    return {
        "source": "Citizen_Report",
        "source_record_id": source_record_id,
        "event_type": canonical_event_type,
        "description": report.description,
        "event_timestamp": final_timestamp,
        "latitude": final_lat,
        "longitude": final_lon,
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
        "credibility_score": credibility_score,
        "credibility_status": credibility_status,
        "credibility_reasons": credibility_reasons,
        "source_trust_score": source_trust_score,
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
    Evidence-based verification evaluating independent weather observations
    and nearby ground reports.

    Returns:
        Dict[str, Any]: Contains verification_status and confidence_score.
    """
    res = await verify_weather_event(
        latitude=event_record.get("latitude"),
        longitude=event_record.get("longitude"),
        event_timestamp=event_record.get("event_timestamp"),
        event_type=event_record.get("event_type"),
        source=event_record.get("source", "Citizen_Report"),
        current_status=event_record.get("verification_status", "Unverified"),
        duplicate_of=event_record.get("duplicate_of"),
        exclude_event_id=event_record.get("event_id"),
    )
    return {
        "verification_status": res["verification_status"],
        "confidence_score": res["confidence_score"],
    }


async def process_and_store_citizen_report(
    report: CitizenReportCreate,
) -> Dict[str, Any]:
    """
    Orchestrate processing and persisting a citizen report into PostgreSQL:
    1. Resolve authoritative coordinates from state/district if not provided directly.
    2. Perform automated reverse-geocoding (if state/district are not provided).
    3. Perform spatio-temporal duplicate detection against existing weather events.
    4. Normalize payload into public.weather_events schema.
    5. Verify evidence (modular hook).
    6. Safely persist record into Supabase PostgreSQL.

    Returns:
        Dict[str, Any]: Object containing event_id, status='received',
                        verification_status, duplicate_of, city, district, and state.

    Raises:
        RuntimeError: If database persistence fails (credentials sanitized).
    """
    # 1. Resolve coordinates from direct input or authoritative state/district mapping
    final_lat = report.latitude
    final_lon = report.longitude

    if final_lat is None or final_lon is None:
        if report.state and (report.district or report.city):
            resolved = resolve_district_coordinates(report.state, report.district or report.city)
            if resolved:
                final_lat, final_lon = resolved

    if final_lat is None or final_lon is None:
        raise ValueError("Valid geographical coordinates or an authoritative state and district must be provided.")

    final_timestamp = report.timestamp or datetime.now(timezone.utc)

    # 2. Administrative location resolution
    # If state and district were selected from authoritative dropdowns, preserve them.
    # Otherwise reverse-geocode coordinates.
    if report.state and (report.district or report.city):
        resolved_state = report.state
        resolved_district = report.district
        resolved_city = report.city or report.district
    else:
        geocoded = await reverse_geocode(final_lat, final_lon)
        resolved_state = geocoded.get("state")
        resolved_district = geocoded.get("district")
        resolved_city = geocoded.get("city")

    # 3. Automated duplicate detection
    dup_result = await detect_duplicate_report(
        latitude=final_lat,
        longitude=final_lon,
        event_timestamp=final_timestamp,
        event_type=report.event_type,
        description=report.description,
    )

    if dup_result.get("is_duplicate"):
        verification_status = "Duplicate"
        duplicate_of = dup_result.get("duplicate_of")
        confidence_score = dup_result.get("confidence_score")
    else:
        duplicate_of = None
        # 4. Verification & confidence evaluation against independent evidence
        try:
            verif_res = await verify_weather_event(
                latitude=final_lat,
                longitude=final_lon,
                event_timestamp=final_timestamp,
                event_type=report.event_type,
                source="Citizen_Report",
                current_status="Unverified",
            )
            verification_status = verif_res["verification_status"]
            confidence_score = verif_res["confidence_score"]
        except Exception as exc:
            sanitized_msg = sanitize_error_message(str(exc))
            logger.warning(
                "Verification evaluation failed for report (%s, %s): %s. Storing as Unverified.",
                final_lat,
                final_lon,
                sanitized_msg,
            )
            verification_status = "Unverified"
            confidence_score = None

    # 5. Credibility scoring & source trust evaluation
    try:
        cred_res = await evaluate_and_score_citizen_report(
            latitude=final_lat,
            longitude=final_lon,
            event_timestamp=final_timestamp,
            event_type=report.event_type,
            description=report.description,
            is_duplicate=(verification_status == "Duplicate"),
            duplicate_of=duplicate_of,
        )
        credibility_score = cred_res["credibility_score"]
        credibility_status = cred_res["credibility_status"]
        credibility_reasons = cred_res["credibility_reasons"]
        source_trust_score = cred_res["source_trust_score"]
    except Exception as exc:
        sanitized_msg = sanitize_error_message(str(exc))
        logger.warning(
            "Credibility evaluation failed for report (%s, %s): %s. Storing default values.",
            final_lat,
            final_lon,
            sanitized_msg,
        )
        credibility_score = None
        credibility_status = "Unverified"
        credibility_reasons = []
        source_trust_score = 50.0

    # 6. Normalize report with verified coordinates, divisions, and evaluation outcome
    record = normalize_citizen_report(
        report=report,
        latitude=final_lat,
        longitude=final_lon,
        city=resolved_city,
        district=resolved_district,
        state=resolved_state,
        verification_status=verification_status,
        duplicate_of=duplicate_of,
        confidence_score=confidence_score,
        credibility_score=credibility_score,
        credibility_status=credibility_status,
        credibility_reasons=credibility_reasons,
        source_trust_score=source_trust_score,
    )

    # 6. Insert into database
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
            "credibility_score": inserted.get("credibility_score"),
            "credibility_status": inserted.get("credibility_status"),
            "credibility_reasons": inserted.get("credibility_reasons"),
            "source_trust_score": inserted.get("source_trust_score"),
        }
    except Exception as exc:
        sanitized_msg = sanitize_error_message(str(exc))
        logger.error("Failed to persist citizen weather report: %s", sanitized_msg)
        raise RuntimeError(f"Failed to persist citizen report: {sanitized_msg}") from None
