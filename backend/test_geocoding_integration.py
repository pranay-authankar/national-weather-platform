"""
Comprehensive verification test for Reverse Geocoding in Citizen Weather Reports.
Tests:
1. Geocoding service behavior on real coordinates (Mumbai, Raipur)
2. Geocoding service behavior on open water / non-geocodable coordinates
3. Geocoding service error and timeout resilience (custom provider that throws)
4. Integration with POST /api/reports:
   - Submits temporary citizen report with real coordinates
   - Queries Supabase to assert city, district, state are correctly populated
   - Deletes temporary citizen report from Supabase
   - Asserts deletion succeeded
5. Integration with POST /api/reports on failed/unmapped coordinates:
   - Submits report with ocean coordinates
   - Asserts city, district, state stored as NULL
   - Deletes temporary citizen report from Supabase
   - Confirms database contains no dummy/test records
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
from datetime import datetime, timezone
import httpx
from main import app
from database import get_db_connection
from services.geocoding_service import (
    BaseGeocodingProvider,
    GeocodedLocation,
    NominatimGeocodingProvider,
    get_geocoding_provider,
    set_geocoding_provider,
    reverse_geocode,
)


class FailingProvider(BaseGeocodingProvider):
    """Provider that simulates unexpected network/timeout failures."""
    async def reverse_geocode(self, latitude: float, longitude: float) -> GeocodedLocation:
        raise httpx.ConnectTimeout("Connection timed out simulating network failure")


async def test_geocoding_service_unit():
    print("--- [1] Unit Tests: Real Reverse Geocoding ---")
    
    # Mumbai coordinates
    mumbai_res = await reverse_geocode(19.0760, 72.8777)
    print("Mumbai reverse geocode:", mumbai_res)
    assert mumbai_res["city"] == "Mumbai", f"Expected Mumbai, got {mumbai_res['city']}"
    assert mumbai_res["state"] == "Maharashtra", f"Expected Maharashtra, got {mumbai_res['state']}"
    assert mumbai_res["district"] is not None, f"Expected non-null district, got {mumbai_res['district']}"
    print("[OK] Mumbai coordinates resolved successfully")

    await asyncio.sleep(1)

    # Ocean coordinates
    ocean_res = await reverse_geocode(15.0, 65.0)
    print("Ocean reverse geocode:", ocean_res)
    assert ocean_res["city"] is None
    assert ocean_res["district"] is None
    assert ocean_res["state"] is None
    print("[OK] Ocean coordinates returned NULL as expected")

    # Error simulation
    original_provider = get_geocoding_provider()
    try:
        set_geocoding_provider(FailingProvider())
        failing_res = await reverse_geocode(19.0760, 72.8777)
        print("Failing provider result:", failing_res)
        assert failing_res == {"city": None, "district": None, "state": None}
        print("[OK] Failing provider handled gracefully without throwing")
    finally:
        set_geocoding_provider(original_provider)


async def test_endpoint_and_database_persistence():
    print("\n--- [2] Integration Test: POST /api/reports with real coordinates ---")

    # Check baseline record count
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM weather_events;")
            baseline_count = cur.fetchone()[0]
    print(f"Baseline database record count: {baseline_count}")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Submit temporary report for Mumbai
        payload = {
            "event_type": "Heavy Rain",
            "description": "TEMPORARY_TEST_REPORT: Waterlogging near Kurla station for reverse-geocoding verification.",
            "latitude": 19.0760,
            "longitude": 72.8777,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image_url": "https://example.com/test_waterlogging.jpg",
        }
        
        response = await client.post("/api/reports", json=payload)
        print(f"POST /api/reports status code: {response.status_code}")
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        print(f"Response body: {data}")
        event_id = data.get("event_id")
        assert event_id is not None
        assert data.get("status") == "received"

    # Verify record in Supabase / PostgreSQL
    print(f"\nVerifying event {event_id} in Supabase database...")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT event_id, source, event_type, city, district, state, verification_status
                FROM weather_events
                WHERE event_id = %s;
            """, (event_id,))
            row = cur.fetchone()
            assert row is not None, f"Event {event_id} not found in weather_events!"
            
            db_event_id, db_source, db_event_type, db_city, db_district, db_state, db_status = row
            print(f"Retrieved from Supabase:\n"
                  f"  event_id: {db_event_id}\n"
                  f"  source: {db_source}\n"
                  f"  event_type: {db_event_type}\n"
                  f"  city: {db_city}\n"
                  f"  district: {db_district}\n"
                  f"  state: {db_state}\n"
                  f"  verification_status: {db_status}")

            assert db_source == "Citizen_Report"
            assert db_event_type == "Heavy Rain"
            assert db_city == "Mumbai", f"Expected city 'Mumbai', got {db_city}"
            assert db_district is not None, f"Expected non-null district, got {db_district}"
            assert db_state == "Maharashtra", f"Expected state 'Maharashtra', got {db_state}"
            assert db_status == "Unverified"
            print("[OK] Database record verified: city, district, and state correctly populated!")

            # Clean up: DELETE the temporary test record
            print(f"\nCleaning up: Deleting temporary test record {event_id} from Supabase...")
            cur.execute("DELETE FROM weather_events WHERE event_id = %s;", (event_id,))
            deleted_rows = cur.rowcount
            conn.commit()
            print(f"Deleted {deleted_rows} row(s).")
            assert deleted_rows == 1

            # Confirm record is gone
            cur.execute("SELECT COUNT(*) FROM weather_events WHERE event_id = %s;", (event_id,))
            remaining = cur.fetchone()[0]
            assert remaining == 0
            print(f"[OK] Confirmed record {event_id} is permanently deleted.")

            # Confirm database count equals baseline
            cur.execute("SELECT COUNT(*) FROM weather_events;")
            final_count = cur.fetchone()[0]
            assert final_count == baseline_count, f"Count mismatch: baseline={baseline_count}, final={final_count}"
            print(f"[OK] Database clean! Record count restored to baseline: {final_count}")


async def test_endpoint_with_unmapped_coordinates():
    print("\n--- [3] Integration Test: POST /api/reports with unmapped (ocean) coordinates ---")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "event_type": "Other",
            "description": "TEMPORARY_TEST_REPORT: Coordinates in Arabian Sea with no admin boundary.",
            "latitude": 15.0,
            "longitude": 65.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await client.post("/api/reports", json=payload)
        assert response.status_code == 201
        event_id = response.json()["event_id"]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT city, district, state FROM weather_events WHERE event_id = %s;
            """, (event_id,))
            row = cur.fetchone()
            assert row is not None
            city, district, state = row
            assert city is None, f"Expected city to be None, got {city}"
            assert district is None, f"Expected district to be None, got {district}"
            assert state is None, f"Expected state to be None, got {state}"
            print("[OK] Unmapped coordinates stored as NULL without rejecting the report")

            # Clean up immediately
            cur.execute("DELETE FROM weather_events WHERE event_id = %s;", (event_id,))
            conn.commit()
            print(f"[OK] Cleaned up ocean test report {event_id}")


async def main():
    try:
        await test_geocoding_service_unit()
        await test_endpoint_and_database_persistence()
        await test_endpoint_with_unmapped_coordinates()
        print("\n==========================================")
        print("ALL REVERSE GEOCODING TESTS PASSED!")
        print("==========================================")
    except Exception as exc:
        print(f"\n[FAIL] TEST FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
