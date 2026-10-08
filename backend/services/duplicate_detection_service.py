"""
Service for detecting duplicate weather reports in public.weather_events.

Evaluates:
- Geographic proximity using PostGIS ST_DWithin and ST_Distance on geography type.
- Time proximity within a configurable time window.
- Weather event type compatibility (identical or shared weather phenomenon cluster).
- Text similarity via deterministic normalization and similarity metrics.

Returns a duplicate candidate only when combined multi-factor evidence is sufficiently strong.
Fault-tolerant: database/query failures safely return no duplicate without crashing the application.
"""

from datetime import datetime, timedelta, timezone
import difflib
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

import psycopg
from database import get_db_connection, sanitize_error_message

logger = logging.getLogger(__name__)

# --- Configurable Thresholds & Constants ---

# Geographic proximity threshold (default: 2.0 km)
DEFAULT_MAX_DISTANCE_KM: float = float(os.getenv("DUPLICATE_MAX_DISTANCE_KM", "2.0"))
DEFAULT_MAX_DISTANCE_METERS: float = DEFAULT_MAX_DISTANCE_KM * 1000.0

# Temporal proximity threshold (default: 2.0 hours)
DEFAULT_MAX_TIME_DIFF_HOURS: float = float(os.getenv("DUPLICATE_MAX_TIME_DIFF_HOURS", "2.0"))
DEFAULT_MAX_TIME_DIFF_SECONDS: float = DEFAULT_MAX_TIME_DIFF_HOURS * 3600.0

# Combined confidence threshold to mark as Duplicate (default: 65.0%)
DEFAULT_CONFIDENCE_THRESHOLD: float = float(os.getenv("DUPLICATE_CONFIDENCE_THRESHOLD", "65.0"))

# Compatible weather event clusters (case-insensitive)
COMPATIBLE_EVENT_CLUSTERS: List[Set[str]] = [
    {"Rainfall", "Heavy Rain", "Flooding", "Thunderstorm"},
    {"Strong Wind", "Thunderstorm", "Cyclone"},
    {"Dust Storm", "Strong Wind"},
]

# Lightweight English stopwords for text normalization
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "could", "did", "do", "does", "doing", "down", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "it", "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor",
    "not", "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "with", "would", "you", "your", "yours", "yourself", "yourselves",
    "near", "area", "seen", "reported", "noticed", "heavy", "moderate", "light",
}


class DuplicateDetectionResult(TypedDict):
    """
    Result dictionary returned by duplicate detection service.
    """
    is_duplicate: bool
    duplicate_of: Optional[str]
    confidence_score: Optional[float]
    details: Optional[Dict[str, Any]]


def calculate_event_type_similarity(type1: str, type2: str) -> float:
    """
    Compute compatibility score between two event types:
    - 1.0 for exact (case-insensitive) match
    - 0.75 for compatible event cluster match (e.g. Heavy Rain and Flooding)
    - 0.0 for incompatible types (e.g. Heatwave and Heavy Rain)
    """
    if not type1 or not type2:
        return 0.0

    t1 = type1.strip().lower()
    t2 = type2.strip().lower()

    if t1 == t2:
        return 1.0

    for cluster in COMPATIBLE_EVENT_CLUSTERS:
        cluster_lower = {c.lower() for c in cluster}
        if t1 in cluster_lower and t2 in cluster_lower:
            return 0.75

    return 0.0


def normalize_text(text: Optional[str]) -> str:
    """
    Deterministic text normalization for lightweight comparison:
    - Lowercase
    - Strip punctuation and symbols
    - Remove common English stop words
    """
    if not text:
        return ""
    lowered = text.lower()
    cleaned = re.sub(r"[^\w\s]", " ", lowered)
    tokens = cleaned.split()
    filtered = [w for w in tokens if w not in STOP_WORDS and len(w) > 1]
    return " ".join(filtered)


def calculate_text_similarity(desc1: Optional[str], desc2: Optional[str]) -> Optional[float]:
    """
    Calculate text similarity between two descriptions:
    - Returns None if either description is missing or blank (neutral evidence).
    - Returns float in [0.0, 1.0] using blended Jaccard token overlap and sequence ratio.
    """
    if not desc1 or not desc2:
        return None

    n1 = normalize_text(desc1)
    n2 = normalize_text(desc2)

    if not n1 or not n2:
        return None

    tokens1 = set(n1.split())
    tokens2 = set(n2.split())

    if not tokens1 or not tokens2:
        return None

    jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)
    seq_ratio = difflib.SequenceMatcher(None, n1, n2).ratio()

    return max(jaccard, seq_ratio)


def find_spatial_temporal_candidates(
    latitude: float,
    longitude: float,
    event_timestamp: datetime,
    max_distance_meters: float = DEFAULT_MAX_DISTANCE_METERS,
    max_time_diff_seconds: float = DEFAULT_MAX_TIME_DIFF_SECONDS,
) -> List[Dict[str, Any]]:
    """
    Query PostgreSQL using PostGIS geography ST_DWithin and ST_Distance to retrieve
    spatio-temporal candidates within distance and time windows.

    Avoids loading the entire table into memory by executing indexed spatial filtering.
    """
    # Ensure timezone awareness on timestamp
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
        ORDER BY distance_meters ASC
        LIMIT 25;
    """

    candidates: List[Dict[str, Any]] = []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {
                "target_lat": latitude,
                "target_lon": longitude,
                "min_time": min_time,
                "max_time": max_time,
                "max_distance_meters": max_distance_meters,
            })
            rows = cur.fetchall()
            for r in rows:
                candidates.append({
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
                })

    return candidates


def evaluate_candidate(
    new_event_type: str,
    new_timestamp: datetime,
    new_description: Optional[str],
    candidate: Dict[str, Any],
    max_distance_meters: float = DEFAULT_MAX_DISTANCE_METERS,
    max_time_diff_seconds: float = DEFAULT_MAX_TIME_DIFF_SECONDS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Tuple[bool, float, Dict[str, Any]]:
    """
    Score a single candidate against the new report.
    Returns:
        (is_duplicate, confidence_score, score_breakdown)
    """
    distance_meters = candidate["distance_meters"]
    cand_timestamp = candidate["event_timestamp"]
    cand_type = candidate["event_type"]
    cand_desc = candidate.get("description")

    # Hard geographic distance cutoff
    if distance_meters > max_distance_meters:
        return False, 0.0, {"reason": "Distance exceeded"}

    # Hard temporal cutoff
    if cand_timestamp.tzinfo is None:
        cand_timestamp = cand_timestamp.replace(tzinfo=timezone.utc)
    if new_timestamp.tzinfo is None:
        new_timestamp = new_timestamp.replace(tzinfo=timezone.utc)

    time_diff_seconds = abs((new_timestamp - cand_timestamp).total_seconds())
    if time_diff_seconds > max_time_diff_seconds:
        return False, 0.0, {"reason": "Time window exceeded"}

    # Hard event type compatibility cutoff
    type_sim = calculate_event_type_similarity(new_event_type, cand_type)
    if type_sim <= 0.0:
        return False, 0.0, {"reason": "Incompatible event type"}

    # Normalized component scores [0.0, 1.0]
    s_dist = max(0.0, 1.0 - (distance_meters / max_distance_meters))
    s_time = max(0.0, 1.0 - (time_diff_seconds / max_time_diff_seconds))
    s_type = type_sim

    text_sim = calculate_text_similarity(new_description, cand_desc)

    # Composite score formula:
    # When text is available, text adds positive evidence.
    # When text is missing on either record, rely on spatio-temporal and type evidence.
    if text_sim is not None:
        composite = (
            0.40 * s_dist +
            0.30 * s_time +
            0.15 * s_type +
            0.15 * text_sim
        ) * 100.0
    else:
        composite = (
            0.45 * s_dist +
            0.35 * s_time +
            0.20 * s_type
        ) * 100.0

    is_duplicate = composite >= confidence_threshold

    breakdown = {
        "candidate_id": candidate["event_id"],
        "candidate_source": candidate["source"],
        "distance_meters": round(distance_meters, 1),
        "time_diff_seconds": round(time_diff_seconds, 1),
        "spatial_score": round(s_dist, 3),
        "temporal_score": round(s_time, 3),
        "type_score": round(s_type, 3),
        "text_similarity": round(text_sim, 3) if text_sim is not None else None,
        "confidence_score": round(composite, 2),
    }

    return is_duplicate, composite, breakdown


async def detect_duplicate_report(
    latitude: float,
    longitude: float,
    event_timestamp: datetime,
    event_type: str,
    description: Optional[str] = None,
    max_distance_meters: float = DEFAULT_MAX_DISTANCE_METERS,
    max_time_diff_seconds: float = DEFAULT_MAX_TIME_DIFF_SECONDS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> DuplicateDetectionResult:
    """
    Primary entry point to detect whether a citizen report is a duplicate of an existing event.

    Guarantees:
    - Never raises unhandled exceptions. If database or network fails, logs safely
      and returns is_duplicate=False so submission continues uninterrupted.
    - If a duplicate candidate is identified with confidence >= threshold:
      returns is_duplicate=True and the canonical root duplicate_of event ID.
    - If no candidate meets threshold: returns is_duplicate=False and duplicate_of=None.
    """
    try:
        candidates = find_spatial_temporal_candidates(
            latitude=latitude,
            longitude=longitude,
            event_timestamp=event_timestamp,
            max_distance_meters=max_distance_meters,
            max_time_diff_seconds=max_time_diff_seconds,
        )

        if not candidates:
            return {
                "is_duplicate": False,
                "duplicate_of": None,
                "confidence_score": None,
                "details": None,
            }

        best_candidate: Optional[Dict[str, Any]] = None
        best_score: float = -1.0
        best_breakdown: Optional[Dict[str, Any]] = None

        for cand in candidates:
            is_dup, score, breakdown = evaluate_candidate(
                new_event_type=event_type,
                new_timestamp=event_timestamp,
                new_description=description,
                candidate=cand,
                max_distance_meters=max_distance_meters,
                max_time_diff_seconds=max_time_diff_seconds,
                confidence_threshold=confidence_threshold,
            )

            if is_dup and score > best_score:
                best_score = score
                best_candidate = cand
                best_breakdown = breakdown

        if best_candidate and best_score >= confidence_threshold:
            # If candidate was itself a duplicate of another event, resolve to the root original
            canonical_original_id = best_candidate.get("duplicate_of") or best_candidate["event_id"]
            logger.info(
                "Duplicate detected for report (lat=%s, lon=%s): matches original %s (confidence=%.1f%%)",
                latitude,
                longitude,
                canonical_original_id,
                best_score,
            )
            return {
                "is_duplicate": True,
                "duplicate_of": canonical_original_id,
                "confidence_score": round(best_score, 2),
                "details": best_breakdown,
            }

        return {
            "is_duplicate": False,
            "duplicate_of": None,
            "confidence_score": None,
            "details": None,
        }

    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.warning(
            "Duplicate detection encountered an error for (%s, %s): %s. Defaulting to Unverified.",
            latitude,
            longitude,
            sanitized,
        )
        return {
            "is_duplicate": False,
            "duplicate_of": None,
            "confidence_score": None,
            "details": None,
        }
