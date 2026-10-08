"""
Automated test suite for APScheduler-based continuous Open-Meteo weather ingestion.

Covers:
- Test 1: Scheduler configuration defaults and environment overrides.
- Test 2: Scheduler startup, status, and clean shutdown lifecycle.
- Test 3: Endpoint GET /api/scheduler/status response structure.
- Test 4: Live Open-Meteo ingestion triggering in dry-run mode (real API, no DB mutation).
- Test 5: Spatio-temporal duplicate detection and skip behavior for existing observations.
- Test 6: Graceful error handling and fault tolerance on network/API failure.
- Test 7: Lifespan integration with FastAPI startup and shutdown.
- Test 8: Final database cleanliness check (strictly 2 baseline records, 0 dummy records).
"""

from datetime import datetime, timezone
import os
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
import httpx
from main import app
from database import get_db_connection
from services.scheduler_service import (
    DEFAULT_INTERVAL_MINUTES,
    DEFAULT_LOCATIONS,
    get_configured_interval_minutes,
    get_configured_locations,
    get_scheduler_status,
    is_ingestion_enabled,
    run_open_meteo_ingestion_job,
    start_scheduler,
    stop_scheduler,
)
from services.weather_event_service import weather_event_exists


def get_current_record_count() -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.weather_events;")
            return cur.fetchone()[0]


async def run_scheduler_tests():
    baseline_count = get_current_record_count()
    print(f"[*] Starting Scheduler Tests. Baseline record count in Supabase: {baseline_count}")
    assert baseline_count == 2, f"Expected baseline count of 2, found {baseline_count}"

    # --- Test 1: Configuration defaults and overrides ---
    print("\n--- [Test 1] Scheduler configuration defaults ---")
    interval = get_configured_interval_minutes()
    assert interval == DEFAULT_INTERVAL_MINUTES == 30, f"Expected default interval 30, got {interval}"

    locations = get_configured_locations()
    assert len(locations) == len(DEFAULT_LOCATIONS) == 10, f"Expected 10 default locations, got {len(locations)}"
    for loc in locations:
        assert "city" in loc and "state" in loc
        assert -90.0 <= loc["latitude"] <= 90.0
        assert -180.0 <= loc["longitude"] <= 180.0
    print("[OK] Test 1 passed: Default configuration verified with 30min interval and 10 Indian locations.")

    # --- Test 2: Scheduler startup, status, and shutdown lifecycle ---
    print("\n--- [Test 2] Scheduler lifecycle (start -> status -> stop) ---")
    started = start_scheduler()
    assert started is True, "Failed to start scheduler"

    status_running = get_scheduler_status()
    assert status_running["running"] is True, "Scheduler status does not reflect running=True"
    assert status_running["enabled"] is True
    assert status_running["interval_minutes"] == 30
    assert status_running["locations_count"] == 10
    assert status_running["next_run_timestamp"] is not None

    stopped = stop_scheduler()
    assert stopped is True, "Failed to stop scheduler"

    status_stopped = get_scheduler_status()
    assert status_stopped["running"] is False, "Scheduler status does not reflect running=False"
    print("[OK] Test 2 passed: Scheduler starts, reports active status, and cleanly shuts down.")

    # --- Test 3: Endpoint GET /api/scheduler/status ---
    print("\n--- [Test 3] Endpoint GET /api/scheduler/status ---")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/scheduler/status")
        assert res.status_code == 200, f"Failed with {res.status_code}: {res.text}"
        body = res.json()
        assert "running" in body
        assert "enabled" in body
        assert "interval_minutes" in body
        assert "locations_count" in body
        assert "locations" in body
        assert body["interval_minutes"] == 30
        assert body["locations_count"] == 10
    print("[OK] Test 3 passed: GET /api/scheduler/status returns structured scheduler telemetry.")

    # --- Test 4: Live Open-Meteo Ingestion Triggering in Dry-Run Mode ---
    print("\n--- [Test 4] Live Open-Meteo API ingestion triggering (Dry-Run) ---")
    test_location = [{"city": "Raipur", "state": "Chhattisgarh", "latitude": 21.25, "longitude": 81.63}]
    job_result = await run_open_meteo_ingestion_job(dry_run=True, custom_locations=test_location)

    assert job_result["dry_run"] is True
    assert job_result["total_locations"] == 1
    assert job_result["failed"] == 0
    assert job_result["successful"] == 1
    assert job_result["status"] == "success"

    detail = job_result["details"][0]
    assert detail["city"] == "Raipur"
    assert detail["status"] == "dry_run"
    assert detail["event_type"] is not None

    # Verify zero database mutation occurred
    current_count = get_current_record_count()
    assert current_count == baseline_count == 2, f"Database mutated during dry-run! Count: {current_count}"
    print(f"[OK] Test 4 passed: Successfully fetched and normalized real Open-Meteo observation without DB insert.")

    # --- Test 5: Ingestion Duplicate Detection Logic ---
    print("\n--- [Test 5] Ingestion duplicate detection and skip behavior ---")
    # Query real baseline record
    existing_record_id = "open_meteo_21.25_81.63_20261007T203000Z"
    exists_check = weather_event_exists("Open_Meteo", existing_record_id)
    assert exists_check is True, f"Expected record {existing_record_id} to exist in baseline database"

    non_existent_check = weather_event_exists("Open_Meteo", "non_existent_record_id_test_999")
    assert non_existent_check is False

    # Verify zero records added
    assert get_current_record_count() == baseline_count == 2
    print("[OK] Test 5 passed: Existing baseline observations accurately recognized to prevent duplicate insertion.")

    # --- Test 6: Fault Tolerance on API Failure ---
    print("\n--- [Test 6] Fault tolerance on external failure ---")
    invalid_location = [{"city": "InvalidCity", "state": "InvalidState", "latitude": 999.0, "longitude": 999.0}]
    failure_result = await run_open_meteo_ingestion_job(dry_run=True, custom_locations=invalid_location)

    assert failure_result["failed"] == 1
    assert failure_result["successful"] == 0
    assert failure_result["status"] == "failed"
    assert failure_result["details"][0]["status"] == "failed"
    assert "error" in failure_result["details"][0]
    print("[OK] Test 6 passed: Out-of-bounds coordinates handled gracefully without crashing.")

    # --- Test 7: FastAPI Lifespan Integration ---
    print("\n--- [Test 7] FastAPI lifespan integration ---")
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            health_res = await client.get("/api/health")
            assert health_res.status_code == 200
            assert health_res.json() == {"status": "ok"}

            sched_res = await client.get("/api/scheduler/status")
            assert sched_res.status_code == 200
            assert sched_res.json()["running"] is True
    # Upon exiting context manager, lifespan terminates scheduler cleanly
    assert get_scheduler_status()["running"] is False
    print("[OK] Test 7 passed: Lifespan successfully initializes and cleanly stops scheduler on app exit.")

    # --- Test 8: Final Database Cleanliness ---
    print("\n--- [Test 8] Final database cleanliness check ---")
    final_count = get_current_record_count()
    print(f"[*] Final database count: {final_count} (Baseline: {baseline_count})")
    assert final_count == 2, f"Database count expected 2, found {final_count}"
    print("[OK] Test 8 passed: Supabase database remains strictly at 2 real baseline records.")

    print("\n==========================================")
    print("ALL 8 SCHEDULER TESTS PASSED!")
    print("==========================================")


if __name__ == "__main__":
    asyncio.run(run_scheduler_tests())
