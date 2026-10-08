"""
Automated test suite for Weather Events Map API (GET /api/events/map).

Covers all milestone requirements:
- Test 1: GET /api/events/map -> HTTP 200, valid response structure.
- Test 2: Only events with valid coordinates are returned.
- Test 3: Event type filter.
- Test 4: Source filter.
- Test 5: Verification status filter.
- Test 6: State/city filter.
- Test 7: Time range filter.
- Test 8: India bounding-box filter.
- Test 9: Custom bounding-box filter.
- Test 10: Limit validation.
- Test 11: Combined filters.
- Test 12: Empty result -> HTTP 200 with data=[] and count=0.
- Test 13: SQL injection-style filter input is safely parameterized.
- Test 14: Existing events API still works (GET /api/events, GET /api/events/{id}).
- Test 15: Health/database health endpoints still work.
"""

from datetime import datetime, timezone
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
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


async def run_map_api_tests():
    baseline_count = get_current_record_count()
    print(f"[*] Starting Map API Tests. Baseline record count in Supabase: {baseline_count}")
    assert baseline_count == 2, f"Expected baseline count of 2, found {baseline_count}"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        # --- Test 1: GET /api/events/map base structure ---
        print("\n--- [Test 1] GET /api/events/map base response ---")
        res1 = await client.get("/api/events/map")
        assert res1.status_code == 200, f"Failed: {res1.text}"
        body1 = res1.json()
        assert "data" in body1, "Response missing 'data' field"
        assert "count" in body1, "Response missing 'count' field"
        assert isinstance(body1["data"], list), "'data' must be a list"
        assert isinstance(body1["count"], int), "'count' must be an integer"
        assert body1["count"] == len(body1["data"]) == 2, f"Expected 2 real baseline records, got {body1['count']}"

        # Validate MapEvent fields
        first = body1["data"][0]
        required_keys = {
            "event_id",
            "latitude",
            "longitude",
            "event_type",
            "source",
            "event_timestamp",
            "city",
            "district",
            "state",
            "verification_status",
            "confidence_score",
        }
        for key in required_keys:
            assert key in first, f"Missing key '{key}' in map marker record"

        # Verify excluded heavy fields
        forbidden_keys = {"description", "image_url", "video_url", "pressure", "created_at"}
        for fkey in forbidden_keys:
            assert fkey not in first, f"Unexpected heavy field '{fkey}' found in map response"
        print("[OK] Test 1 passed: Valid lightweight map response structure with 2 real events.")

        # --- Test 2: Only events with valid coordinates are returned ---
        print("\n--- [Test 2] Coordinate validity ---")
        for ev in body1["data"]:
            lat = ev["latitude"]
            lon = ev["longitude"]
            assert lat is not None and isinstance(lat, (int, float)), f"Invalid latitude: {lat}"
            assert lon is not None and isinstance(lon, (int, float)), f"Invalid longitude: {lon}"
            assert -90.0 <= lat <= 90.0, f"Latitude out of bounds: {lat}"
            assert -180.0 <= lon <= 180.0, f"Longitude out of bounds: {lon}"
        print("[OK] Test 2 passed: All returned events have strictly valid geographic coordinates.")

        # --- Test 3: Event type filter ---
        print("\n--- [Test 3] Event type filter ---")
        res3_match = await client.get("/api/events/map?event_type=Other")
        assert res3_match.status_code == 200
        body3_match = res3_match.json()
        assert body3_match["count"] == 2
        for ev in body3_match["data"]:
            assert ev["event_type"] == "Other"

        res3_nomatch = await client.get("/api/events/map?event_type=Cyclone")
        assert res3_nomatch.status_code == 200
        assert res3_nomatch.json()["count"] == 0
        assert res3_nomatch.json()["data"] == []

        res3_invalid = await client.get("/api/events/map?event_type=Apocalypse")
        assert res3_invalid.status_code == 400
        print("[OK] Test 3 passed: Event type filter accurately matched and rejected invalid types.")

        # --- Test 4: Source filter ---
        print("\n--- [Test 4] Source filter ---")
        res4_match = await client.get("/api/events/map?source=Open_Meteo")
        assert res4_match.status_code == 200
        body4_match = res4_match.json()
        assert body4_match["count"] == 2
        for ev in body4_match["data"]:
            assert ev["source"] == "Open_Meteo"

        res4_nomatch = await client.get("/api/events/map?source=Citizen_Report")
        assert res4_nomatch.status_code == 200
        assert res4_nomatch.json()["count"] == 0

        res4_invalid = await client.get("/api/events/map?source=Twitter")
        assert res4_invalid.status_code == 400
        print("[OK] Test 4 passed: Source filter matches valid sources and rejects unknown sources.")

        # --- Test 5: Verification status filter ---
        print("\n--- [Test 5] Verification status filter ---")
        res5_match = await client.get("/api/events/map?verification_status=Unverified")
        assert res5_match.status_code == 200
        assert res5_match.json()["count"] == 2

        res5_nomatch = await client.get("/api/events/map?verification_status=Verified")
        assert res5_nomatch.status_code == 200
        assert res5_nomatch.json()["count"] == 0

        res5_invalid = await client.get("/api/events/map?verification_status=UnknownStatus")
        assert res5_invalid.status_code == 400
        print("[OK] Test 5 passed: Verification status filter accurately filters records.")

        # --- Test 6: State and city case-insensitive filter ---
        print("\n--- [Test 6] State and city filter ---")
        res6_state_lower = await client.get("/api/events/map?state=chhattisgarh")
        assert res6_state_lower.status_code == 200
        assert res6_state_lower.json()["count"] == 2

        res6_state_upper = await client.get("/api/events/map?state=CHHATTISGARH")
        assert res6_state_upper.status_code == 200
        assert res6_state_upper.json()["count"] == 2

        res6_city_lower = await client.get("/api/events/map?city=raipur")
        assert res6_city_lower.status_code == 200
        assert res6_city_lower.json()["count"] == 2

        res6_nomatch = await client.get("/api/events/map?city=Atlantis")
        assert res6_nomatch.status_code == 200
        assert res6_nomatch.json()["count"] == 0
        print("[OK] Test 6 passed: Case-insensitive state and city matching operates correctly.")

        # --- Test 7: Time range filter ---
        print("\n--- [Test 7] Time range filter ---")
        # Record timestamps are 2026-10-07 20:00:00Z and 2026-10-07 20:30:00Z
        res7_partial = await client.get("/api/events/map?start_time=2026-10-07T20:15:00Z")
        assert res7_partial.status_code == 200
        body7_partial = res7_partial.json()
        assert body7_partial["count"] == 1
        assert "20:30" in body7_partial["data"][0]["event_timestamp"]

        res7_both = await client.get("/api/events/map?start_time=2026-10-07T19:00:00Z&end_time=2026-10-07T21:00:00Z")
        assert res7_both.status_code == 200
        assert res7_both.json()["count"] == 2

        res7_inverted = await client.get("/api/events/map?start_time=2026-10-08T00:00:00Z&end_time=2026-10-07T00:00:00Z")
        assert res7_inverted.status_code == 400
        print("[OK] Test 7 passed: Time range boundary filters and inverted time validation verified.")

        # --- Test 8: India bounding-box filter ---
        print("\n--- [Test 8] India bounding box filter ---")
        res8_india = await client.get("/api/events/map?min_lat=6.0&max_lat=37.5&min_lon=68.0&max_lon=97.5")
        assert res8_india.status_code == 200
        body8_india = res8_india.json()
        assert body8_india["count"] == 2
        for ev in body8_india["data"]:
            assert 6.0 <= ev["latitude"] <= 37.5
            assert 68.0 <= ev["longitude"] <= 97.5
        print("[OK] Test 8 passed: India bounding box filter contains both Raipur baseline records.")

        # --- Test 9: Custom bounding-box filter ---
        print("\n--- [Test 9] Custom bounding-box filter ---")
        # Bounding box around Raipur (21.25, 81.63)
        res9_raipur_box = await client.get("/api/events/map?min_lat=21.0&max_lat=21.5&min_lon=81.5&max_lon=82.0")
        assert res9_raipur_box.status_code == 200
        assert res9_raipur_box.json()["count"] == 2

        # Bounding box excluding Raipur (e.g. South India)
        res9_south_box = await client.get("/api/events/map?min_lat=8.0&max_lat=12.0&min_lon=76.0&max_lon=80.0")
        assert res9_south_box.status_code == 200
        assert res9_south_box.json()["count"] == 0
        assert res9_south_box.json()["data"] == []

        # Inverted lat bounding box (min_lat >= max_lat)
        res9_inv_lat = await client.get("/api/events/map?min_lat=30.0&max_lat=20.0&min_lon=70.0&max_lon=80.0")
        assert res9_inv_lat.status_code == 400

        # Inverted lon bounding box (min_lon >= max_lon)
        res9_inv_lon = await client.get("/api/events/map?min_lat=20.0&max_lat=30.0&min_lon=90.0&max_lon=80.0")
        assert res9_inv_lon.status_code == 400

        # Incomplete bounding box (e.g. only 2 parameters)
        res9_incomplete = await client.get("/api/events/map?min_lat=20.0&max_lat=30.0")
        assert res9_incomplete.status_code == 400
        print("[OK] Test 9 passed: Custom bounding box includes/excludes correctly and validates bounds.")

        # --- Test 10: Limit validation ---
        print("\n--- [Test 10] Limit validation ---")
        res10_limit1 = await client.get("/api/events/map?limit=1")
        assert res10_limit1.status_code == 200
        assert res10_limit1.json()["count"] == 1
        assert len(res10_limit1.json()["data"]) == 1

        # Check sorting: newest record (20:30) must be returned when limit=1
        assert "20:30" in res10_limit1.json()["data"][0]["event_timestamp"]

        res10_zero = await client.get("/api/events/map?limit=0")
        assert res10_zero.status_code == 422

        res10_negative = await client.get("/api/events/map?limit=-1")
        assert res10_negative.status_code == 422

        res10_over = await client.get("/api/events/map?limit=5001")
        assert res10_over.status_code == 422

        res10_max = await client.get("/api/events/map?limit=5000")
        assert res10_max.status_code == 200
        assert res10_max.json()["count"] == 2
        print("[OK] Test 10 passed: Limit parameter enforces [1, 5000] boundaries and orders DESC.")

        # --- Test 11: Combined filters ---
        print("\n--- [Test 11] Combined multi-attribute filters ---")
        res11 = await client.get(
            "/api/events/map?event_type=Other&source=Open_Meteo&state=chhattisgarh&city=raipur"
            "&min_lat=6.0&max_lat=37.5&min_lon=68.0&max_lon=97.5&limit=10"
        )
        assert res11.status_code == 200
        assert res11.json()["count"] == 2

        # Conflicting filter produces empty result
        res11_conflict = await client.get("/api/events/map?event_type=Other&state=Kerala")
        assert res11_conflict.status_code == 200
        assert res11_conflict.json()["count"] == 0
        print("[OK] Test 11 passed: Multi-attribute and conflicting combined filters behave properly.")

        # --- Test 12: Empty result schema ---
        print("\n--- [Test 12] Empty result schema ---")
        res12 = await client.get("/api/events/map?event_type=Heatwave")
        assert res12.status_code == 200
        body12 = res12.json()
        assert body12 == {"data": [], "count": 0}
        print("[OK] Test 12 passed: Empty result returns HTTP 200 with {'data': [], 'count': 0}.")

        # --- Test 13: SQL injection safety ---
        print("\n--- [Test 13] SQL injection safety ---")
        injection_queries = [
            "/api/events/map?city=%27%20OR%20%271%27=%271",
            "/api/events/map?state=%27;%20DROP%20TABLE%20weather_events;%20--",
            "/api/events/map?district=%22%20UNION%20SELECT%20*%20FROM%20weather_events%20--",
        ]
        for q in injection_queries:
            inj_res = await client.get(q)
            assert inj_res.status_code == 200
            assert inj_res.json()["count"] == 0

        # Verify DB still intact and count is baseline 2
        assert get_current_record_count() == 2
        print("[OK] Test 13 passed: SQL injection attempts neutralized, database unharmed.")

        # --- Test 14: Existing events API still works ---
        print("\n--- [Test 14] Existing events API regression ---")
        res14_events = await client.get("/api/events")
        assert res14_events.status_code == 200
        assert res14_events.json()["pagination"]["total"] == 2

        single_id = "ca16925a-d55f-4d28-9007-d3632be00eee"
        res14_single = await client.get(f"/api/events/{single_id}")
        assert res14_single.status_code == 200
        assert res14_single.json()["event_id"] == single_id

        res14_missing = await client.get("/api/events/00000000-0000-0000-0000-000000000000")
        assert res14_missing.status_code == 404
        print("[OK] Test 14 passed: Existing events endpoints (/api/events, /api/events/{id}) function correctly.")

        # --- Test 15: Health endpoints regression ---
        print("\n--- [Test 15] Health endpoints regression ---")
        res15_health = await client.get("/api/health")
        assert res15_health.status_code == 200
        assert res15_health.json() == {"status": "ok"}

        res15_db_health = await client.get("/api/database/health")
        assert res15_db_health.status_code == 200
        assert res15_db_health.json()["status"] == "ok"
        assert res15_db_health.json()["database"] == "connected"
        print("[OK] Test 15 passed: Health and database health endpoints operational.")

    # Final DB check
    final_count = get_current_record_count()
    print(f"\n[*] Final Supabase weather_events count: {final_count}")
    assert final_count == 2, f"Expected 2 records, got {final_count}"
    print("==========================================")
    print("ALL 15 MAP API TESTS PASSED!")
    print("==========================================")


if __name__ == "__main__":
    asyncio.run(run_map_api_tests())
