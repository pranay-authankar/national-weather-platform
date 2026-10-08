"""
Service module for periodic, background Open-Meteo weather data ingestion.
Utilizes APScheduler (AsyncIOScheduler) to orchestrate continuous meteorological polling
across configured Indian administrative locations without blocking FastAPI request handling.
"""

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import sanitize_error_message
from services.weather_event_service import ingest_open_meteo_weather

logger = logging.getLogger(__name__)

# Default continuous ingestion interval (in minutes)
DEFAULT_INTERVAL_MINUTES: int = 30

# Canonical default Indian monitoring locations spanning key meteorological zones
DEFAULT_LOCATIONS: List[Dict[str, Any]] = [
    {"city": "New Delhi", "state": "Delhi", "latitude": 28.6139, "longitude": 77.2090},
    {"city": "Mumbai", "state": "Maharashtra", "latitude": 19.0760, "longitude": 72.8777},
    {"city": "Kolkata", "state": "West Bengal", "latitude": 22.5726, "longitude": 88.3639},
    {"city": "Chennai", "state": "Tamil Nadu", "latitude": 13.0827, "longitude": 80.2707},
    {"city": "Bengaluru", "state": "Karnataka", "latitude": 12.9716, "longitude": 77.5946},
    {"city": "Hyderabad", "state": "Telangana", "latitude": 17.3850, "longitude": 78.4867},
    {"city": "Ahmedabad", "state": "Gujarat", "latitude": 23.0225, "longitude": 72.5714},
    {"city": "Jaipur", "state": "Rajasthan", "latitude": 26.9124, "longitude": 75.7873},
    {"city": "Guwahati", "state": "Assam", "latitude": 26.1445, "longitude": 91.7362},
    {"city": "Raipur", "state": "Chhattisgarh", "latitude": 21.2500, "longitude": 81.6300},
]

# Module-level singleton scheduler instance and state tracker
_scheduler: Optional[AsyncIOScheduler] = None
_last_run_timestamp: Optional[str] = None
_last_run_status: Optional[str] = None
_last_run_summary: Optional[Dict[str, Any]] = None


def get_configured_locations() -> List[Dict[str, Any]]:
    """
    Retrieve list of Indian locations to monitor from environment or defaults.
    Format in .env: JSON array of objects with city, state, latitude, longitude.
    """
    env_locations = os.getenv("OPEN_METEO_INGESTION_LOCATIONS")
    if env_locations:
        try:
            parsed = json.loads(env_locations)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception as exc:
            logger.warning(
                "Failed to parse OPEN_METEO_INGESTION_LOCATIONS JSON: %s. Falling back to defaults.",
                exc,
            )
    return DEFAULT_LOCATIONS


def get_configured_interval_minutes() -> int:
    """
    Retrieve polling interval in minutes from environment or default (30 min).
    """
    env_interval = os.getenv("OPEN_METEO_INGESTION_INTERVAL_MINUTES")
    if env_interval:
        try:
            interval = int(env_interval)
            if interval > 0:
                return interval
        except ValueError:
            logger.warning(
                "Invalid OPEN_METEO_INGESTION_INTERVAL_MINUTES '%s'. Using default %d.",
                env_interval,
                DEFAULT_INTERVAL_MINUTES,
            )
    return DEFAULT_INTERVAL_MINUTES


def is_ingestion_enabled() -> bool:
    """
    Check whether background ingestion is enabled (default: true).
    """
    return os.getenv("OPEN_METEO_INGESTION_ENABLED", "true").lower() in ("true", "1", "yes")


async def run_open_meteo_ingestion_job(
    dry_run: bool = False,
    custom_locations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Execute a batch polling cycle across configured Indian locations.
    Gracefully handles individual location failures and skips duplicates.

    Parameters:
        dry_run: If True, fetches and parses real data without database insertion.
        custom_locations: Optional override list of locations to process.

    Returns:
        Dict[str, Any]: Summary of batch execution.
    """
    global _last_run_timestamp, _last_run_status, _last_run_summary

    locations = custom_locations if custom_locations is not None else get_configured_locations()
    start_time = datetime.now(timezone.utc)
    logger.info("Starting Open-Meteo ingestion job for %d location(s) (dry_run=%s).", len(locations), dry_run)

    successful = 0
    skipped_duplicates = 0
    failed = 0
    details: List[Dict[str, Any]] = []

    for loc in locations:
        city = loc.get("city")
        state = loc.get("state")
        lat = loc.get("latitude")
        lon = loc.get("longitude")

        try:
            result = await ingest_open_meteo_weather(
                latitude=float(lat),
                longitude=float(lon),
                city=city,
                state=state,
                skip_if_exists=True,
                dry_run=dry_run,
            )

            if result.get("status") == "skipped":
                skipped_duplicates += 1
                details.append({
                    "city": city,
                    "state": state,
                    "status": "skipped",
                    "reason": "duplicate_observation",
                })
            else:
                successful += 1
                details.append({
                    "city": city,
                    "state": state,
                    "status": result.get("status", "success"),
                    "event_type": result.get("event_type") or result.get("classified_event_type"),
                })

        except Exception as exc:
            failed += 1
            sanitized = sanitize_error_message(str(exc))
            logger.warning("Ingestion failed for %s, %s (%s, %s): %s", city, state, lat, lon, sanitized)
            details.append({
                "city": city,
                "state": state,
                "status": "failed",
                "error": sanitized,
            })

    end_time = datetime.now(timezone.utc)
    duration_seconds = (end_time - start_time).total_seconds()

    if failed == 0:
        status_label = "success"
    elif successful > 0 or skipped_duplicates > 0:
        status_label = "partial_failure"
    else:
        status_label = "failed"

    summary = {
        "timestamp": start_time.isoformat(),
        "duration_seconds": round(duration_seconds, 2),
        "total_locations": len(locations),
        "successful": successful,
        "skipped_duplicates": skipped_duplicates,
        "failed": failed,
        "status": status_label,
        "dry_run": dry_run,
        "details": details,
    }

    _last_run_timestamp = start_time.isoformat()
    _last_run_status = status_label
    _last_run_summary = summary

    logger.info(
        "Open-Meteo ingestion finished: %d succeeded, %d skipped duplicates, %d failed in %.2fs.",
        successful,
        skipped_duplicates,
        failed,
        duration_seconds,
    )

    return summary


def start_scheduler() -> bool:
    """
    Initialize and start the background AsyncIOScheduler on the active asyncio event loop.
    Job interval defaults to 30 minutes unless configured via .env.
    """
    global _scheduler

    if not is_ingestion_enabled():
        logger.info("Open-Meteo background ingestion is disabled via OPEN_METEO_INGESTION_ENABLED.")
        return False

    if _scheduler is not None and _scheduler.running:
        logger.info("Open-Meteo ingestion scheduler is already running.")
        return True

    interval_minutes = get_configured_interval_minutes()
    locations = get_configured_locations()

    try:
        _scheduler = AsyncIOScheduler()
        # Add interval job; executes every `interval_minutes` minutes
        _scheduler.add_job(
            run_open_meteo_ingestion_job,
            trigger="interval",
            minutes=interval_minutes,
            id="open_meteo_periodic_ingestion",
            name="Periodic Open-Meteo Real Data Ingestion",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        _scheduler.start()
        logger.info(
            "Open-Meteo background scheduler successfully started. Polling %d locations every %d minutes.",
            len(locations),
            interval_minutes,
        )
        return True
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Failed to start Open-Meteo ingestion scheduler: %s", sanitized)
        return False


def stop_scheduler() -> bool:
    """
    Gracefully shut down the background scheduler.
    """
    global _scheduler

    if _scheduler is not None:
        try:
            if _scheduler.running:
                _scheduler.shutdown(wait=False)
            logger.info("Open-Meteo background scheduler shut down cleanly.")
            _scheduler = None
            return True
        except Exception as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.warning("Error during scheduler shutdown: %s", sanitized)
            _scheduler = None
            return False
    return False


def get_scheduler_status() -> Dict[str, Any]:
    """
    Retrieve operational health and status metadata for the scheduler.
    """
    is_running = _scheduler.running if _scheduler is not None else False
    interval = get_configured_interval_minutes()
    locations = get_configured_locations()
    enabled = is_ingestion_enabled()

    next_run_time: Optional[str] = None
    if _scheduler is not None and is_running:
        job = _scheduler.get_job("open_meteo_periodic_ingestion")
        if job and job.next_run_time:
            next_run_time = job.next_run_time.isoformat()

    return {
        "running": is_running,
        "enabled": enabled,
        "interval_minutes": interval,
        "locations_count": len(locations),
        "locations": [{"city": loc["city"], "state": loc["state"]} for loc in locations],
        "next_run_timestamp": next_run_time,
        "last_run_timestamp": _last_run_timestamp,
        "last_run_status": _last_run_status,
        "last_run_summary": _last_run_summary,
    }
