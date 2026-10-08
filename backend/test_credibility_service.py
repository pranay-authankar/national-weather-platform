"""
Comprehensive test suite for Weather Report Credibility Evaluation & Source Trust Scoring.

Covers:
1. Strong credible citizen report (corroborated by nearby weather + independent reports -> Verified).
2. Isolated report with insufficient evidence (valid fields, no nearby data -> Unverified, baseline score).
3. Report corroborated by nearby real weather (Open-Meteo observation -> Likely).
4. Contradictory weather conditions (e.g. Flooding during 0mm rain & arid heat, Heatwave during cold/rain -> Suspicious).
5. Duplicate report (duplicate penalty applied -> Suspicious).
6. Suspicious / incomplete / spam report (spam tokens, gibberish, invalid GPS, future timestamp -> Suspicious).
7. Source trust scoring (IMD=95, Open_Meteo=90, Citizen dynamic calculation, baseline neutral=50, verified increase, rejected decrease).
8. End-to-end POST /api/reports pipeline with database persistence of credibility fields.
9. Backward compatibility of GET /api/events and GET /api/events/{event_id}.
10. Database cleanup verification: Zero dummy records left in Supabase (count restored to baseline).
"""

import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
from datetime import datetime, timedelta, timezone
import httpx


from database import get_db_connection
from main import app
from schemas.events import VALID_CREDIBILITY_STATUSES
from services.report_credibility_service import (
    REASON_AGREES_WITH_WEATHER_OBSERVATION,
    REASON_CONTRADICTORY_WEATHER_OBSERVATION,
    REASON_CORROBORATING_INDEPENDENT_REPORTS,
    REASON_DUPLICATE_REPORT,
    REASON_FUTURE_TIMESTAMP,
    REASON_INCOMPLETE_OR_SPAM_DESCRIPTION,
    REASON_INVALID_LOCATION,
    REASON_KNOWN_EVENT_TYPE,
    REASON_MEANINGFUL_DESCRIPTION,
    REASON_NO_NEARBY_OBSERVATION_DATA,
    REASON_VALID_LOCATION,
    REASON_VALID_TIMESTAMP,
    STATUS_LIKELY,
    STATUS_SUSPICIOUS,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
    calculate_report_credibility,
    calculate_source_trust_score,
    evaluate_and_score_citizen_report,
)


def get_current_record_count() -> int:
    """Query current total weather_events in Supabase."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM weather_events;")
            return cur.fetchone()[0]


def delete_records_by_ids(event_ids: list):
    """Delete created test records from Supabase."""
    if not event_ids:
        return
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM weather_events WHERE event_id = ANY(%s::uuid[]);", (event_ids,))
            conn.commit()


# =========================================================================
# 1. Deterministic Unit Tests for Credibility Scoring
# =========================================================================

def test_isolated_report_insufficient_evidence():
    """
    Isolated report with valid fields but no nearby observation data
    must remain Unverified with baseline score (~45.0) and NOT be marked Suspicious.
    """
    now = datetime.now(timezone.utc)
    result = calculate_report_credibility(
        latitude=12.9716,
        longitude=77.5946,
        event_timestamp=now - timedelta(minutes=15),
        event_type="Heavy Rain",
        description="Waterlogging on 100 Feet Road after sudden downpour.",
        is_duplicate=False,
        duplicate_of=None,
        nearby_observations=[],
        nearby_citizen_reports=[],
    )

    assert result["credibility_status"] == STATUS_UNVERIFIED, f"Expected Unverified, got {result['credibility_status']}"
    assert 35.0 <= result["credibility_score"] < 55.0, f"Expected score in [35, 55), got {result['credibility_score']}"
    assert REASON_VALID_LOCATION in result["credibility_reasons"]
    assert REASON_VALID_TIMESTAMP in result["credibility_reasons"]
    assert REASON_MEANINGFUL_DESCRIPTION in result["credibility_reasons"]
    assert REASON_KNOWN_EVENT_TYPE in result["credibility_reasons"]
    assert REASON_NO_NEARBY_OBSERVATION_DATA in result["credibility_reasons"]
    assert REASON_CONTRADICTORY_WEATHER_OBSERVATION not in result["credibility_reasons"]
    print("[PASS] test_isolated_report_insufficient_evidence: Status is Unverified, score is neutral baseline.")


def test_report_corroborated_by_nearby_weather():
    """
    Citizen report agreeing with nearby official weather observation receives
    strong positive boost and maps to 'Likely' (score >= 55.0).
    """
    now = datetime.now(timezone.utc)
    mock_obs = [
        {
            "event_id": "mock-obs-1",
            "source": "Open_Meteo",
            "event_type": "Rainfall",
            "temperature": 26.5,
            "rainfall": 12.0,
            "humidity": 88.0,
            "wind_speed": 18.0,
        }
    ]

    result = calculate_report_credibility(
        latitude=21.25,
        longitude=81.63,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Rainfall",
        description="Continuous rain observed near city center for over 30 minutes.",
        is_duplicate=False,
        duplicate_of=None,
        nearby_observations=mock_obs,
        nearby_citizen_reports=[],
    )

    assert result["credibility_status"] == STATUS_LIKELY, f"Expected Likely, got {result['credibility_status']}"
    assert result["credibility_score"] >= 55.0, f"Expected score >= 55.0, got {result['credibility_score']}"
    assert REASON_AGREES_WITH_WEATHER_OBSERVATION in result["credibility_reasons"]
    print(f"[PASS] test_report_corroborated_by_nearby_weather: Status is Likely (score={result['credibility_score']}).")


def test_strong_credible_report_corroborated():
    """
    Citizen report corroborated by BOTH nearby weather observations and
    independent citizen reports maps to 'Verified' (score >= 80.0).
    """
    now = datetime.now(timezone.utc)
    mock_obs = [
        {
            "event_id": "mock-obs-1",
            "source": "Open_Meteo",
            "event_type": "Rainfall",
            "temperature": 25.0,
            "rainfall": 15.0,
            "humidity": 92.0,
            "wind_speed": 22.0,
        }
    ]
    mock_citizen = [
        {
            "event_id": "mock-citizen-2",
            "source": "Citizen_Report",
            "event_type": "Rainfall",
            "description": "Heavy showers on highway.",
            "duplicate_of": None,
        }
    ]

    result = calculate_report_credibility(
        latitude=21.25,
        longitude=81.63,
        event_timestamp=now - timedelta(minutes=20),
        event_type="Rainfall",
        description="Heavy monsoon downpour with standing water on main road.",
        is_duplicate=False,
        duplicate_of=None,
        nearby_observations=mock_obs,
        nearby_citizen_reports=mock_citizen,
    )

    assert result["credibility_status"] == STATUS_VERIFIED, f"Expected Verified, got {result['credibility_status']}"
    assert result["credibility_score"] >= 80.0, f"Expected score >= 80.0, got {result['credibility_score']}"
    assert REASON_AGREES_WITH_WEATHER_OBSERVATION in result["credibility_reasons"]
    assert REASON_CORROBORATING_INDEPENDENT_REPORTS in result["credibility_reasons"]
    print(f"[PASS] test_strong_credible_report_corroborated: Status is Verified (score={result['credibility_score']}).")


def test_contradictory_weather_conditions():
    """
    Severe physical contradiction between citizen report and nearby sensor observation
    penalizes the score and marks report as 'Suspicious' (score < 35.0).
    """
    now = datetime.now(timezone.utc)

    # Case A: Flooding reported when sensor recorded bone dry 42°C with 0mm rainfall and 20% humidity
    dry_obs = [
        {
            "event_id": "mock-obs-dry",
            "source": "Open_Meteo",
            "event_type": "Other",
            "temperature": 42.0,
            "rainfall": 0.0,
            "humidity": 20.0,
            "wind_speed": 8.0,
        }
    ]
    res_dry = calculate_report_credibility(
        latitude=28.6139,
        longitude=77.2090,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Flooding",
        description="Severe deep flooding across the whole market square with boats needed.",
        nearby_observations=dry_obs,
    )
    assert res_dry["credibility_status"] == STATUS_SUSPICIOUS
    assert res_dry["credibility_score"] < 35.0
    assert REASON_CONTRADICTORY_WEATHER_OBSERVATION in res_dry["credibility_reasons"]

    # Case B: Heatwave reported when sensor recorded 15°C with heavy rain
    cold_obs = [
        {
            "event_id": "mock-obs-cold",
            "source": "Open_Meteo",
            "event_type": "Heavy Rain",
            "temperature": 15.0,
            "rainfall": 20.0,
            "humidity": 95.0,
            "wind_speed": 10.0,
        }
    ]
    res_cold = calculate_report_credibility(
        latitude=31.1048,
        longitude=77.1734,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Heatwave",
        description="Extreme scorching heatwave with blistering sun and sunstrokes.",
        nearby_observations=cold_obs,
    )
    assert res_cold["credibility_status"] == STATUS_SUSPICIOUS
    assert res_cold["credibility_score"] < 35.0
    assert REASON_CONTRADICTORY_WEATHER_OBSERVATION in res_cold["credibility_reasons"]
    print("[PASS] test_contradictory_weather_conditions: Both physical contradiction cases mapped to Suspicious.")


def test_duplicate_report_penalty():
    """
    Duplicate reports receive negative duplicate signal and map to Suspicious (< 35.0).
    """
    now = datetime.now(timezone.utc)
    result = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=now - timedelta(minutes=5),
        event_type="Heavy Rain",
        description="Heavy rain near Dadar station causing train delays.",
        is_duplicate=True,
        duplicate_of="11111111-2222-3333-4444-555555555555",
        nearby_observations=[],
    )
    assert result["credibility_status"] == STATUS_SUSPICIOUS
    assert result["credibility_score"] < 35.0
    assert REASON_DUPLICATE_REPORT in result["credibility_reasons"]
    print(f"[PASS] test_duplicate_report_penalty: Status is Suspicious (score={result['credibility_score']}).")


def test_suspicious_incomplete_content():
    """
    Incomplete descriptions, repetitive spam, invalid GPS, and future timestamps
    are correctly flagged with negative penalties.
    """
    now = datetime.now(timezone.utc)

    # 1. Obvious spam / placeholder description
    res_spam = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=now,
        event_type="Thunderstorm",
        description="test test asdf fake",
        nearby_observations=[],
    )
    assert REASON_INCOMPLETE_OR_SPAM_DESCRIPTION in res_spam["credibility_reasons"]
    assert res_spam["credibility_status"] == STATUS_SUSPICIOUS

    # 2. Invalid coordinates
    res_bad_gps = calculate_report_credibility(
        latitude=195.0,  # Invalid latitude (> 90)
        longitude=72.8777,
        event_timestamp=now,
        event_type="Thunderstorm",
        description="Heavy storm and thunder rattling window frames.",
        nearby_observations=[],
    )
    assert REASON_INVALID_LOCATION in res_bad_gps["credibility_reasons"]
    assert res_bad_gps["credibility_status"] == STATUS_SUSPICIOUS

    # 3. Future timestamp (+5 days)
    res_future = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=now + timedelta(days=5),
        event_type="Thunderstorm",
        description="Heavy storm and thunder rattling window frames.",
        nearby_observations=[],
    )
    assert REASON_FUTURE_TIMESTAMP in res_future["credibility_reasons"]
    assert res_future["credibility_status"] == STATUS_SUSPICIOUS
    print("[PASS] test_suspicious_incomplete_content: Spam, invalid GPS, and future timestamps properly flagged.")


def test_source_trust_scoring():
    """
    Validate source trust scoring for official sources and dynamic citizen trust.
    """
    # Official / Established sources
    assert calculate_source_trust_score("IMD") == 95.0
    assert calculate_source_trust_score("IMD_RSS") == 95.0
    assert calculate_source_trust_score("Data_Gov") == 95.0
    assert calculate_source_trust_score("Open_Meteo") == 90.0
    assert calculate_source_trust_score("Unknown_Source") == 50.0

    # Citizen_Report with no historical data -> baseline neutral (50.0)
    assert calculate_source_trust_score("Citizen_Report", historical_stats={"total_count": 0}) == 50.0

    # Citizen_Report with high verified ratio -> increased trust (> 50.0)
    high_trust = calculate_source_trust_score(
        "Citizen_Report",
        historical_stats={
            "total_count": 10,
            "verified_count": 8,
            "likely_count": 2,
            "suspicious_count": 0,
            "duplicate_count": 1,
        },
    )
    assert high_trust > 50.0
    assert high_trust <= 90.0  # Respects maximum clamp

    # Citizen_Report with high suspicious/rejected count -> decreased trust (< 50.0)
    low_trust = calculate_source_trust_score(
        "Citizen_Report",
        historical_stats={
            "total_count": 10,
            "verified_count": 0,
            "likely_count": 0,
            "suspicious_count": 8,
            "duplicate_count": 2,
        },
    )
    assert low_trust < 50.0
    assert low_trust >= 10.0  # Respects minimum clamp

    # Duplicates should NOT increase trust
    dup_stats = {
        "total_count": 5,
        "verified_count": 0,
        "likely_count": 0,
        "suspicious_count": 0,
        "duplicate_count": 5,
    }
    assert calculate_source_trust_score("Citizen_Report", historical_stats=dup_stats) == 50.0
    print("[PASS] test_source_trust_scoring: Official constants and dynamic citizen calculations verified.")


# =========================================================================
# 2. End-to-End API and Database Integration Tests
# =========================================================================

async def run_integration_and_database_tests():
    baseline_count = get_current_record_count()
    print(f"\n[*] Starting Integration Tests. Baseline Supabase records: {baseline_count}")
    assert baseline_count == 2, f"Expected exactly 2 baseline records, found {baseline_count}"

    transport = httpx.ASGITransport(app=app)
    created_event_ids = []

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            
            # --- Integration 1: Submit Citizen Report and check DB persistence of credibility fields ---
            print("\n--- [Integration 1] Submit Citizen Report via POST /api/reports ---")
            payload = {
                "event_type": "Thunderstorm",
                "description": "TEMPORARY_TEST_CREDIBILITY: Severe localized lightning and intense rainfall.",
                "latitude": 21.2514,
                "longitude": 81.6296,
                "timestamp": "2026-10-08T18:00:00Z",
            }
            res = await client.post("/api/reports", json=payload)
            assert res.status_code == 201, f"Failed: {res.text}"
            res_data = res.json()
            assert "event_id" in res_data
            assert res_data["status"] == "received"
            event_id = res_data["event_id"]
            created_event_ids.append(event_id)

            # Query database directly to verify stored credibility columns
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            credibility_score,
                            credibility_status,
                            credibility_reasons,
                            source_trust_score
                        FROM public.weather_events
                        WHERE event_id = %s::uuid;
                    """, (event_id,))
                    row = cur.fetchone()
                    assert row is not None, "Report record was not found in weather_events!"
                    cred_score, cred_status, cred_reasons, src_trust = row
                    print(f"Persisted DB columns: score={cred_score}, status={cred_status}, reasons={cred_reasons}, trust={src_trust}")
                    assert cred_score is not None
                    assert cred_status in VALID_CREDIBILITY_STATUSES
                    assert isinstance(cred_reasons, list)
                    assert len(cred_reasons) > 0
                    assert src_trust is not None

            # --- Integration 2: GET /api/events/{event_id} returns credibility fields ---
            print("\n--- [Integration 2] GET /api/events/{event_id} response contains credibility fields ---")
            detail_res = await client.get(f"/api/events/{event_id}")
            assert detail_res.status_code == 200, f"Failed: {detail_res.text}"
            detail_data = detail_res.json()
            assert "credibility_score" in detail_data
            assert "credibility_status" in detail_data
            assert "credibility_reasons" in detail_data
            assert "source_trust_score" in detail_data
            assert detail_data["credibility_status"] == cred_status
            assert detail_data["credibility_score"] == cred_score
            print(f"[PASS] GET /api/events/{event_id} correctly serialized credibility fields.")

            # --- Integration 3: GET /api/events with credibility_status filter ---
            print("\n--- [Integration 3] GET /api/events?credibility_status=... ---")
            filter_res = await client.get(f"/api/events?credibility_status={cred_status}")
            assert filter_res.status_code == 200, f"Failed: {filter_res.text}"
            events_list = filter_res.json()["data"]
            found_ids = [e["event_id"] for e in events_list]
            assert event_id in found_ids
            print(f"[PASS] GET /api/events successfully filtered by credibility_status='{cred_status}'.")

            # --- Integration 4: Backward compatibility of existing Open-Meteo records ---
            print("\n--- [Integration 4] Backward compatibility of GET /api/events for baseline records ---")
            all_res = await client.get("/api/events?source=Open_Meteo")
            assert all_res.status_code == 200
            open_meteo_events = all_res.json()["data"]
            assert len(open_meteo_events) >= 2
            for ev in open_meteo_events:
                # Fields exist in response schema as None or float
                assert "credibility_score" in ev
                assert "credibility_status" in ev
                assert "credibility_reasons" in ev
                assert "source_trust_score" in ev
            print("[PASS] Backward compatibility verified for existing Open-Meteo records.")

    finally:
        # --- Strict Database Cleanup ---
        print("\n--- Cleaning up temporary test records ---")
        delete_records_by_ids(created_event_ids)
        final_count = get_current_record_count()
        print(f"Final record count in Supabase: {final_count}")
        assert final_count == baseline_count, (
            f"ERROR: DB record count mismatch! Baseline was {baseline_count}, now {final_count}!"
        )
        print("[SUCCESS] Zero test records remain. Baseline DB count (2) verified intact!")


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING REPORT CREDIBILITY & SOURCE TRUST UNIT TESTS")
    print("=" * 70)
    test_isolated_report_insufficient_evidence()
    test_report_corroborated_by_nearby_weather()
    test_strong_credible_report_corroborated()
    test_contradictory_weather_conditions()
    test_duplicate_report_penalty()
    test_suspicious_incomplete_content()
    test_source_trust_scoring()

    print("\n" + "=" * 70)
    print("RUNNING REPORT CREDIBILITY INTEGRATION & DATABASE TESTS")
    print("=" * 70)
    asyncio.run(run_integration_and_database_tests())
    print("\nALL CREDIBILITY TESTS PASSED SUCCESSFULLY!")
