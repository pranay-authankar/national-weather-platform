"""
Comprehensive tests for Citizen Weather Report Duplicate Detection.

Tests:
1. No matching nearby event -> stored as Unverified, duplicate_of is None.
2. Strong nearby, within time window, same event type -> marked as Duplicate, duplicate_of set to original event_id.
3. Far away (> 2km) -> not duplicate, stored as Unverified.
4. Outside time window (> 2h) -> not duplicate, stored as Unverified.
5. Incompatible event type (Heatwave vs Heavy Rain) -> not duplicate.
6. Database / query error simulation -> endpoint does not crash, stores as Unverified.
7. Database cleanup confirmation -> all temporary records deleted, restoring DB to baseline.
"""

import sys
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
from datetime import datetime, timedelta, timezone
import httpx
import psycopg
from main import app
from database import get_db_connection
import services.duplicate_detection_service as dup_service
from services.weather_event_service import insert_weather_event


def get_current_record_count() -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM weather_events;")
            return cur.fetchone()[0]


def delete_records_by_ids(event_ids: list):
    if not event_ids:
        return
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM weather_events WHERE event_id = ANY(%s::uuid[]);", (event_ids,))
            conn.commit()


async def run_duplicate_detection_tests():
    baseline_count = get_current_record_count()
    print(f"[*] Starting Duplicate Detection Tests. Baseline record count in Supabase: {baseline_count}")

    transport = httpx.ASGITransport(app=app)
    created_event_ids = []

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            
            # --- Test 1: Report with no matching nearby event ---
            print("\n--- [Test 1] Report with no matching nearby event ---")
            payload1 = {
                "event_type": "Heavy Rain",
                "description": "TEMPORARY_TEST_1: Isolated shower in a new area.",
                "latitude": 12.9716,  # Bengaluru
                "longitude": 77.5946,
                "timestamp": "2026-10-08T10:00:00Z",
            }
            res1 = await client.post("/api/reports", json=payload1)
            assert res1.status_code == 201, f"Failed: {res1.text}"
            id1 = res1.json()["event_id"]
            created_event_ids.append(id1)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, duplicate_of FROM weather_events WHERE event_id = %s;", (id1,))
                    status1, dup_of1 = cur.fetchone()
                    print(f"Report 1: status={status1}, duplicate_of={dup_of1}")
                    assert status1 == "Unverified", f"Expected Unverified, got {status1}"
                    assert dup_of1 is None, f"Expected duplicate_of to be None, got {dup_of1}"
            print("[OK] Test 1 passed: New isolated report stored as Unverified.")

            # --- Setup base event in Mumbai for Tests 2, 3, 4 ---
            base_time = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
            base_event_data = {
                "source": "Citizen_Report",
                "source_record_id": "test_base_original_001",
                "event_type": "Heavy Rain",
                "description": "Waterlogging up to 2 feet on S.V. Road near Bandra station.",
                "event_timestamp": base_time,
                "latitude": 19.0550,
                "longitude": 72.8400,
                "location": None,
                "city": "Mumbai",
                "district": "Mumbai Suburban District",
                "state": "Maharashtra",
                "temperature": None,
                "rainfall": None,
                "humidity": None,
                "wind_speed": None,
                "wind_direction": None,
                "pressure": None,
                "image_url": None,
                "video_url": None,
                "source_url": None,
                "verification_status": "Unverified",
                "confidence_score": None,
                "duplicate_of": None,
            }
            inserted_base = insert_weather_event(base_event_data)
            base_id = inserted_base["event_id"]
            created_event_ids.append(base_id)
            print(f"\n[*] Created Base Original Event: {base_id} at (19.0550, 72.8400) at {base_time.isoformat()}")

            # --- Test 2: Strong nearby/time/type match -> Duplicate ---
            print("\n--- [Test 2] Strong nearby, within time window, same event type ---")
            # 250m away, 15 minutes later, same event type "Heavy Rain", similar description
            payload2 = {
                "event_type": "Heavy Rain",
                "description": "Waterlogging 2 feet near Bandra station road.",
                "latitude": 19.0570,  # ~240 meters north
                "longitude": 72.8405,
                "timestamp": "2026-10-08T12:15:00Z",  # 15 mins later
            }
            res2 = await client.post("/api/reports", json=payload2)
            assert res2.status_code == 201, f"Failed: {res2.text}"
            id2 = res2.json()["event_id"]
            created_event_ids.append(id2)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, duplicate_of, confidence_score FROM weather_events WHERE event_id = %s;", (id2,))
                    status2, dup_of2, conf2 = cur.fetchone()
                    print(f"Report 2: status={status2}, duplicate_of={dup_of2}, confidence={conf2}")
                    assert status2 == "Duplicate", f"Expected Duplicate, got {status2}"
                    assert str(dup_of2) == str(base_id), f"Expected duplicate_of {base_id}, got {dup_of2}"
                    assert conf2 is not None and conf2 >= 65.0, f"Expected confidence >= 65.0, got {conf2}"

                    # Verify base original record was NOT modified
                    cur.execute("SELECT verification_status, duplicate_of FROM weather_events WHERE event_id = %s;", (base_id,))
                    base_status, base_dup_of = cur.fetchone()
                    assert base_status == "Unverified", f"Original was modified: {base_status}"
                    assert base_dup_of is None, f"Original duplicate_of was modified: {base_dup_of}"

            print("[OK] Test 2 passed: Duplicate detected, duplicate_of set to original, original untouched.")

            # --- Test 3: Far away (> 2 km) -> Not duplicate ---
            print("\n--- [Test 3] Far away (> 2km) -> Not duplicate ---")
            # ~8.5 km away in Mumbai suburbs, same time window and type
            payload3 = {
                "event_type": "Heavy Rain",
                "description": "Heavy rainfall in Kurla area.",
                "latitude": 19.0760,  # Kurla: ~8 km away
                "longitude": 72.8777,
                "timestamp": "2026-10-08T12:10:00Z",
            }
            res3 = await client.post("/api/reports", json=payload3)
            assert res3.status_code == 201, f"Failed: {res3.text}"
            id3 = res3.json()["event_id"]
            created_event_ids.append(id3)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, duplicate_of FROM weather_events WHERE event_id = %s;", (id3,))
                    status3, dup_of3 = cur.fetchone()
                    print(f"Report 3: status={status3}, duplicate_of={dup_of3}")
                    assert status3 != "Duplicate", f"Expected not Duplicate, got {status3}"
                    assert dup_of3 is None, f"Expected duplicate_of to be None, got {dup_of3}"
            print("[OK] Test 3 passed: Report far away (>2km) is NOT duplicate.")

            # --- Test 4: Outside time window (> 2 hours) -> Not duplicate ---
            print("\n--- [Test 4] Outside time window (> 2 hours) -> Not duplicate ---")
            # Same location (19.0550, 72.8400), but 3.5 hours later
            payload4 = {
                "event_type": "Heavy Rain",
                "description": "Waterlogging observed near Bandra station.",
                "latitude": 19.0552,
                "longitude": 72.8401,
                "timestamp": "2026-10-08T15:30:00Z",  # 3.5 hours later
            }
            res4 = await client.post("/api/reports", json=payload4)
            assert res4.status_code == 201, f"Failed: {res4.text}"
            id4 = res4.json()["event_id"]
            created_event_ids.append(id4)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, duplicate_of FROM weather_events WHERE event_id = %s;", (id4,))
                    status4, dup_of4 = cur.fetchone()
                    print(f"Report 4: status={status4}, duplicate_of={dup_of4}")
                    assert status4 != "Duplicate", f"Expected not Duplicate, got {status4}"
                    assert dup_of4 is None, f"Expected duplicate_of to be None, got {dup_of4}"
            print("[OK] Test 4 passed: Report outside time window is NOT duplicate.")

            # --- Test 5: Incompatible event type (Heatwave vs Heavy Rain) -> Not duplicate ---
            print("\n--- [Test 5] Incompatible event type -> Not duplicate ---")
            payload5 = {
                "event_type": "Heatwave",
                "description": "Extreme scorching heat recorded.",
                "latitude": 19.0552,
                "longitude": 72.8401,
                "timestamp": "2026-10-08T12:05:00Z",  # 5 mins later at same spot
            }
            res5 = await client.post("/api/reports", json=payload5)
            assert res5.status_code == 201, f"Failed: {res5.text}"
            id5 = res5.json()["event_id"]
            created_event_ids.append(id5)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, duplicate_of FROM weather_events WHERE event_id = %s;", (id5,))
                    status5, dup_of5 = cur.fetchone()
                    print(f"Report 5: status={status5}, duplicate_of={dup_of5}")
                    assert status5 == "Unverified", f"Expected Unverified, got {status5}"
                    assert dup_of5 is None, f"Expected duplicate_of to be None, got {dup_of5}"
            print("[OK] Test 5 passed: Incompatible event types are NOT marked as duplicate.")

            # --- Test 6: Database / Query failure resilience ---
            print("\n--- [Test 6] Database / query failure simulation -> Stored as Unverified without crashing ---")
            
            # Monkeypatch find_spatial_temporal_candidates to simulate query failure
            original_func = dup_service.find_spatial_temporal_candidates
            def mock_failing_query(*args, **kwargs):
                raise psycopg.OperationalError("Simulated database timeout or network disconnect")

            try:
                dup_service.find_spatial_temporal_candidates = mock_failing_query
                payload6 = {
                    "event_type": "Thunderstorm",
                    "description": "TEMPORARY_TEST_6: Thunder and lightning during simulated query failure.",
                    "latitude": 28.6139,
                    "longitude": 77.2090,
                    "timestamp": "2026-10-08T13:00:00Z",
                }
                res6 = await client.post("/api/reports", json=payload6)
                assert res6.status_code == 201, f"Failed: {res6.text}"
                id6 = res6.json()["event_id"]
                created_event_ids.append(id6)

                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT verification_status, duplicate_of FROM weather_events WHERE event_id = %s;", (id6,))
                        status6, dup_of6 = cur.fetchone()
                        print(f"Report 6: status={status6}, duplicate_of={dup_of6}")
                        assert status6 == "Unverified", f"Expected Unverified on query failure, got {status6}"
                        assert dup_of6 is None, f"Expected duplicate_of None on query failure, got {dup_of6}"
                print("[OK] Test 6 passed: Backend gracefully handles duplicate-detection query failure.")
            finally:
                dup_service.find_spatial_temporal_candidates = original_func

    finally:
        # --- Cleanup all temporary test records ---
        print(f"\n[*] Cleaning up {len(created_event_ids)} temporary test record(s) from Supabase...")
        delete_records_by_ids(created_event_ids)
        final_count = get_current_record_count()
        print(f"[*] Final record count in Supabase: {final_count} (Baseline: {baseline_count})")
        assert final_count == baseline_count, f"DB integrity error: expected {baseline_count}, found {final_count}"
        print("[OK] Supabase database verified: All test records removed, database restored to real data.")


if __name__ == "__main__":
    asyncio.run(run_duplicate_detection_tests())
