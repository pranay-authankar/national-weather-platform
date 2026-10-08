"""
Comprehensive verification test suite for Weather Report Verification and Confidence Scoring.

Tests:
1. Valid isolated citizen report -> Unverified, low/baseline confidence (35.0).
2. Citizen report with independent nearby supporting event -> Likely (score: 60.0).
3. Citizen report with strong independent evidence (official observation + additional source) -> Verified (score: 100.0).
4. Duplicate report -> remains Duplicate, duplicate_of preserved.
5. Insufficient evidence -> does not become Verified.
6. Verification query/database failure simulation -> endpoint still succeeds (201), report stored as Unverified.
7. Database cleanup confirmation -> all temporary records deleted, restoring DB to baseline count (2).
"""

import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
from datetime import datetime, timedelta, timezone
import httpx
import psycopg
from main import app
from database import get_db_connection
import services.verification_service as verif_service
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


async def run_verification_tests():
    baseline_count = get_current_record_count()
    print(f"[*] Starting Verification Tests. Baseline record count in Supabase: {baseline_count}")

    transport = httpx.ASGITransport(app=app)
    created_event_ids = []

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            
            # --- Test 1: Valid isolated citizen report ---
            print("\n--- [Test 1] Valid isolated citizen report -> Unverified, baseline confidence ---")
            payload1 = {
                "event_type": "Heavy Rain",
                "description": "TEMPORARY_TEST_1: Isolated rainfall observation.",
                "latitude": 15.3173,  # Gadag, Karnataka (far from existing records)
                "longitude": 75.7139,
                "timestamp": "2026-10-08T09:00:00Z",
            }
            res1 = await client.post("/api/reports", json=payload1)
            assert res1.status_code == 201, f"Failed: {res1.text}"
            id1 = res1.json()["event_id"]
            created_event_ids.append(id1)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, confidence_score, duplicate_of FROM weather_events WHERE event_id = %s;", (id1,))
                    status1, score1, dup_of1 = cur.fetchone()
                    print(f"Report 1: status={status1}, confidence_score={score1}, duplicate_of={dup_of1}")
                    assert status1 == "Unverified", f"Expected Unverified, got {status1}"
                    assert score1 == 35.0, f"Expected baseline score 35.0 (15+10+10), got {score1}"
                    assert dup_of1 is None
            print("[OK] Test 1 passed: Isolated report remains Unverified with baseline confidence 35.0.")

            # --- Test 2: Citizen report with independent nearby supporting event -> Likely ---
            print("\n--- [Test 2] Citizen report with independent nearby supporting event -> Likely ---")
            # Insert a supporting independent citizen report in Pune
            base_time = datetime(2026, 10, 8, 11, 0, 0, tzinfo=timezone.utc)
            supporting_citizen_data = {
                "source": "Citizen_Report",
                "source_record_id": "test_supp_citizen_001",
                "event_type": "Heavy Rain",
                "description": "Waterlogging on Shivaji Road.",
                "event_timestamp": base_time,
                "latitude": 18.5204,  # Pune Center
                "longitude": 73.8567,
                "location": None,
                "city": "Pune",
                "district": "Pune",
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
                "confidence_score": 35.0,
                "duplicate_of": None,
            }
            inserted_supp = insert_weather_event(supporting_citizen_data)
            supp_id = inserted_supp["event_id"]
            created_event_ids.append(supp_id)
            print(f"[*] Inserted Supporting Citizen Event: {supp_id} in Pune")

            # Submit report ~3.3 km away (outside 2km duplicate cutoff, within 25km verification radius)
            payload2 = {
                "event_type": "Heavy Rain",
                "description": "TEMPORARY_TEST_2: Heavy showers observed in Pune suburbs.",
                "latitude": 18.5450,  # ~3.3 km away
                "longitude": 73.8750,
                "timestamp": "2026-10-08T11:45:00Z",  # 45 mins later
            }
            res2 = await client.post("/api/reports", json=payload2)
            assert res2.status_code == 201, f"Failed: {res2.text}"
            id2 = res2.json()["event_id"]
            created_event_ids.append(id2)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, confidence_score, duplicate_of FROM weather_events WHERE event_id = %s;", (id2,))
                    status2, score2, dup_of2 = cur.fetchone()
                    print(f"Report 2: status={status2}, confidence_score={score2}, duplicate_of={dup_of2}")
                    assert status2 == "Likely", f"Expected Likely, got {status2}"
                    assert score2 == 60.0, f"Expected 60.0 (35 + 25 nearby event), got {score2}"
                    assert dup_of2 is None, f"Expected duplicate_of None, got {dup_of2}"
            print("[OK] Test 2 passed: Confidence increased to 60.0 and status mapped to Likely.")

            # --- Test 3: Citizen report with strong independent evidence -> Verified ---
            print("\n--- [Test 3] Citizen report with strong independent evidence -> Verified ---")
            # Create two independent supporting sources in Ahmedabad:
            # 1. Official Open_Meteo observation
            # 2. Independent citizen report
            ahmedabad_time = datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)
            official_obs_data = {
                "source": "Open_Meteo",
                "source_record_id": "test_official_open_meteo_001",
                "event_type": "Heavy Rain",
                "description": None,
                "event_timestamp": ahmedabad_time,
                "latitude": 23.0225,  # Ahmedabad
                "longitude": 72.5714,
                "location": None,
                "city": "Ahmedabad",
                "district": "Ahmedabad",
                "state": "Gujarat",
                "temperature": 27.5,
                "rainfall": 28.0,
                "humidity": 92.0,
                "wind_speed": 35.0,
                "wind_direction": 180.0,
                "pressure": 1005.0,
                "image_url": None,
                "video_url": None,
                "source_url": None,
                "verification_status": "Verified",
                "confidence_score": 100.0,
                "duplicate_of": None,
            }
            ins_official = insert_weather_event(official_obs_data)
            official_id = ins_official["event_id"]
            created_event_ids.append(official_id)

            citizen_supp_data2 = {
                "source": "Citizen_Report",
                "source_record_id": "test_citizen_supp_002",
                "event_type": "Heavy Rain",
                "description": "Heavy rainfall near riverfront.",
                "event_timestamp": ahmedabad_time + timedelta(minutes=20),
                "latitude": 23.0550,  # ~4 km away
                "longitude": 72.5850,
                "location": None,
                "city": "Ahmedabad",
                "district": "Ahmedabad",
                "state": "Gujarat",
                "temperature": None,
                "rainfall": None,
                "humidity": None,
                "wind_speed": None,
                "wind_direction": None,
                "pressure": None,
                "image_url": None,
                "video_url": None,
                "source_url": None,
                "verification_status": "Likely",
                "confidence_score": 60.0,
                "duplicate_of": None,
            }
            ins_citizen2 = insert_weather_event(citizen_supp_data2)
            citizen2_id = ins_citizen2["event_id"]
            created_event_ids.append(citizen2_id)
            print(f"[*] Inserted Official Obs {official_id} and Citizen Report {citizen2_id} in Ahmedabad")

            # Submit citizen report 2.5 km away from official and 2.6 km away from citizen report
            # (outside 2 km duplicate threshold, within 25 km verification radius)
            payload3 = {
                "event_type": "Heavy Rain",
                "description": "TEMPORARY_TEST_3: Downpour near Ashram Road.",
                "latitude": 23.0400,  # ~2.5 km from official, ~2.2 km from citizen
                "longitude": 72.5650,
                "timestamp": "2026-10-08T14:15:00Z",
            }
            res3 = await client.post("/api/reports", json=payload3)
            assert res3.status_code == 201, f"Failed: {res3.text}"
            id3 = res3.json()["event_id"]
            created_event_ids.append(id3)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, confidence_score, duplicate_of FROM weather_events WHERE event_id = %s;", (id3,))
                    status3, score3, dup_of3 = cur.fetchone()
                    print(f"Report 3: status={status3}, confidence_score={score3}, duplicate_of={dup_of3}")
                    assert status3 == "Verified", f"Expected Verified, got {status3}"
                    assert score3 == 100.0, f"Expected 100.0 (35 + 25 + 25 + 15), got {score3}"
                    assert dup_of3 is None
            print("[OK] Test 3 passed: Strong multi-source confirmation achieves Verified status (100.0).")

            # --- Test 4: Duplicate report -> remains Duplicate ---
            print("\n--- [Test 4] Duplicate report -> remains Duplicate ---")
            # Base event in Nagpur
            nagpur_time = datetime(2026, 10, 8, 16, 0, 0, tzinfo=timezone.utc)
            base_nagpur_data = {
                "source": "Citizen_Report",
                "source_record_id": "test_nagpur_base_001",
                "event_type": "Thunderstorm",
                "description": "Lightning strikes near Sitabuldi.",
                "event_timestamp": nagpur_time,
                "latitude": 21.1458,
                "longitude": 79.0882,
                "location": None,
                "city": "Nagpur",
                "district": "Nagpur",
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
                "confidence_score": 35.0,
                "duplicate_of": None,
            }
            ins_nagpur = insert_weather_event(base_nagpur_data)
            nagpur_base_id = ins_nagpur["event_id"]
            created_event_ids.append(nagpur_base_id)

            # Submit duplicate report 150m away, 10 minutes later
            payload4 = {
                "event_type": "Thunderstorm",
                "description": "Thunder and lightning in Sitabuldi market.",
                "latitude": 21.1465,  # ~100m away
                "longitude": 79.0890,
                "timestamp": "2026-10-08T16:10:00Z",
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
                    assert status4 == "Duplicate", f"Expected Duplicate, got {status4}"
                    assert str(dup_of4) == str(nagpur_base_id), f"Expected duplicate_of {nagpur_base_id}, got {dup_of4}"
            print("[OK] Test 4 passed: Duplicate status and duplicate_of reference preserved.")

            # --- Test 5: Insufficient evidence -> does not become Verified ---
            print("\n--- [Test 5] Insufficient evidence -> does not become Verified ---")
            payload5 = {
                "event_type": "Fog",
                "description": "TEMPORARY_TEST_5: Dense morning fog.",
                "latitude": 27.1767,  # Agra, UP (no other fog records)
                "longitude": 78.0081,
                "timestamp": "2026-10-08T05:30:00Z",
            }
            res5 = await client.post("/api/reports", json=payload5)
            assert res5.status_code == 201
            id5 = res5.json()["event_id"]
            created_event_ids.append(id5)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT verification_status, confidence_score FROM weather_events WHERE event_id = %s;", (id5,))
                    status5, score5 = cur.fetchone()
                    print(f"Report 5: status={status5}, confidence_score={score5}")
                    assert status5 == "Unverified", f"Expected Unverified, got {status5}"
                    assert score5 <= 39.0, f"Expected score <= 39, got {score5}"
            print("[OK] Test 5 passed: Insufficient evidence remains Unverified.")

            # --- Test 6: Verification query/database failure simulation ---
            print("\n--- [Test 6] Verification query/database failure simulation ---")
            original_func = verif_service.find_supporting_events

            def mock_failing_query(*args, **kwargs):
                raise psycopg.OperationalError("Simulated database timeout or network disconnect")

            try:
                verif_service.find_supporting_events = mock_failing_query
                payload6 = {
                    "event_type": "Flooding",
                    "description": "TEMPORARY_TEST_6: Flooding test during simulated verification query error.",
                    "latitude": 22.5726,  # Kolkata
                    "longitude": 88.3639,
                    "timestamp": "2026-10-08T17:00:00Z",
                }
                res6 = await client.post("/api/reports", json=payload6)
                assert res6.status_code == 201, f"Expected 201, got {res6.status_code}: {res6.text}"
                id6 = res6.json()["event_id"]
                created_event_ids.append(id6)

                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT verification_status, confidence_score FROM weather_events WHERE event_id = %s;", (id6,))
                        status6, score6 = cur.fetchone()
                        print(f"Report 6: status={status6}, confidence_score={score6}")
                        assert status6 == "Unverified", f"Expected Unverified, got {status6}"
                        # With database query failure, falls back to local evidence (valid fields = 35.0)
                        assert score6 == 35.0, f"Expected 35.0, got {score6}"
                print("[OK] Test 6 passed: Backend gracefully handles verification query failure.")
            finally:
                verif_service.find_supporting_events = original_func

    finally:
        # --- Cleanup all temporary test records ---
        print(f"\n[*] Cleaning up {len(created_event_ids)} temporary test record(s) from Supabase...")
        delete_records_by_ids(created_event_ids)
        final_count = get_current_record_count()
        print(f"[*] Final record count in Supabase: {final_count} (Baseline: {baseline_count})")
        assert final_count == baseline_count, f"DB integrity error: expected {baseline_count}, found {final_count}"
        print("[OK] Supabase database verified: All test records removed, database restored to real data.")


if __name__ == "__main__":
    asyncio.run(run_verification_tests())
