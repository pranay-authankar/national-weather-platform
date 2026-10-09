"""
Service module for Admin Weather Report Moderation.
Handles status transitions (verify, reject, restore), duplicate-event validation,
credential protection, and persistent audit logging.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

import psycopg
from database import get_db_connection, sanitize_error_message
from routers.events import EVENT_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ModerationError(Exception):
    """Base exception for report moderation operations."""
    pass


class EventNotFoundError(ModerationError):
    """Raised when the target weather event ID does not exist."""
    pass


class InvalidStatusTransitionError(ModerationError):
    """Raised when an invalid status transition is requested."""
    pass


class DuplicateEventRestrictionError(ModerationError):
    """Raised when attempting to mark a duplicate event as Verified."""
    pass


class ModerationValidationError(ModerationError):
    """Raised when moderation parameters (e.g. reason) are invalid."""
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_uuid(val: str) -> str:
    """Validate string as a valid UUID."""
    try:
        parsed = uuid.UUID(str(val).strip())
        return str(parsed)
    except (ValueError, AttributeError, TypeError):
        raise ModerationValidationError(f"Invalid UUID format for event ID: '{val}'.")


def _row_to_event_dict(row: tuple) -> Dict[str, Any]:
    """Convert a database tuple matching EVENT_COLUMNS into a structured dictionary."""
    (
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
        source_trust_score,
    ) = row

    return {
        "event_id": str(event_id),
        "source": str(source),
        "event_type": str(event_type),
        "description": description,
        "event_timestamp": event_timestamp.isoformat() if hasattr(event_timestamp, "isoformat") else str(event_timestamp),
        "latitude": float(latitude) if latitude is not None else None,
        "longitude": float(longitude) if longitude is not None else None,
        "city": city,
        "district": district,
        "state": state,
        "temperature": float(temperature) if temperature is not None else None,
        "rainfall": float(rainfall) if rainfall is not None else None,
        "humidity": float(humidity) if humidity is not None else None,
        "wind_speed": float(wind_speed) if wind_speed is not None else None,
        "wind_direction": float(wind_direction) if wind_direction is not None else None,
        "pressure": float(pressure) if pressure is not None else None,
        "image_url": image_url,
        "video_url": video_url,
        "source_url": source_url,
        "verification_status": str(verification_status),
        "confidence_score": float(confidence_score) if confidence_score is not None else None,
        "duplicate_of": str(duplicate_of) if duplicate_of is not None else None,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "credibility_score": float(credibility_score) if credibility_score is not None else None,
        "credibility_status": credibility_status,
        "credibility_reasons": credibility_reasons,
        "source_trust_score": float(source_trust_score) if source_trust_score is not None else None,
    }


# ---------------------------------------------------------------------------
# Core Moderation Engine
# ---------------------------------------------------------------------------

def moderate_weather_event(
    event_id: str,
    new_status: str,
    reason: str,
    moderator_id: str,
) -> Dict[str, Any]:
    """
    Execute an administrative moderation decision on a weather event.
    
    Guarantees:
    - Atomically updates event status and writes audit log entry.
    - Validates status transitions:
        * Cannot transition to current status (idempotency/redundancy rejection).
        * Cannot mark a duplicate event as Verified while retaining duplicate relationship.
        * Can only restore a Rejected event back to Unverified for reassessment.
    - Preserves all credibility scores, duplicate relationships, and original event metadata.
    
    Returns:
        Dict[str, Any]: Audit summary and updated event record.
    """
    clean_event_id = _validate_uuid(event_id)
    clean_reason = reason.strip() if reason else ""
    if len(clean_reason) < 3:
        raise ModerationValidationError("Moderation reason must be at least 3 characters long.")

    if new_status not in ("Verified", "Rejected", "Unverified"):
        raise ModerationValidationError(f"Invalid target moderation status: '{new_status}'.")

    select_sql = f"""
        SELECT {EVENT_COLUMNS}
        FROM public.weather_events
        WHERE event_id = %s;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. Fetch existing event
                cur.execute(select_sql, (clean_event_id,))
                row = cur.fetchone()
                if not row:
                    raise EventNotFoundError(f"Weather event '{clean_event_id}' not found.")

                current_event = _row_to_event_dict(row)
                current_status = current_event["verification_status"]
                duplicate_of = current_event["duplicate_of"]

                # 2. Check transition validity
                # Restore restriction: only Rejected events can be restored to Unverified
                if new_status == "Unverified" and current_status != "Rejected":
                    raise InvalidStatusTransitionError(
                        f"Only Rejected reports can be restored to Unverified for reassessment. Current status is '{current_status}'."
                    )

                # Duplicate restriction: cannot verify duplicate
                if new_status == "Verified" and (current_status == "Duplicate" or duplicate_of is not None):
                    raise DuplicateEventRestrictionError(
                        "Cannot mark a duplicate record as Verified while retaining a duplicate relationship."
                    )

                if current_status == new_status:
                    raise InvalidStatusTransitionError(
                        f"Event is already '{current_status}'. Transition from '{current_status}' to '{new_status}' is invalid."
                    )

                # 3. Calculate updated confidence score while strictly preserving credibility fields
                if new_status == "Verified":
                    new_confidence = 100.0
                elif new_status == "Rejected":
                    new_confidence = 0.0
                elif new_status == "Unverified":
                    new_confidence = 35.0
                else:
                    new_confidence = current_event["confidence_score"]

                # 4. Update weather event
                update_sql = f"""
                    UPDATE public.weather_events
                    SET verification_status = %(new_status)s,
                        confidence_score = %(confidence_score)s
                    WHERE event_id = %(event_id)s
                    RETURNING {EVENT_COLUMNS};
                """
                cur.execute(
                    update_sql,
                    {
                        "new_status": new_status,
                        "confidence_score": new_confidence,
                        "event_id": clean_event_id,
                    },
                )
                updated_row = cur.fetchone()
                updated_event = _row_to_event_dict(updated_row)

                # 5. Insert audit log entry
                audit_sql = """
                    INSERT INTO public.moderation_audit_log (
                        event_id,
                        previous_status,
                        new_status,
                        reason,
                        moderator_id
                    ) VALUES (
                        %(event_id)s,
                        %(previous_status)s,
                        %(new_status)s,
                        %(reason)s,
                        %(moderator_id)s
                    ) RETURNING audit_id, created_at;
                """
                cur.execute(
                    audit_sql,
                    {
                        "event_id": clean_event_id,
                        "previous_status": current_status,
                        "new_status": new_status,
                        "reason": clean_reason,
                        "moderator_id": moderator_id,
                    },
                )
                audit_row = cur.fetchone()
                audit_id = str(audit_row[0])
                moderated_at = audit_row[1]

            conn.commit()

        return {
            "audit_id": audit_id,
            "event_id": clean_event_id,
            "previous_status": current_status,
            "new_status": new_status,
            "reason": clean_reason,
            "moderator_id": moderator_id,
            "moderated_at": moderated_at.isoformat() if hasattr(moderated_at, "isoformat") else str(moderated_at),
            "event": updated_event,
        }

    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        raise RuntimeError(f"Database error during moderation: {sanitized}") from None


# ---------------------------------------------------------------------------
# Audit History Queries
# ---------------------------------------------------------------------------

def get_event_audit_history(event_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve chronological audit logs for a single weather event.
    """
    clean_event_id = _validate_uuid(event_id)

    # Check if event exists
    check_sql = "SELECT 1 FROM public.weather_events WHERE event_id = %s;"
    select_sql = """
        SELECT
            audit_id,
            event_id,
            previous_status,
            new_status,
            reason,
            moderator_id,
            created_at
        FROM public.moderation_audit_log
        WHERE event_id = %s
        ORDER BY created_at DESC;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(check_sql, (clean_event_id,))
                if not cur.fetchone():
                    raise EventNotFoundError(f"Weather event '{clean_event_id}' not found.")

                cur.execute(select_sql, (clean_event_id,))
                rows = cur.fetchall()

        entries: List[Dict[str, Any]] = []
        for r in rows:
            entries.append({
                "audit_id": str(r[0]),
                "event_id": str(r[1]),
                "previous_status": r[2],
                "new_status": r[3],
                "reason": r[4],
                "moderator_id": r[5],
                "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
            })
        return entries

    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        raise RuntimeError(f"Database error reading audit history: {sanitized}") from None


def get_audit_history_list(
    event_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Query paginated audit history across events.
    """
    conditions: List[str] = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if event_id:
        clean_id = _validate_uuid(event_id)
        conditions.append("event_id = %(event_id)s")
        params["event_id"] = clean_id

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    select_sql = f"""
        SELECT
            audit_id,
            event_id,
            previous_status,
            new_status,
            reason,
            moderator_id,
            created_at
        FROM public.moderation_audit_log
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %(limit)s OFFSET %(offset)s;
    """

    count_sql = f"""
        SELECT COUNT(*)
        FROM public.moderation_audit_log
        {where_clause};
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                total = cur.fetchone()[0]

                cur.execute(select_sql, params)
                rows = cur.fetchall()

        entries: List[Dict[str, Any]] = []
        for r in rows:
            entries.append({
                "audit_id": str(r[0]),
                "event_id": str(r[1]),
                "previous_status": r[2],
                "new_status": r[3],
                "reason": r[4],
                "moderator_id": r[5],
                "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
            })

        return {
            "data": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        raise RuntimeError(f"Database error reading audit list: {sanitized}") from None
