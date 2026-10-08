"""
Automated test suite for Weather Analytics API (GET /api/analytics/summary).

Covers all milestone requirements:
- Test 1: GET /api/analytics/summary -> HTTP 200, valid response structure.
- Test 2: total_events matches the filtered database result.
- Test 3: verification breakdown is correct.
- Test 4: all 5 verification categories are represented (Verified, Likely, Unverified, Rejected, Duplicate) even with count 0.
- Test 5: events_by_type counts match PostgreSQL.
- Test 6: events_by_source counts match PostgreSQL.
- Test 7: events_by_state counts match PostgreSQL.
- Test 8: events_over_time matches PostgreSQL daily aggregation.
- Test 9: event_type filter works.
- Test 10: source filter works.
- Test 11: verification_status filter works.
- Test 12: state/city filter works.
- Test 13: time range filter works.
- Test 14: combined filters work.
- Test 15: start_time > end_time returns HTTP 400.
- Test 16: SQL injection-style input is safely parameterized.
- Test 17: empty result returns valid zero-count analytics rather than crashing.
- Test 18: existing APIs regression (GET /api/events, GET /api/events/map, GET /api/health, GET /api/database/health, POST /api/reports).
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


async def run_analytics_api_tests():
    baseline_count = get_current_record_count()
    print(f"[*] Starting Analytics API Tests. Baseline record count in Supabase: {baseline_count}")
    assert baseline_count == 2, f"Expected baseline count of 2, found {baseline_count}"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        # --- Test 1: GET /api/analytics/summary base structure ---
        print("\n--- [Test 1] GET /api/analytics/summary base response ---")
        res1 = await client.get("/api/analytics/summary")
        assert res1.status_code == 200, f"Failed: {res1.text}"
        body1 = res1.json()

        expected_keys = {
            "total_events",
            "verified_events",
            "likely_events",
            "unverified_events",
            "rejected_events",
            "duplicate_events",
            "verification_breakdown",
            "events_by_type",
            "events_by_source",
            "events_by_state",
            "events_over_time",
        }
        for k in expected_keys:
            assert k in body1, f"Missing key '{k}' in analytics response"
        print("[OK] Test 1 passed: Valid analytics response structure returned.")

        # --- Test 2: total_events matches database ---
        print("\n--- [Test 2] total_events match ---")
        assert body1["total_events"] == baseline_count == 2
        print(f"[OK] Test 2 passed: total_events ({body1['total_events']}) matches real database count.")

        # --- Test 3: verification breakdown is correct ---
        print("\n--- [Test 3] verification breakdown counts ---")
        assert body1["unverified_events"] == 2
        assert body1["verified_events"] == 0
        assert body1["likely_events"] == 0
        assert body1["rejected_events"] == 0
        assert body1["duplicate_events"] == 0
        print("[OK] Test 3 passed: Verification distribution matches database records.")

        # --- Test 4: All 5 verification categories represented ---
        print("\n--- [Test 4] All five verification categories present ---")
        breakdown = body1["verification_breakdown"]
        assert len(breakdown) == 5, f"Expected 5 categories, got {len(breakdown)}"
        status_map = {item["status"]: item["count"] for item in breakdown}
        for expected_status in ["Verified", "Likely", "Unverified", "Rejected", "Duplicate"]:
            assert expected_status in status_map, f"Missing category: {expected_status}"
        assert status_map["Unverified"] == 2
        assert status_map["Verified"] == 0
        assert status_map["Likely"] == 0
        assert status_map["Rejected"] == 0
        assert status_map["Duplicate"] == 0
        print("[OK] Test 4 passed: All 5 verification categories represented with zero-counts preserved.")

        # --- Test 5: events_by_type counts match PostgreSQL ---
        print("\n--- [Test 5] events_by_type counts ---")
        types = body1["events_by_type"]
        assert len(types) == 1
        assert types[0]["event_type"] == "Other"
        assert types[0]["count"] == 2
        print("[OK] Test 5 passed: events_by_type accurately calculated by PostgreSQL.")

        # --- Test 6: events_by_source counts match PostgreSQL ---
        print("\n--- [Test 6] events_by_source counts ---")
        sources = body1["events_by_source"]
        assert len(sources) == 1
        assert sources[0]["source"] == "Open_Meteo"
        assert sources[0]["count"] == 2
        print("[OK] Test 6 passed: events_by_source accurately calculated by PostgreSQL.")

        # --- Test 7: events_by_state counts match PostgreSQL ---
        print("\n--- [Test 7] events_by_state counts ---")
        states = body1["events_by_state"]
        assert len(states) == 1
        assert states[0]["state"] == "Chhattisgarh"
        assert states[0]["count"] == 2
        print("[OK] Test 7 passed: events_by_state accurately calculated by PostgreSQL.")

        # --- Test 8: events_over_time matches daily aggregation ---
        print("\n--- [Test 8] events_over_time daily aggregation ---")
        daily = body1["events_over_time"]
        assert len(daily) == 1
        assert daily[0]["date"] == "2026-10-07"
        assert daily[0]["count"] == 2
        print("[OK] Test 8 passed: events_over_time accurately reflects daily aggregation.")

        # --- Test 9: event_type filter ---
        print("\n--- [Test 9] event_type filter ---")
        res9_match = await client.get("/api/analytics/summary?event_type=Other")
        assert res9_match.status_code == 200
        assert res9_match.json()["total_events"] == 2

        res9_nomatch = await client.get("/api/analytics/summary?event_type=Cyclone")
        assert res9_nomatch.status_code == 200
        assert res9_nomatch.json()["total_events"] == 0
        assert res9_nomatch.json()["events_by_type"] == []

        res9_invalid = await client.get("/api/analytics/summary?event_type=InvalidType")
        assert res9_invalid.status_code == 400
        print("[OK] Test 9 passed: event_type filter works correctly.")

        # --- Test 10: source filter ---
        print("\n--- [Test 10] source filter ---")
        res10_match = await client.get("/api/analytics/summary?source=Open_Meteo")
        assert res10_match.status_code == 200
        assert res10_match.json()["total_events"] == 2

        res10_nomatch = await client.get("/api/analytics/summary?source=Citizen_Report")
        assert res10_nomatch.status_code == 200
        assert res10_nomatch.json()["total_events"] == 0

        res10_invalid = await client.get("/api/analytics/summary?source=InvalidSource")
        assert res10_invalid.status_code == 400
        print("[OK] Test 10 passed: source filter works correctly.")

        # --- Test 11: verification_status filter ---
        print("\n--- [Test 11] verification_status filter ---")
        res11_match = await client.get("/api/analytics/summary?verification_status=Unverified")
        assert res11_match.status_code == 200
        assert res11_match.json()["total_events"] == 2
        assert res11_match.json()["unverified_events"] == 2

        res11_nomatch = await client.get("/api/analytics/summary?verification_status=Verified")
        assert res11_nomatch.status_code == 200
        assert res11_nomatch.json()["total_events"] == 0
        assert res11_nomatch.json()["verified_events"] == 0

        res11_invalid = await client.get("/api/analytics/summary?verification_status=InvalidStatus")
        assert res11_invalid.status_code == 400
        print("[OK] Test 11 passed: verification_status filter works correctly.")

        # --- Test 12: state and city filter ---
        print("\n--- [Test 12] state and city filter ---")
        res12_state = await client.get("/api/analytics/summary?state=chhattisgarh")
        assert res12_state.status_code == 200
        assert res12_state.json()["total_events"] == 2

        res12_city = await client.get("/api/analytics/summary?city=raipur")
        assert res12_city.status_code == 200
        assert res12_city.json()["total_events"] == 2

        res12_nomatch = await client.get("/api/analytics/summary?city=Mumbai")
        assert res12_nomatch.status_code == 200
        assert res12_nomatch.json()["total_events"] == 0
        print("[OK] Test 12 passed: Case-insensitive state and city filters work correctly.")

        # --- Test 13: Time range filter ---
        print("\n--- [Test 13] time range filter ---")
        res13_partial = await client.get("/api/analytics/summary?start_time=2026-10-07T20:15:00Z")
        assert res13_partial.status_code == 200
        assert res13_partial.json()["total_events"] == 1
        assert res13_partial.json()["events_over_time"][0]["count"] == 1

        res13_both = await client.get("/api/analytics/summary?start_time=2026-10-07T19:00:00Z&end_time=2026-10-07T21:00:00Z")
        assert res13_both.status_code == 200
        assert res13_both.json()["total_events"] == 2

        res13_out = await client.get("/api/analytics/summary?start_time=2026-10-01T00:00:00Z&end_time=2026-10-02T00:00:00Z")
        assert res13_out.status_code == 200
        assert res13_out.json()["total_events"] == 0
        print("[OK] Test 13 passed: Time range filters function properly.")

        # --- Test 14: Combined filters ---
        print("\n--- [Test 14] combined filters ---")
        res14 = await client.get(
            "/api/analytics/summary?event_type=Other&source=Open_Meteo&state=chhattisgarh&city=raipur"
        )
        assert res14.status_code == 200
        assert res14.json()["total_events"] == 2

        res14_conflict = await client.get(
            "/api/analytics/summary?event_type=Other&state=Maharashtra"
        )
        assert res14_conflict.status_code == 200
        assert res14_conflict.json()["total_events"] == 0
        print("[OK] Test 14 passed: Combined filters evaluate conjunctively.")

        # --- Test 15: start_time > end_time returns HTTP 400 ---
        print("\n--- [Test 15] start_time > end_time validation ---")
        res15 = await client.get(
            "/api/analytics/summary?start_time=2026-10-08T00:00:00Z&end_time=2026-10-07T00:00:00Z"
        )
        assert res15.status_code == 400
        print("[OK] Test 15 passed: Inverted time range rejected with HTTP 400.")

        # --- Test 16: SQL injection safety ---
        print("\n--- [Test 16] SQL injection safety ---")
        injection_queries = [
            "/api/analytics/summary?city=%27%20OR%20%271%27=%271",
            "/api/analytics/summary?state=%27;%20DROP%20TABLE%20weather_events;%20--",
            "/api/analytics/summary?district=%22%20UNION%20SELECT%20*%20FROM%20weather_events%20--",
        ]
        for q in injection_queries:
            inj_res = await client.get(q)
            assert inj_res.status_code == 200
            assert inj_res.json()["total_events"] == 0
        assert get_current_record_count() == baseline_count == 2
        print("[OK] Test 16 passed: SQL injection attempts neutralized, database intact.")

        # --- Test 17: Empty result returns valid zero-count analytics ---
        print("\n--- [Test 17] Empty result zero-count analytics ---")
        res17 = await client.get("/api/analytics/summary?event_type=Flooding")
        assert res17.status_code == 200
        body17 = res17.json()
        assert body17["total_events"] == 0
        assert body17["verified_events"] == 0
        assert body17["likely_events"] == 0
        assert body17["unverified_events"] == 0
        assert body17["rejected_events"] == 0
        assert body17["duplicate_events"] == 0
        assert body17["events_by_type"] == []
        assert body17["events_by_source"] == []
        assert body17["events_by_state"] == []
        assert body17["events_over_time"] == []
        assert len(body17["verification_breakdown"]) == 5
        for item in body17["verification_breakdown"]:
            assert item["count"] == 0
        print("[OK] Test 17 passed: Empty result returns valid zero-count analytics without errors.")

        # --- Test 18: Existing APIs regression ---
        print("\n--- [Test 18] Existing APIs regression ---")
        res18_events = await client.get("/api/events")
        assert res18_events.status_code == 200
        assert res18_events.json()["pagination"]["total"] == 2

        res18_map = await client.get("/api/events/map")
        assert res18_map.status_code == 200
        assert res18_map.json()["count"] == 2

        res18_health = await client.get("/api/health")
        assert res18_health.status_code == 200
        assert res18_health.json() == {"status": "ok"}

        res18_db_health = await client.get("/api/database/health")
        assert res18_db_health.status_code == 200
        assert res18_db_health.json()["status"] == "ok"
        assert res18_db_health.json()["database"] == "connected"

        # POST /api/reports temporary test
        report_payload = {
            "event_type": "Thunderstorm",
            "description": "TEMPORARY_TEST_REGRESSION: Testing POST /api/reports.",
            "latitude": 21.25,
            "longitude": 81.63,
            "timestamp": "2026-10-08T18:00:00Z",
        }
        res18_report = await client.post("/api/reports", json=report_payload)
        assert res18_report.status_code == 201
        temp_event_id = res18_report.json()["event_id"]

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM weather_events WHERE event_id = %s;", (temp_event_id,))
                conn.commit()

        final_count = get_current_record_count()
        assert final_count == baseline_count == 2
        print(f"[OK] Test 18 passed: All existing APIs operational, database verified at {final_count} records.")

    print("\n==========================================")
    print("ALL 18 ANALYTICS API TESTS PASSED!")
    print("==========================================")


if __name__ == "__main__":
    asyncio.run(run_analytics_api_tests())
