"""
Automated test suite for Weather Events API (GET /api/events, GET /api/events/{event_id}).

Covers:
- Test 1: GET /api/events returns 200, valid structure, only real baseline records.
- Test 2: Pagination with page=1 & page_size=1, pagination metadata accuracy.
- Test 3: Event type filter matching and non-matching.
- Test 4: Source filter matching and non-matching.
- Test 5: Verification status filter matching and non-matching.
- Test 6: State/city case-insensitive filters.
- Test 7: Time range boundary filters.
- Test 8: Combined multi-attribute filters.
- Test 9: Invalid page/page_size validation (HTTP 422).
- Test 10: start_time > end_time validation (HTTP 400).
- Test 11: GET /api/events/{existing_event_id} returns HTTP 200.
- Test 12: GET /api/events/{nonexistent UUID} returns HTTP 404.
- Test 13: SQL injection-style filter input safely handled, DB unaffected.
- Test 14: Regression: GET /api/health, GET /api/database/health, POST /api/reports.
"""

from datetime import datetime, timezone
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
import httpx
from main import app
from database import get_db_connection


def get_current_record_count() -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM weather_events;")
            return cur.fetchone()[0]


async def run_events_api_tests():
    baseline_count = get_current_record_count()
    print(f"[*] Starting Events API Tests. Baseline record count in Supabase: {baseline_count}")
    assert baseline_count == 2, f"Expected baseline count of 2, found {baseline_count}"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        
        # --- Test 1: GET /api/events base structure ---
        print("\n--- [Test 1] GET /api/events base response ---")
        res1 = await client.get("/api/events")
        assert res1.status_code == 200, f"Failed: {res1.text}"
        body1 = res1.json()
        assert "data" in body1
        assert "pagination" in body1
        pagination1 = body1["pagination"]
        assert pagination1["page"] == 1
        assert pagination1["page_size"] == 50
        assert pagination1["total"] == baseline_count
        assert len(body1["data"]) == baseline_count
        
        first_event = body1["data"][0]
        assert "event_id" in first_event
        assert "event_type" in first_event
        assert "event_timestamp" in first_event
        assert "source" in first_event
        existing_event_id = first_event["event_id"]
        print(f"[OK] Test 1 passed: Returned {len(body1['data'])} real events with complete schema.")

        # --- Test 2: Pagination page=1&page_size=1 ---
        print("\n--- [Test 2] Pagination page=1&page_size=1 ---")
        res2_p1 = await client.get("/api/events?page=1&page_size=1")
        assert res2_p1.status_code == 200
        body2_p1 = res2_p1.json()
        assert len(body2_p1["data"]) == 1
        assert body2_p1["pagination"]["page"] == 1
        assert body2_p1["pagination"]["page_size"] == 1
        assert body2_p1["pagination"]["total"] == baseline_count
        assert body2_p1["pagination"]["total_pages"] == baseline_count
        p1_id = body2_p1["data"][0]["event_id"]

        res2_p2 = await client.get("/api/events?page=2&page_size=1")
        assert res2_p2.status_code == 200
        body2_p2 = res2_p2.json()
        assert len(body2_p2["data"]) == 1
        assert body2_p2["pagination"]["page"] == 2
        p2_id = body2_p2["data"][0]["event_id"]
        assert p1_id != p2_id, "Page 1 and Page 2 must return distinct records"
        print("[OK] Test 2 passed: Accurate pagination metadata and deterministic slicing.")

        # --- Test 3: Event type filter ---
        print("\n--- [Test 3] Event type filter ---")
        res3_match = await client.get("/api/events?event_type=Other")
        assert res3_match.status_code == 200
        body3_match = res3_match.json()
        assert body3_match["pagination"]["total"] == 2
        assert all(e["event_type"] == "Other" for e in body3_match["data"])

        res3_nomatch = await client.get("/api/events?event_type=Heavy%20Rain")
        assert res3_nomatch.status_code == 200
        body3_nomatch = res3_nomatch.json()
        assert body3_nomatch["pagination"]["total"] == 0
        assert len(body3_nomatch["data"]) == 0
        print("[OK] Test 3 passed: Event type filter returns only matching records.")

        # --- Test 4: Source filter ---
        print("\n--- [Test 4] Source filter ---")
        res4_match = await client.get("/api/events?source=Open_Meteo")
        assert res4_match.status_code == 200
        body4_match = res4_match.json()
        assert body4_match["pagination"]["total"] == 2
        assert all(e["source"] == "Open_Meteo" for e in body4_match["data"])

        res4_nomatch = await client.get("/api/events?source=Citizen_Report")
        assert res4_nomatch.status_code == 200
        assert res4_nomatch.json()["pagination"]["total"] == 0
        print("[OK] Test 4 passed: Source filter returns only matching records.")

        # --- Test 5: Verification status filter ---
        print("\n--- [Test 5] Verification status filter ---")
        res5_match = await client.get("/api/events?verification_status=Unverified")
        assert res5_match.status_code == 200
        body5_match = res5_match.json()
        assert body5_match["pagination"]["total"] == 2
        assert all(e["verification_status"] == "Unverified" for e in body5_match["data"])

        res5_nomatch = await client.get("/api/events?verification_status=Verified")
        assert res5_nomatch.status_code == 200
        assert res5_nomatch.json()["pagination"]["total"] == 0
        print("[OK] Test 5 passed: Verification status filter returns only matching records.")

        # --- Test 6: State/City case-insensitive filter ---
        print("\n--- [Test 6] State and city case-insensitive filter ---")
        res6_state = await client.get("/api/events?state=chhattisgarh")
        assert res6_state.status_code == 200
        assert res6_state.json()["pagination"]["total"] == 2

        res6_city = await client.get("/api/events?city=RAIPUR")
        assert res6_city.status_code == 200
        assert res6_city.json()["pagination"]["total"] == 2

        res6_nomatch = await client.get("/api/events?state=Maharashtra")
        assert res6_nomatch.status_code == 200
        assert res6_nomatch.json()["pagination"]["total"] == 0
        print("[OK] Test 6 passed: Case-insensitive location filtering functions correctly.")

        # --- Test 7: Time range boundary filters ---
        print("\n--- [Test 7] Time range boundary filters ---")
        # Real records are at 20:00:00 and 20:30:00 on 2026-10-07
        res7_both = await client.get("/api/events?start_time=2026-10-07T19:00:00Z&end_time=2026-10-07T21:00:00Z")
        assert res7_both.status_code == 200
        assert res7_both.json()["pagination"]["total"] == 2

        res7_one = await client.get("/api/events?start_time=2026-10-07T20:15:00Z&end_time=2026-10-07T21:00:00Z")
        assert res7_one.status_code == 200
        assert res7_one.json()["pagination"]["total"] == 1
        assert "20:30:00" in res7_one.json()["data"][0]["event_timestamp"]

        res7_none = await client.get("/api/events?start_time=2026-10-01T00:00:00Z&end_time=2026-10-06T00:00:00Z")
        assert res7_none.status_code == 200
        assert res7_none.json()["pagination"]["total"] == 0
        print("[OK] Test 7 passed: Time range boundaries correctly filter by observation timestamp.")

        # --- Test 8: Combined filters ---
        print("\n--- [Test 8] Combined multi-attribute filters ---")
        res8_match = await client.get(
            "/api/events?source=Open_Meteo&event_type=Other&state=Chhattisgarh&verification_status=Unverified"
        )
        assert res8_match.status_code == 200
        assert res8_match.json()["pagination"]["total"] == 2

        res8_nomatch = await client.get(
            "/api/events?source=Open_Meteo&event_type=Other&state=Maharashtra"
        )
        assert res8_nomatch.status_code == 200
        assert res8_nomatch.json()["pagination"]["total"] == 0
        print("[OK] Test 8 passed: Combined multi-attribute filters evaluate conjunctively.")

        # --- Test 9: Invalid page/page_size validation ---
        print("\n--- [Test 9] Invalid page/page_size validation ---")
        res9_p0 = await client.get("/api/events?page=0")
        assert res9_p0.status_code == 422, f"Expected 422 for page=0, got {res9_p0.status_code}"

        res9_ps0 = await client.get("/api/events?page_size=0")
        assert res9_ps0.status_code == 422, f"Expected 422 for page_size=0, got {res9_ps0.status_code}"

        res9_ps101 = await client.get("/api/events?page_size=101")
        assert res9_ps101.status_code == 422, f"Expected 422 for page_size=101, got {res9_ps101.status_code}"
        print("[OK] Test 9 passed: Invalid pagination parameters rejected with HTTP 422.")

        # --- Test 10: start_time > end_time validation ---
        print("\n--- [Test 10] start_time > end_time validation ---")
        res10 = await client.get("/api/events?start_time=2026-10-08T12:00:00Z&end_time=2026-10-08T10:00:00Z")
        assert res10.status_code == 400
        assert "start_time cannot be greater than end_time" in res10.json()["detail"]
        print("[OK] Test 10 passed: Inverted time range rejected with HTTP 400.")

        # --- Test 11: GET /api/events/{existing_event_id} ---
        print("\n--- [Test 11] GET /api/events/{existing_event_id} ---")
        res11 = await client.get(f"/api/events/{existing_event_id}")
        assert res11.status_code == 200
        event11 = res11.json()
        assert event11["event_id"] == existing_event_id
        assert event11["source"] == "Open_Meteo"
        assert event11["event_type"] == "Other"
        assert event11["city"] == "Raipur"
        print(f"[OK] Test 11 passed: Successfully retrieved single event {existing_event_id}.")

        # --- Test 12: GET /api/events/{nonexistent UUID} ---
        print("\n--- [Test 12] GET /api/events/{nonexistent UUID} ---")
        res12_uuid = await client.get("/api/events/00000000-0000-0000-0000-000000000000")
        assert res12_uuid.status_code == 404
        assert "not found" in res12_uuid.json()["detail"].lower()

        res12_malformed = await client.get("/api/events/invalid-uuid-format")
        assert res12_malformed.status_code == 404
        assert "not found" in res12_malformed.json()["detail"].lower()
        print("[OK] Test 12 passed: Missing or malformed event IDs return HTTP 404.")

        # --- Test 13: SQL injection-style filter input safety ---
        print("\n--- [Test 13] SQL injection-style filter input safety ---")
        # Categorical injection rejected by validator
        res13_sqli1 = await client.get("/api/events?event_type=' OR '1'='1")
        assert res13_sqli1.status_code == 400

        # Location text injection safely parameterized
        res13_sqli2 = await client.get("/api/events?city=' OR 1=1 --")
        assert res13_sqli2.status_code == 200
        assert res13_sqli2.json()["pagination"]["total"] == 0

        res13_sqli3 = await client.get("/api/events?state='; DROP TABLE weather_events; --")
        assert res13_sqli3.status_code == 200
        assert res13_sqli3.json()["pagination"]["total"] == 0

        # Confirm database is completely intact
        assert get_current_record_count() == baseline_count
        print("[OK] Test 13 passed: SQL injection payloads safely neutralized by parameterized SQL.")

        # --- Test 14: Regression on existing endpoints ---
        print("\n--- [Test 14] Regression on existing endpoints ---")
        res14_health = await client.get("/api/health")
        assert res14_health.status_code == 200
        assert res14_health.json() == {"status": "ok"}

        res14_db = await client.get("/api/database/health")
        assert res14_db.status_code == 200
        assert res14_db.json()["database"] == "connected"

        # Temporary report submission and immediate cleanup
        report_payload = {
            "event_type": "Thunderstorm",
            "description": "TEMPORARY_TEST_REGRESSION: Testing POST /api/reports.",
            "latitude": 21.25,
            "longitude": 81.63,
            "timestamp": "2026-10-08T18:00:00Z",
        }
        res14_report = await client.post("/api/reports", json=report_payload)
        assert res14_report.status_code == 201
        temp_event_id = res14_report.json()["event_id"]

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM weather_events WHERE event_id = %s;", (temp_event_id,))
                conn.commit()

        final_count = get_current_record_count()
        assert final_count == baseline_count, f"Database not clean: expected {baseline_count}, found {final_count}"
        print(f"[OK] Test 14 passed: Existing endpoints operational, database verified at {final_count} records.")

    print("\n==========================================")
    print("ALL 14 EVENTS API TESTS PASSED!")
    print("==========================================")


if __name__ == "__main__":
    asyncio.run(run_events_api_tests())
