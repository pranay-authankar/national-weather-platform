"""
AI-Ready Weather Report Credibility Evaluation & Source Trust Scoring Service.

Provides a deterministic, explainable credibility scoring layer for citizen weather reports
and source trust evaluation. Designed as an AI/ML-ready feature pipeline where heuristic
signals can seamlessly be augmented or replaced by a trained ML/LLM model in future iterations.

Core Signals:
1. Location Validity (+10 / -25): Geographic coordinates presence and range.
2. Timestamp Validity (+10 / -25): Recency and plausibility (no future or ancient reports).
3. Meaningful Description (+15 / -20): Content length, vocabulary, and spam/gibberish filtering.
4. Known Event Type (+10 / -15): Canonical weather classification conformance.
5. Meteorological Agreement (+25): Nearby sensor/official observation agrees with reported weather.
6. Corroborating Reports (+20): Independent, non-duplicate citizen reports nearby in space-time.
7. Meteorological Contradiction (-35): Nearby observations physically contradict the reported event.
8. Duplicate Report (-30): Report identified as duplicate of an existing event.
9. Incomplete/Invalid Content (-20 to -25): Missing fields or placeholder text.

Anti-False-Positive Rule:
Lack of nearby observation data does NOT mark a report as fake or suspicious.
An isolated report with valid fields remains 'Unverified' with a baseline score (~45.0).
"""

from datetime import datetime, timedelta, timezone
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

import psycopg
from database import get_db_connection, sanitize_error_message
from schemas.events import VALID_EVENT_TYPES
from services.duplicate_detection_service import calculate_event_type_similarity

logger = logging.getLogger(__name__)

# --- Machine-readable Reason Codes ---
REASON_VALID_LOCATION = "VALID_LOCATION"
REASON_INVALID_LOCATION = "INVALID_LOCATION"

REASON_VALID_TIMESTAMP = "VALID_TIMESTAMP"
REASON_FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
REASON_STALE_TIMESTAMP = "STALE_TIMESTAMP"
REASON_INVALID_TIMESTAMP = "INVALID_TIMESTAMP"

REASON_MEANINGFUL_DESCRIPTION = "MEANINGFUL_DESCRIPTION"
REASON_BRIEF_DESCRIPTION = "BRIEF_DESCRIPTION"
REASON_INCOMPLETE_OR_SPAM_DESCRIPTION = "INCOMPLETE_OR_SPAM_DESCRIPTION"

REASON_KNOWN_EVENT_TYPE = "KNOWN_EVENT_TYPE"
REASON_UNKNOWN_EVENT_TYPE = "UNKNOWN_EVENT_TYPE"

REASON_AGREES_WITH_WEATHER_OBSERVATION = "AGREES_WITH_WEATHER_OBSERVATION"
REASON_CORROBORATING_INDEPENDENT_REPORTS = "CORROBORATING_INDEPENDENT_REPORTS"
REASON_NO_NEARBY_OBSERVATION_DATA = "NO_NEARBY_OBSERVATION_DATA"
REASON_CONTRADICTORY_WEATHER_OBSERVATION = "CONTRADICTORY_WEATHER_OBSERVATION"

REASON_DUPLICATE_REPORT = "DUPLICATE_REPORT"
REASON_OFFICIAL_SOURCE = "OFFICIAL_SOURCE"

# --- Status Definitions ---
STATUS_VERIFIED = "Verified"
STATUS_LIKELY = "Likely"
STATUS_UNVERIFIED = "Unverified"
STATUS_SUSPICIOUS = "Suspicious"

# --- Status Thresholds ---
SCORE_THRESHOLD_VERIFIED_MIN = 80.0
SCORE_THRESHOLD_LIKELY_MIN = 55.0
SCORE_THRESHOLD_UNVERIFIED_MIN = 35.0

# --- Spatio-temporal Defaults ---
DEFAULT_CREDIBILITY_RADIUS_METERS = float(os.getenv("CREDIBILITY_RADIUS_KM", "25.0")) * 1000.0
DEFAULT_CREDIBILITY_TIME_WINDOW_SECONDS = float(os.getenv("CREDIBILITY_TIME_WINDOW_HOURS", "4.0")) * 3600.0

# Static Source Trust Constants
SOURCE_TRUST_IMD = 95.0
SOURCE_TRUST_IMD_RSS = 95.0
SOURCE_TRUST_DATA_GOV = 95.0
SOURCE_TRUST_OPEN_METEO = 90.0
SOURCE_TRUST_CITIZEN_BASE = 50.0
SOURCE_TRUST_DEFAULT = 50.0

OFFICIAL_SOURCES: Set[str] = {
    "IMD",
    "IMD_RSS",
    "Data_Gov",
    "Open_Meteo",
}

# Suspicious words / placeholders often submitted in test or spam submissions
SPAM_TOKENS: Set[str] = {
    "test",
    "testing",
    "fake",
    "asdf",
    "qwerty",
    "dummy",
    "sample",
    "demo",
    "foo",
    "bar",
    "blah",
    "random",
}


class CredibilityResult(TypedDict):
    """
    Standardized credibility scoring output.
    """
    credibility_score: float
    credibility_status: str
    credibility_reasons: List[str]
    evidence_summary: str
    source_trust_score: float


def is_valid_coordinate(latitude: Optional[float], longitude: Optional[float]) -> bool:
    """
    Validate that geographic coordinates exist and are within global boundaries.
    """
    if latitude is None or longitude is None:
        return False
    try:
        lat = float(latitude)
        lon = float(longitude)
        return (-90.0 <= lat <= 90.0) and (-180.0 <= lon <= 180.0)
    except (ValueError, TypeError):
        return False


def evaluate_location_signal(
    latitude: Optional[float],
    longitude: Optional[float],
) -> Tuple[float, List[str]]:
    """
    Evaluate geographic coordinates signal.
    """
    if is_valid_coordinate(latitude, longitude):
        return 10.0, [REASON_VALID_LOCATION]
    return -25.0, [REASON_INVALID_LOCATION]


def evaluate_timestamp_signal(
    event_timestamp: Optional[datetime],
) -> Tuple[float, List[str]]:
    """
    Evaluate observation timestamp plausibility.
    Accepts timestamps up to 1 hour in the future (to accommodate minor client clock skew)
    and not older than 30 days.
    """
    if event_timestamp is None or not isinstance(event_timestamp, datetime):
        return -20.0, [REASON_INVALID_TIMESTAMP]

    now = datetime.now(timezone.utc)
    ts = event_timestamp if event_timestamp.tzinfo else event_timestamp.replace(tzinfo=timezone.utc)

    # Future check (more than 1 hour in the future)
    if ts > now + timedelta(hours=1):
        return -25.0, [REASON_FUTURE_TIMESTAMP]

    # Stale check (older than 30 days)
    if ts < now - timedelta(days=30):
        return -15.0, [REASON_STALE_TIMESTAMP]

    return 10.0, [REASON_VALID_TIMESTAMP]


def evaluate_description_signal(
    description: Optional[str],
) -> Tuple[float, List[str]]:
    """
    Evaluate eyewitness description content.
    Identifies meaningful descriptions, short notes, and obviously spam/incomplete text.
    """
    if not description or not isinstance(description, str):
        return -20.0, [REASON_INCOMPLETE_OR_SPAM_DESCRIPTION]

    trimmed = description.strip()
    if len(trimmed) < 5:
        return -20.0, [REASON_INCOMPLETE_OR_SPAM_DESCRIPTION]

    # Check for repetitive single-character sequences (e.g. "aaaaa", ".....")
    compact_chars = re.sub(r"\s+", "", trimmed.lower())
    if len(set(compact_chars)) <= 2:
        return -20.0, [REASON_INCOMPLETE_OR_SPAM_DESCRIPTION]

    # Tokenize and inspect for spam/placeholder patterns
    words = [w.lower() for w in re.findall(r"\b\w+\b", trimmed)]
    if words and all(w in SPAM_TOKENS for w in words):
        return -20.0, [REASON_INCOMPLETE_OR_SPAM_DESCRIPTION]

    # Meaningful description: sufficient length and informative word count
    if len(trimmed) >= 15 and len(words) >= 3:
        return 15.0, [REASON_MEANINGFUL_DESCRIPTION]

    # Brief description: between 5 and 14 chars or few words
    return 5.0, [REASON_BRIEF_DESCRIPTION]


def evaluate_event_type_signal(
    event_type: Optional[str],
) -> Tuple[float, List[str]]:
    """
    Evaluate weather event classification conformance.
    """
    if not event_type or not isinstance(event_type, str):
        return -15.0, [REASON_UNKNOWN_EVENT_TYPE]

    trimmed = event_type.strip()
    if trimmed in VALID_EVENT_TYPES:
        return 10.0, [REASON_KNOWN_EVENT_TYPE]

    # Check case-insensitive match
    lower_map = {t.lower(): t for t in VALID_EVENT_TYPES}
    if trimmed.lower() in lower_map:
        return 10.0, [REASON_KNOWN_EVENT_TYPE]

    return -15.0, [REASON_UNKNOWN_EVENT_TYPE]


def evaluate_weather_observation_consistency(
    event_type: str,
    nearby_observations: List[Dict[str, Any]],
) -> Tuple[float, List[str], Optional[str]]:
    """
    Evaluate physical consistency and agreement against real nearby official/sensor weather observations.

    Returns:
        (score_adjustment, reasons, explanation_note)
    """
    if not nearby_observations:
        # Crucial anti-false-positive rule: Lack of nearby weather data remains neutral Unverified
        return 0.0, [REASON_NO_NEARBY_OBSERVATION_DATA], None

    norm_type = event_type.strip()

    # 1. Contradiction Detection
    for obs in nearby_observations:
        temp = obs.get("temperature")
        rain = obs.get("rainfall")
        humidity = obs.get("humidity")
        wind = obs.get("wind_speed")
        obs_type = obs.get("event_type", "")

        # Contradiction A: Heatwave claimed during cold/mild weather or active heavy rainfall
        if norm_type == "Heatwave":
            if (temp is not None and temp < 24.0) or (rain is not None and rain >= 5.0):
                note = f"Reported Heatwave but nearby observation recorded {temp}°C and {rain}mm rain."
                return -35.0, [REASON_CONTRADICTORY_WEATHER_OBSERVATION], note

        # Contradiction B: Severe rain/flooding claimed during zero rain, low humidity, and high heat
        elif norm_type in ("Rainfall", "Heavy Rain", "Thunderstorm", "Flooding"):
            if (
                rain is not None and rain == 0.0
                and humidity is not None and humidity < 35.0
                and temp is not None and temp >= 38.0
            ):
                note = f"Reported {norm_type} but nearby observation recorded 0mm rain, {humidity}% humidity, and {temp}°C."
                return -35.0, [REASON_CONTRADICTORY_WEATHER_OBSERVATION], note

        # Contradiction C: Fog claimed under hot, arid conditions
        elif norm_type == "Fog":
            if (
                temp is not None and temp >= 35.0
                and humidity is not None and humidity < 40.0
            ):
                note = f"Reported Fog but nearby observation recorded {temp}°C and {humidity}% humidity."
                return -35.0, [REASON_CONTRADICTORY_WEATHER_OBSERVATION], note

        # Contradiction D: Dust storm claimed during heavy downpour
        elif norm_type == "Dust Storm":
            if rain is not None and rain >= 10.0:
                note = f"Reported Dust Storm during active {rain}mm rainfall."
                return -35.0, [REASON_CONTRADICTORY_WEATHER_OBSERVATION], note

        # Contradiction E: Cyclone claimed with calm winds and high pressure
        elif norm_type == "Cyclone":
            if wind is not None and wind < 12.0:
                note = f"Reported Cyclone but nearby station recorded calm wind speed of {wind} km/h."
                return -35.0, [REASON_CONTRADICTORY_WEATHER_OBSERVATION], note

    # 2. Positive Agreement Detection
    for obs in nearby_observations:
        temp = obs.get("temperature")
        rain = obs.get("rainfall")
        humidity = obs.get("humidity")
        wind = obs.get("wind_speed")
        obs_type = obs.get("event_type", "")

        # Agreement A: Rain / storm conditions
        if norm_type in ("Rainfall", "Heavy Rain", "Thunderstorm", "Flooding"):
            if (rain is not None and rain > 0.0) or (humidity is not None and humidity >= 70.0):
                return 25.0, [REASON_AGREES_WITH_WEATHER_OBSERVATION], "Corroborated by nearby precipitation/humidity observation."
            if obs_type in ("Rainfall", "Heavy Rain", "Thunderstorm", "Flooding"):
                return 25.0, [REASON_AGREES_WITH_WEATHER_OBSERVATION], f"Corroborated by nearby {obs_type} observation."

        # Agreement B: Heatwave conditions
        elif norm_type == "Heatwave":
            if (temp is not None and temp >= 38.0) or obs_type == "Heatwave":
                return 25.0, [REASON_AGREES_WITH_WEATHER_OBSERVATION], f"Corroborated by high temperature ({temp}°C) observation."

        # Agreement C: Wind / Cyclone
        elif norm_type in ("Strong Wind", "Cyclone"):
            if (wind is not None and wind >= 25.0) or obs_type in ("Strong Wind", "Cyclone"):
                return 25.0, [REASON_AGREES_WITH_WEATHER_OBSERVATION], f"Corroborated by elevated wind speed ({wind} km/h)."

        # Agreement D: Fog
        elif norm_type == "Fog":
            if (humidity is not None and humidity >= 85.0) or obs_type == "Fog":
                return 25.0, [REASON_AGREES_WITH_WEATHER_OBSERVATION], "Corroborated by high relative humidity observation."

        # Agreement E: Compatible event type
        sim = calculate_event_type_similarity(norm_type, obs_type)
        if sim >= 0.5:
            return 25.0, [REASON_AGREES_WITH_WEATHER_OBSERVATION], f"Compatible with nearby {obs_type} record."

    # Inconclusive observation (exists, but neither confirms nor contradicts)
    return 0.0, [], None


def evaluate_corroborating_citizen_reports(
    event_type: str,
    nearby_citizen_reports: List[Dict[str, Any]],
) -> Tuple[float, List[str]]:
    """
    Evaluate presence of independent, non-duplicate citizen reports nearby in space-time.
    """
    if not nearby_citizen_reports:
        return 0.0, []

    # Count reports with compatible event types
    matching_reports = [
        r for r in nearby_citizen_reports
        if calculate_event_type_similarity(event_type, r.get("event_type", "")) > 0.0
    ]

    if matching_reports:
        return 20.0, [REASON_CORROBORATING_INDEPENDENT_REPORTS]

    return 0.0, []


def evaluate_duplicate_signal(
    is_duplicate: bool,
    duplicate_of: Optional[str] = None,
) -> Tuple[float, List[str]]:
    """
    Evaluate duplicate penalty signal.
    """
    if is_duplicate or duplicate_of:
        return -30.0, [REASON_DUPLICATE_REPORT]
    return 0.0, []


def map_score_to_credibility_status(score: float) -> str:
    """
    Map final numeric credibility score (0-100) to credibility status:
    - 80.0 to 100.0: Verified
    - 55.0 to 79.9: Likely
    - 35.0 to 54.9: Unverified
    - Below 35.0: Suspicious
    """
    if score >= SCORE_THRESHOLD_VERIFIED_MIN:
        return STATUS_VERIFIED
    if score >= SCORE_THRESHOLD_LIKELY_MIN:
        return STATUS_LIKELY
    if score >= SCORE_THRESHOLD_UNVERIFIED_MIN:
        return STATUS_UNVERIFIED
    return STATUS_SUSPICIOUS


def calculate_source_trust_score(
    source: str,
    historical_stats: Optional[Dict[str, int]] = None,
) -> float:
    """
    Calculate source trust score (0.0–100.0) based on source origin and real historical records.

    Rules:
    - IMD / IMD_RSS / Data_Gov: 95.0 (official government baseline)
    - Open_Meteo: 90.0 (established external meteorological data)
    - Citizen_Report: Dynamic trust calculated from real historical outcomes in database:
      * Base neutral trust: 50.0 (if no historical citizen records exist)
      * Verified reports increase trust (+4.0)
      * Likely reports moderately increase trust (+1.5)
      * Rejected / Suspicious reports decrease trust (-5.0)
      * Duplicates do NOT artificially increase trust
      * Clamped between 10.0 and 90.0
    - Other sources: 50.0
    """
    if source in ("IMD", "IMD_RSS"):
        return SOURCE_TRUST_IMD
    if source == "Data_Gov":
        return SOURCE_TRUST_DATA_GOV
    if source == "Open_Meteo":
        return SOURCE_TRUST_OPEN_METEO
    if source != "Citizen_Report":
        return SOURCE_TRUST_DEFAULT

    # Dynamic calculation for Citizen_Report
    stats = historical_stats
    if stats is None:
        stats = fetch_citizen_historical_stats()

    total_count = stats.get("total_count", 0)
    if total_count == 0:
        # Baseline neutral trust when no historical citizen records exist
        return SOURCE_TRUST_CITIZEN_BASE

    verified_count = stats.get("verified_count", 0)
    likely_count = stats.get("likely_count", 0)
    suspicious_count = stats.get("suspicious_count", 0)

    dynamic_score = (
        SOURCE_TRUST_CITIZEN_BASE
        + (verified_count * 4.0)
        + (likely_count * 1.5)
        - (suspicious_count * 5.0)
    )

    clamped_score = max(10.0, min(90.0, dynamic_score))
    return round(clamped_score, 1)


def fetch_citizen_historical_stats() -> Dict[str, int]:
    """
    Query PostgreSQL for actual historical citizen report outcomes.
    Does not invent statistics.
    """
    sql = """
        SELECT
            COUNT(*) AS total_count,
            COUNT(*) FILTER (WHERE credibility_status = 'Verified' OR verification_status = 'Verified') AS verified_count,
            COUNT(*) FILTER (WHERE credibility_status = 'Likely' OR verification_status = 'Likely') AS likely_count,
            COUNT(*) FILTER (WHERE credibility_status = 'Suspicious' OR verification_status = 'Rejected') AS suspicious_count,
            COUNT(*) FILTER (WHERE duplicate_of IS NOT NULL OR verification_status = 'Duplicate') AS duplicate_count
        FROM public.weather_events
        WHERE source = 'Citizen_Report';
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
                if row:
                    return {
                        "total_count": int(row[0]),
                        "verified_count": int(row[1]),
                        "likely_count": int(row[2]),
                        "suspicious_count": int(row[3]),
                        "duplicate_count": int(row[4]),
                    }
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.warning("Could not fetch citizen historical stats: %s. Using neutral base.", sanitized)

    return {
        "total_count": 0,
        "verified_count": 0,
        "likely_count": 0,
        "suspicious_count": 0,
        "duplicate_count": 0,
    }


def find_nearby_weather_data(
    latitude: float,
    longitude: float,
    event_timestamp: datetime,
    max_distance_meters: float = DEFAULT_CREDIBILITY_RADIUS_METERS,
    max_time_diff_seconds: float = DEFAULT_CREDIBILITY_TIME_WINDOW_SECONDS,
    exclude_event_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Query PostgreSQL via PostGIS for nearby weather events within spatio-temporal radius.
    Partitions results into:
    1. Official weather observations (Open_Meteo, IMD, IMD_RSS, Data_Gov) with meteorological values.
    2. Independent citizen reports (Citizen_Report) that are not duplicates.
    """
    if event_timestamp.tzinfo is None:
        event_timestamp = event_timestamp.replace(tzinfo=timezone.utc)

    min_time = event_timestamp - timedelta(seconds=max_time_diff_seconds)
    max_time = event_timestamp + timedelta(seconds=max_time_diff_seconds)

    query = """
        SELECT
            event_id,
            source,
            event_type,
            description,
            event_timestamp,
            latitude,
            longitude,
            temperature,
            rainfall,
            humidity,
            wind_speed,
            wind_direction,
            pressure,
            verification_status,
            credibility_status,
            duplicate_of,
            ST_Distance(
                COALESCE(location, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography),
                ST_SetSRID(ST_MakePoint(%(target_lon)s, %(target_lat)s), 4326)::geography
            ) AS distance_meters
        FROM public.weather_events
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

    official_observations: List[Dict[str, Any]] = []
    citizen_reports: List[Dict[str, Any]] = []

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                for r in rows:
                    rec = {
                        "event_id": str(r[0]),
                        "source": str(r[1]),
                        "event_type": str(r[2]),
                        "description": r[3],
                        "event_timestamp": r[4],
                        "latitude": float(r[5]) if r[5] is not None else None,
                        "longitude": float(r[6]) if r[6] is not None else None,
                        "temperature": float(r[7]) if r[7] is not None else None,
                        "rainfall": float(r[8]) if r[8] is not None else None,
                        "humidity": float(r[9]) if r[9] is not None else None,
                        "wind_speed": float(r[10]) if r[10] is not None else None,
                        "wind_direction": float(r[11]) if r[11] is not None else None,
                        "pressure": float(r[12]) if r[12] is not None else None,
                        "verification_status": str(r[13]) if r[13] else None,
                        "credibility_status": str(r[14]) if r[14] else None,
                        "duplicate_of": str(r[15]) if r[15] is not None else None,
                        "distance_meters": float(r[16]),
                    }

                    if rec["source"] in OFFICIAL_SOURCES:
                        official_observations.append(rec)
                    elif rec["source"] == "Citizen_Report":
                        # Only consider non-duplicate citizen reports as potential corroborators
                        if not rec["duplicate_of"] and rec["verification_status"] != "Duplicate":
                            citizen_reports.append(rec)
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.warning("Failed querying nearby weather data for credibility: %s", sanitized)

    return official_observations, citizen_reports


def calculate_report_credibility(
    latitude: Optional[float],
    longitude: Optional[float],
    event_timestamp: Optional[datetime],
    event_type: Optional[str],
    description: Optional[str],
    is_duplicate: bool = False,
    duplicate_of: Optional[str] = None,
    nearby_observations: Optional[List[Dict[str, Any]]] = None,
    nearby_citizen_reports: Optional[List[Dict[str, Any]]] = None,
    source: str = "Citizen_Report",
    historical_stats: Optional[Dict[str, int]] = None,
) -> CredibilityResult:
    """
    Calculate credibility score (0-100), credibility status, concise machine-readable reasons,
    and evidence summary using deterministic signals.
    """
    reasons: List[str] = []
    positive_notes: List[str] = []
    negative_notes: List[str] = []
    accumulated_score: float = 0.0

    # 1. Location signal
    loc_score, loc_reasons = evaluate_location_signal(latitude, longitude)
    accumulated_score += loc_score
    reasons.extend(loc_reasons)
    if loc_score > 0:
        positive_notes.append("Valid GPS coordinates")
    else:
        negative_notes.append("Missing or invalid GPS coordinates")

    # 2. Timestamp signal
    ts_score, ts_reasons = evaluate_timestamp_signal(event_timestamp)
    accumulated_score += ts_score
    reasons.extend(ts_reasons)
    if ts_score > 0:
        positive_notes.append("Valid recent observation timestamp")
    elif REASON_FUTURE_TIMESTAMP in ts_reasons:
        negative_notes.append("Observation timestamp is in the future")
    elif REASON_STALE_TIMESTAMP in ts_reasons:
        negative_notes.append("Observation timestamp is older than 30 days")
    else:
        negative_notes.append("Invalid timestamp format")

    # 3. Description signal
    desc_score, desc_reasons = evaluate_description_signal(description)
    accumulated_score += desc_score
    reasons.extend(desc_reasons)
    if desc_score >= 10:
        positive_notes.append("Detailed and meaningful eyewitness description")
    elif desc_score > 0:
        positive_notes.append("Brief eyewitness note")
    else:
        negative_notes.append("Incomplete, repetitive, or placeholder description")

    # 4. Known event type signal
    type_score, type_reasons = evaluate_event_type_signal(event_type)
    accumulated_score += type_score
    reasons.extend(type_reasons)
    if type_score > 0:
        positive_notes.append(f"Standard weather classification '{event_type}'")
    else:
        negative_notes.append(f"Unrecognized weather classification '{event_type}'")

    # 5. Nearby weather observation agreement / contradiction
    obs_score, obs_reasons, obs_note = evaluate_weather_observation_consistency(
        event_type=event_type or "",
        nearby_observations=nearby_observations or [],
    )
    accumulated_score += obs_score
    reasons.extend(obs_reasons)
    if obs_score > 0 and obs_note:
        positive_notes.append(obs_note)
    elif obs_score < 0 and obs_note:
        negative_notes.append(obs_note)
    elif REASON_NO_NEARBY_OBSERVATION_DATA in obs_reasons:
        positive_notes.append("No nearby official weather station within radius (neutral)")

    # 6. Corroborating independent reports
    corrob_score, corrob_reasons = evaluate_corroborating_citizen_reports(
        event_type=event_type or "",
        nearby_citizen_reports=nearby_citizen_reports or [],
    )
    accumulated_score += corrob_score
    reasons.extend(corrob_reasons)
    if corrob_score > 0:
        positive_notes.append("Corroborated by independent nearby citizen report(s)")

    # 7. Duplicate penalty
    dup_score, dup_reasons = evaluate_duplicate_signal(is_duplicate, duplicate_of)
    accumulated_score += dup_score
    reasons.extend(dup_reasons)
    if dup_score < 0:
        negative_notes.append("Identified as duplicate of an existing event")

    # Clamp final score between 0.0 and 100.0
    final_score = round(max(0.0, min(100.0, accumulated_score)), 1)
    status = map_score_to_credibility_status(final_score)

    # Compute source trust score
    source_trust = calculate_source_trust_score(
        source=source,
        historical_stats=historical_stats,
    )

    # Build human-readable evidence summary
    pos_str = "; ".join(positive_notes) if positive_notes else "None"
    neg_str = "; ".join(negative_notes) if negative_notes else "None"
    evidence_summary = (
        f"Credibility: {status} ({final_score}/100.0). "
        f"Positive signals: [{pos_str}]. "
        f"Negative signals: [{neg_str}]."
    )

    return {
        "credibility_score": final_score,
        "credibility_status": status,
        "credibility_reasons": reasons,
        "evidence_summary": evidence_summary,
        "source_trust_score": source_trust,
    }


async def evaluate_and_score_citizen_report(
    latitude: Optional[float],
    longitude: Optional[float],
    event_timestamp: Optional[datetime],
    event_type: Optional[str],
    description: Optional[str],
    is_duplicate: bool = False,
    duplicate_of: Optional[str] = None,
    exclude_event_id: Optional[str] = None,
    nearby_observations_override: Optional[List[Dict[str, Any]]] = None,
    nearby_citizen_override: Optional[List[Dict[str, Any]]] = None,
    historical_stats_override: Optional[Dict[str, int]] = None,
) -> CredibilityResult:
    """
    Main asynchronous pipeline for citizen report credibility and source trust scoring.
    """
    nearby_observations: List[Dict[str, Any]] = []
    nearby_citizen_reports: List[Dict[str, Any]] = []

    if nearby_observations_override is not None:
        nearby_observations = nearby_observations_override
    if nearby_citizen_override is not None:
        nearby_citizen_reports = nearby_citizen_override

    # Query database if overrides were not explicitly provided and location is valid
    if (
        nearby_observations_override is None
        and nearby_citizen_override is None
        and is_valid_coordinate(latitude, longitude)
        and event_timestamp is not None
    ):
        try:
            obs, cits = find_nearby_weather_data(
                latitude=float(latitude),  # type: ignore[arg-type]
                longitude=float(longitude),  # type: ignore[arg-type]
                event_timestamp=event_timestamp,
                exclude_event_id=exclude_event_id,
            )
            nearby_observations = obs
            nearby_citizen_reports = cits
        except Exception as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.warning("Error fetching nearby weather data: %s", sanitized)

    return calculate_report_credibility(
        latitude=latitude,
        longitude=longitude,
        event_timestamp=event_timestamp,
        event_type=event_type,
        description=description,
        is_duplicate=is_duplicate,
        duplicate_of=duplicate_of,
        nearby_observations=nearby_observations,
        nearby_citizen_reports=nearby_citizen_reports,
        source="Citizen_Report",
        historical_stats=historical_stats_override,
    )
