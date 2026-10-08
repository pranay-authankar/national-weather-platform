"""
Service for normalizing external weather observations and inserting them
into the PostgreSQL weather_events table.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging
import psycopg

from database import get_db_connection, sanitize_error_message
from services.open_meteo import fetch_open_meteo_weather
from services.weather_event_classifier import classify_open_meteo_observation

logger = logging.getLogger(__name__)


def weather_event_exists(source: str, source_record_id: str) -> bool:
    """
    Check if a weather event from the specified source and source_record_id already exists.
    """
    sql = """
        SELECT 1
        FROM public.weather_events
        WHERE source = %(source)s AND source_record_id = %(source_record_id)s
        LIMIT 1;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"source": source, "source_record_id": source_record_id})
                return cur.fetchone() is not None
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.warning("Error checking for existing weather event (%s, %s): %s", source, source_record_id, sanitized)
        return False


def normalize_open_meteo_record(
    raw_data: Dict[str, Any],
    latitude: float,
    longitude: float,
    city: Optional[str] = None,
    state: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Normalize raw Open-Meteo response into a structured weather_events dictionary.
    Uses the deterministic weather_event_classifier to determine event_type.

    Parameters:
        raw_data (Dict[str, Any]): Raw JSON response from Open-Meteo API.
        latitude (float): Target latitude coordinate.
        longitude (float): Target longitude coordinate.
        city (Optional[str]): City name if reliably known.
        state (Optional[str]): State name if reliably known.

    Returns:
        Dict[str, Any]: Normalized weather event record ready for insertion.
    """
    current = raw_data.get("current", {})

    # Parse event timestamp from Open-Meteo observation time
    raw_time = current.get("time")
    if raw_time:
        event_timestamp = datetime.fromisoformat(raw_time)
        if event_timestamp.tzinfo is None:
            event_timestamp = event_timestamp.replace(tzinfo=timezone.utc)
    else:
        event_timestamp = datetime.now(timezone.utc)

    # Generate a deterministic, safe source record identifier
    time_str = event_timestamp.strftime("%Y%m%dT%H%M%SZ")
    source_record_id = f"open_meteo_{latitude}_{longitude}_{time_str}"

    # Classify event_type using deterministic rules
    event_type = classify_open_meteo_observation(current)

    return {
        "source": "Open_Meteo",
        "source_record_id": source_record_id,
        "event_type": event_type,
        "description": None,
        "event_timestamp": event_timestamp,
        "latitude": latitude,
        "longitude": longitude,
        "location": None,
        "city": city,
        "district": None,
        "state": state,
        "temperature": float(current["temperature_2m"]) if current.get("temperature_2m") is not None else None,
        "rainfall": float(current["precipitation"]) if current.get("precipitation") is not None else None,
        "humidity": float(current["relative_humidity_2m"]) if current.get("relative_humidity_2m") is not None else None,
        "wind_speed": float(current["wind_speed_10m"]) if current.get("wind_speed_10m") is not None else None,
        "wind_direction": float(current["wind_direction_10m"]) if current.get("wind_direction_10m") is not None else None,
        "pressure": float(current["pressure_msl"]) if current.get("pressure_msl") is not None else None,
        "image_url": None,
        "video_url": None,
        "source_url": None,
        "verification_status": "Unverified",
        "confidence_score": None,
        "duplicate_of": None,
        "credibility_score": 90.0,
        "credibility_status": "Verified",
        "credibility_reasons": ["OFFICIAL_SOURCE"],
        "source_trust_score": 90.0,
    }


def insert_weather_event(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert a normalized weather event into the PostgreSQL weather_events table
    using parameterized SQL.

    Parameters:
        event_data (Dict[str, Any]): Normalized weather event data.

    Returns:
        Dict[str, Any]: Inserted record with generated event_id and created_at.

    Raises:
        RuntimeError: If database connection or insertion fails.
    """
    payload = {
        "credibility_score": None,
        "credibility_status": None,
        "credibility_reasons": None,
        "source_trust_score": None,
        **event_data,
    }

    insert_sql = """
        INSERT INTO weather_events (
            source,
            source_record_id,
            event_type,
            description,
            event_timestamp,
            latitude,
            longitude,
            location,
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
            credibility_score,
            credibility_status,
            credibility_reasons,
            source_trust_score
        ) VALUES (
            %(source)s,
            %(source_record_id)s,
            %(event_type)s,
            %(description)s,
            %(event_timestamp)s,
            %(latitude)s,
            %(longitude)s,
            %(location)s,
            %(city)s,
            %(district)s,
            %(state)s,
            %(temperature)s,
            %(rainfall)s,
            %(humidity)s,
            %(wind_speed)s,
            %(wind_direction)s,
            %(pressure)s,
            %(image_url)s,
            %(video_url)s,
            %(source_url)s,
            %(verification_status)s,
            %(confidence_score)s,
            %(duplicate_of)s,
            %(credibility_score)s,
            %(credibility_status)s,
            %(credibility_reasons)s,
            %(source_trust_score)s
        )
        RETURNING event_id, created_at;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(insert_sql, payload)

                row = cur.fetchone()
                if not row:
                    raise RuntimeError("Failed to retrieve generated event_id from inserted record.")
                event_id = str(row[0])
                created_at = row[1]
            conn.commit()

        # Format timestamps for clean JSON serialization
        formatted_event = {}
        for key, value in event_data.items():
            if isinstance(value, datetime):
                formatted_event[key] = value.isoformat()
            else:
                formatted_event[key] = value

        formatted_event["event_id"] = event_id
        formatted_event["created_at"] = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)

        return formatted_event

    except psycopg.Error as exc:
        sanitized = sanitize_error_message(str(exc))
        raise RuntimeError(f"Database insertion error: {sanitized}") from None
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        raise RuntimeError(f"Unexpected database error: {sanitized}") from None


async def ingest_open_meteo_weather(
    latitude: float = 21.25,
    longitude: float = 81.63,
    city: Optional[str] = "Raipur",
    state: Optional[str] = "Chhattisgarh",
    skip_if_exists: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrate fetching real weather data from Open-Meteo, normalizing the payload
    with deterministic classification, and persisting it into the weather_events table.

    Parameters:
        latitude: Target latitude coordinate.
        longitude: Target longitude coordinate.
        city: Administrative city name.
        state: Administrative state name.
        skip_if_exists: If True, avoids inserting duplicates when source_record_id exists.
        dry_run: If True, performs real fetch and normalization without inserting into database.

    Returns:
        Dict[str, Any]: Ingestion result details.
    """
    # 1. Fetch live weather data from Open-Meteo
    raw_weather = await fetch_open_meteo_weather(latitude=latitude, longitude=longitude)
    current = raw_weather.get("current", {})

    # 2. Normalize response to weather_events schema using deterministic classifier
    normalized_record = normalize_open_meteo_record(
        raw_data=raw_weather,
        latitude=latitude,
        longitude=longitude,
        city=city,
        state=state,
    )

    # 3. Check for duplicates if requested
    if skip_if_exists and weather_event_exists(normalized_record["source"], normalized_record["source_record_id"]):
        logger.info(
            "Weather event for %s (%s, %s) already exists. Skipping duplicate.",
            normalized_record["source_record_id"],
            city,
            state,
        )
        return {
            "status": "skipped",
            "message": "Duplicate observation already exists in database.",
            "source": normalized_record["source"],
            "source_record_id": normalized_record["source_record_id"],
            "event_type": normalized_record["event_type"],
            "city": city,
            "state": state,
            "weather_code": current.get("weather_code"),
            "is_duplicate": True,
        }

    # 4. Handle dry_run mode without database insertion
    if dry_run:
        return {
            "status": "dry_run",
            "message": "Dry run successful. Record validated but not inserted.",
            "source": normalized_record["source"],
            "source_record_id": normalized_record["source_record_id"],
            "event_type": normalized_record["event_type"],
            "city": city,
            "state": state,
            "weather_code": current.get("weather_code"),
            "normalized_record": normalized_record,
        }

    # 5. Insert record into database using parameterized SQL
    inserted_record = insert_weather_event(normalized_record)
    inserted_record["weather_code"] = current.get("weather_code")
    inserted_record["status"] = "inserted"

    return inserted_record
