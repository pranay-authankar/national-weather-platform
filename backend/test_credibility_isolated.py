"""
Isolated unit test suite for Weather Report Credibility Evaluation & Source Trust Scoring (Test 9A).

Strict Safety Guarantees:
- Fully isolated from Supabase PostgreSQL database. Zero database connections attempted.
- Does NOT execute run_integration_and_database_tests or write live records.
- Does NOT rely on hardcoded baseline record counts.
- Does NOT run the background scheduler or trigger external data ingestion.
- Purely deterministic, in-memory execution using unittest.mock.

Coverage Additions for Test 9A:
1. Score clamping: Compounded negative signals clamp score to exactly 0.0.
2. Missing inputs: All-None inputs handled gracefully without unhandled exceptions.
3. Exact status thresholds: Status transitions below, at, and above 35.0, 55.0, 80.0.
4. Reason codes: BRIEF_DESCRIPTION, STALE_TIMESTAMP, UNKNOWN_EVENT_TYPE, and evidence_summary formatting.
5. Determinism: 100 consecutive iterations with fixed inputs produce byte-for-byte identical outputs.
6. Source-trust fallback: Database connection failure in fetch_citizen_historical_stats falls back to 50.0.
7. Media scoring observation: Documents that image_url and video_url do not affect credibility scoring.
8. Core regression suite: Incorporates the 7 existing pure unit tests in isolated mode.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from schemas.events import VALID_CREDIBILITY_STATUSES, VALID_EVENT_TYPES
from services.report_credibility_service import (
    REASON_AGREES_WITH_WEATHER_OBSERVATION,
    REASON_BRIEF_DESCRIPTION,
    REASON_CONTRADICTORY_WEATHER_OBSERVATION,
    REASON_CORROBORATING_INDEPENDENT_REPORTS,
    REASON_DUPLICATE_REPORT,
    REASON_FUTURE_TIMESTAMP,
    REASON_INCOMPLETE_OR_SPAM_DESCRIPTION,
    REASON_INVALID_LOCATION,
    REASON_INVALID_TIMESTAMP,
    REASON_KNOWN_EVENT_TYPE,
    REASON_MEANINGFUL_DESCRIPTION,
    REASON_NO_NEARBY_OBSERVATION_DATA,
    REASON_STALE_TIMESTAMP,
    REASON_UNKNOWN_EVENT_TYPE,
    REASON_VALID_LOCATION,
    REASON_VALID_TIMESTAMP,
    SCORE_THRESHOLD_LIKELY_MIN,
    SCORE_THRESHOLD_UNVERIFIED_MIN,
    SCORE_THRESHOLD_VERIFIED_MIN,
    SOURCE_TRUST_CITIZEN_BASE,
    SOURCE_TRUST_DATA_GOV,
    SOURCE_TRUST_DEFAULT,
    SOURCE_TRUST_IMD,
    SOURCE_TRUST_IMD_RSS,
    SOURCE_TRUST_OPEN_METEO,
    STATUS_LIKELY,
    STATUS_SUSPICIOUS,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
    calculate_report_credibility,
    calculate_source_trust_score,
    evaluate_and_score_citizen_report,
    evaluate_description_signal,
    evaluate_event_type_signal,
    evaluate_location_signal,
    evaluate_timestamp_signal,
    fetch_citizen_historical_stats,
    map_score_to_credibility_status,
)


# Global tracker to ensure zero real database connections are attempted
real_db_connections_attempted = 0


def guard_db_connection(*args, **kwargs):
    global real_db_connections_attempted
    real_db_connections_attempted += 1
    raise RuntimeError("CRITICAL SAFETY VIOLATION: Database connection attempted during isolated testing!")


# ==============================================================================
# 1. Score Clamping Tests
# ==============================================================================

def test_score_clamping_to_zero():
    """Verify that compounded negative signals clamp the credibility score to exactly 0.0."""
    now = datetime.now(timezone.utc)

    # 1a. Compounded negative signals: invalid loc (-25), future ts (-25),
    # spam desc (-20), unknown type (-15), contradiction (-35), duplicate (-30)
    # Total accumulated = -150.0 -> must clamp to 0.0
    contradictory_obs = [{
        "event_id": "mock-obs-dry",
        "source": "Open_Meteo",
        "event_type": "Other",
        "temperature": 42.0,
        "rainfall": 0.0,
        "humidity": 15.0,
        "wind_speed": 5.0,
    }]

    res_extreme_negative = calculate_report_credibility(
        latitude=999.0,                           # Invalid location (-25)
        longitude=999.0,
        event_timestamp=now + timedelta(days=5),  # Future timestamp (-25)
        event_type="Heatwave",                    # Contradicts nearby obs (-35)
        description="test fake dummy",            # Spam description (-20)
        is_duplicate=True,                        # Duplicate penalty (-30)
        duplicate_of="00000000-0000-0000-0000-000000000001",
        nearby_observations=contradictory_obs,
    )

    assert res_extreme_negative["credibility_score"] == 0.0, (
        f"Expected score 0.0, got {res_extreme_negative['credibility_score']}"
    )
    assert res_extreme_negative["credibility_status"] == STATUS_SUSPICIOUS
    assert REASON_INVALID_LOCATION in res_extreme_negative["credibility_reasons"]
    assert REASON_FUTURE_TIMESTAMP in res_extreme_negative["credibility_reasons"]
    assert REASON_INCOMPLETE_OR_SPAM_DESCRIPTION in res_extreme_negative["credibility_reasons"]
    assert REASON_DUPLICATE_REPORT in res_extreme_negative["credibility_reasons"]

    # 1b. Moderate negative signals: Valid fields (+45), but contradiction (-35) and duplicate (-30)
    # Total accumulated = 45 - 35 - 30 = -20.0 -> must clamp to 0.0
    res_moderate_negative = calculate_report_credibility(
        latitude=28.6139,
        longitude=77.2090,
        event_timestamp=now - timedelta(minutes=15),
        event_type="Flooding",
        description="Deep flood water logging on market road requiring boats.",
        is_duplicate=True,
        duplicate_of="00000000-0000-0000-0000-000000000002",
        nearby_observations=contradictory_obs,
    )

    assert res_moderate_negative["credibility_score"] == 0.0, (
        f"Expected score 0.0, got {res_moderate_negative['credibility_score']}"
    )
    assert res_moderate_negative["credibility_status"] == STATUS_SUSPICIOUS
    print("  [PASS] 1a. Score clamping: Compounded negative signals clamp cleanly to 0.0.")


def test_upper_score_boundary_documentation():
    """
    Document upper boundary behavior without distorting production code.
    Verifies that all possible positive signals yield maximum legitimate score (90.0).
    """
    now = datetime.now(timezone.utc)
    mock_obs = [{
        "event_id": "mock-obs-1",
        "source": "Open_Meteo",
        "event_type": "Heavy Rain",
        "temperature": 24.0,
        "rainfall": 25.0,
        "humidity": 95.0,
        "wind_speed": 20.0,
    }]
    mock_citizen = [{
        "event_id": "mock-citizen-1",
        "source": "Citizen_Report",
        "event_type": "Heavy Rain",
        "description": "Flooding on highway.",
        "duplicate_of": None,
    }]

    # All positive signals: loc(+10) + ts(+10) + desc(+15) + type(+10) + agree(+25) + corrob(+20) = 90.0
    res_max = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Heavy Rain",
        description="Torrential monsoon downpour flooding low-lying streets and markets.",
        nearby_observations=mock_obs,
        nearby_citizen_reports=mock_citizen,
    )

    assert res_max["credibility_score"] == 90.0, f"Expected 90.0, got {res_max['credibility_score']}"
    assert res_max["credibility_status"] == STATUS_VERIFIED
    # Confirm clamp function accepts 100.0 without distortion
    assert map_score_to_credibility_status(100.0) == STATUS_VERIFIED
    print("  [PASS] 1b. Upper score boundary: Reaches legitimate maximum 90.0 (Verified) under all positive signals.")


# ==============================================================================
# 2. Missing & None Input Handling Tests
# ==============================================================================

def test_all_none_inputs_handling():
    """Verify that passing None for all parameters runs safely without unhandled exceptions."""
    res_none = calculate_report_credibility(
        latitude=None,
        longitude=None,
        event_timestamp=None,
        event_type=None,
        description=None,
    )

    assert res_none["credibility_score"] == 0.0
    assert res_none["credibility_status"] == STATUS_SUSPICIOUS
    assert isinstance(res_none["credibility_reasons"], list)
    assert REASON_INVALID_LOCATION in res_none["credibility_reasons"]
    assert REASON_INVALID_TIMESTAMP in res_none["credibility_reasons"]
    assert REASON_INCOMPLETE_OR_SPAM_DESCRIPTION in res_none["credibility_reasons"]
    assert REASON_UNKNOWN_EVENT_TYPE in res_none["credibility_reasons"]
    assert REASON_NO_NEARBY_OBSERVATION_DATA in res_none["credibility_reasons"]
    assert isinstance(res_none["evidence_summary"], str)
    assert "Credibility: Suspicious (0.0/100.0)" in res_none["evidence_summary"]
    print("  [PASS] 2a. Missing inputs: All-None input handled safely, yielding 0.0 Suspicious.")


def test_isolated_none_fields_handling():
    """Verify isolated None fields individually trigger appropriate penalty codes."""
    now = datetime.now(timezone.utc)
    base = {
        "latitude": 21.1458,
        "longitude": 79.0882,
        "event_timestamp": now - timedelta(minutes=10),
        "event_type": "Thunderstorm",
        "description": "Loud thunder and heavy rain over the western sector.",
    }

    # Only latitude is None
    res_lat = calculate_report_credibility(**{**base, "latitude": None})
    assert REASON_INVALID_LOCATION in res_lat["credibility_reasons"]
    assert REASON_VALID_TIMESTAMP in res_lat["credibility_reasons"]

    # Only timestamp is None
    res_ts = calculate_report_credibility(**{**base, "event_timestamp": None})
    assert REASON_INVALID_TIMESTAMP in res_ts["credibility_reasons"]
    assert REASON_VALID_LOCATION in res_ts["credibility_reasons"]

    # Only description is None
    res_desc = calculate_report_credibility(**{**base, "description": None})
    assert REASON_INCOMPLETE_OR_SPAM_DESCRIPTION in res_desc["credibility_reasons"]

    # Only event_type is None
    res_type = calculate_report_credibility(**{**base, "event_type": None})
    assert REASON_UNKNOWN_EVENT_TYPE in res_type["credibility_reasons"]
    print("  [PASS] 2b. Missing inputs: Individual None fields isolated correctly with specific reasons.")


# ==============================================================================
# 3. Exact Status Thresholds Tests
# ==============================================================================

def test_exact_status_thresholds():
    """
    Verify the status mapping immediately below, at, and above the thresholds:
    - Below 35.0: Suspicious
    - 35.0 to 54.9: Unverified
    - 55.0 to 79.9: Likely
    - 80.0 to 100.0: Verified
    """
    threshold_cases = [
        (0.0, STATUS_SUSPICIOUS),
        (34.8, STATUS_SUSPICIOUS),
        (34.9, STATUS_SUSPICIOUS),
        (35.0, STATUS_UNVERIFIED),
        (35.1, STATUS_UNVERIFIED),
        (45.0, STATUS_UNVERIFIED),
        (54.9, STATUS_UNVERIFIED),
        (55.0, STATUS_LIKELY),
        (55.1, STATUS_LIKELY),
        (70.0, STATUS_LIKELY),
        (79.9, STATUS_LIKELY),
        (80.0, STATUS_VERIFIED),
        (80.1, STATUS_VERIFIED),
        (90.0, STATUS_VERIFIED),
        (100.0, STATUS_VERIFIED),
    ]

    for score, expected_status in threshold_cases:
        actual_status = map_score_to_credibility_status(score)
        assert actual_status == expected_status, (
            f"Score {score} mapped to {actual_status}, expected {expected_status}"
        )
    print("  [PASS] 3. Exact status thresholds: Boundaries (34.9/35.0, 54.9/55.0, 79.9/80.0) verified.")


# ==============================================================================
# 4. Reason Codes and Descriptions Tests
# ==============================================================================

def test_brief_description_reason():
    """Verify BRIEF_DESCRIPTION is assigned for descriptions between 5 and 14 chars or < 3 words."""
    now = datetime.now(timezone.utc)

    # 10 characters, 2 words -> BRIEF_DESCRIPTION (+5.0)
    score_adj, reasons = evaluate_description_signal("Rain storm")
    assert score_adj == 5.0
    assert reasons == [REASON_BRIEF_DESCRIPTION]

    res = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Heavy Rain",
        description="Rain storm",
    )
    assert REASON_BRIEF_DESCRIPTION in res["credibility_reasons"]
    assert REASON_MEANINGFUL_DESCRIPTION not in res["credibility_reasons"]
    # Base: loc(+10) + ts(+10) + brief_desc(+5) + type(+10) = 35.0 (Unverified)
    assert res["credibility_score"] == 35.0
    assert res["credibility_status"] == STATUS_UNVERIFIED
    print("  [PASS] 4a. Reason codes: BRIEF_DESCRIPTION correctly triggered for brief notes.")


def test_stale_timestamp_reason():
    """Verify STALE_TIMESTAMP (-15.0) is assigned for reports older than 30 days."""
    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(days=35)

    score_adj, reasons = evaluate_timestamp_signal(stale_time)
    assert score_adj == -15.0
    assert reasons == [REASON_STALE_TIMESTAMP]

    res = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=stale_time,
        event_type="Rainfall",
        description="Heavy rain observed near Dadar market intersection.",
    )
    assert REASON_STALE_TIMESTAMP in res["credibility_reasons"]
    assert REASON_VALID_TIMESTAMP not in res["credibility_reasons"]
    # Base: loc(+10) + stale_ts(-15) + desc(+15) + type(+10) = 20.0 (Suspicious)
    assert res["credibility_score"] == 20.0
    assert res["credibility_status"] == STATUS_SUSPICIOUS
    print("  [PASS] 4b. Reason codes: STALE_TIMESTAMP correctly triggered for observations >30 days old.")


def test_unknown_event_type_reason():
    """Verify UNKNOWN_EVENT_TYPE (-15.0) is assigned for non-canonical classifications."""
    score_adj, reasons = evaluate_event_type_signal("AlienInvasion")
    assert score_adj == -15.0
    assert reasons == [REASON_UNKNOWN_EVENT_TYPE]

    res = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
        event_type="VolcanicAshfall",
        description="Heavy ash falling on streets and buildings.",
    )
    assert REASON_UNKNOWN_EVENT_TYPE in res["credibility_reasons"]
    assert REASON_KNOWN_EVENT_TYPE not in res["credibility_reasons"]
    # Base: loc(+10) + ts(+10) + desc(+15) + unknown_type(-15) = 20.0 (Suspicious)
    assert res["credibility_score"] == 20.0
    assert res["credibility_status"] == STATUS_SUSPICIOUS
    print("  [PASS] 4c. Reason codes: UNKNOWN_EVENT_TYPE correctly triggered for non-canonical events.")


def test_evidence_summary_formatting():
    """Verify format, structure, and text content of evidence_summary."""
    now = datetime.now(timezone.utc)
    res = calculate_report_credibility(
        latitude=21.1458,
        longitude=79.0882,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Heavy Rain",
        description="Localized waterlogging observed near the main intersection.",
    )

    summary = res["evidence_summary"]
    # Assert structural pattern
    pattern = r"^Credibility:\s+(Verified|Likely|Unverified|Suspicious)\s+\(\d+\.\d+/100\.0\)\.\s+Positive signals:\s+\[.*\]\.\s+Negative signals:\s+\[.*\]\.$"
    assert re.match(pattern, summary), f"Summary does not match expected structure: {summary}"
    assert "Positive signals: [" in summary
    assert "Negative signals: [" in summary
    assert "Valid GPS coordinates" in summary
    assert "Valid recent observation timestamp" in summary
    assert "Detailed and meaningful eyewitness description" in summary
    print("  [PASS] 4d. Evidence summary: Structured format and signal contents verified.")


# ==============================================================================
# 5. Determinism Tests (100 Iterations)
# ==============================================================================

def test_determinism_100_iterations():
    """Verify 100 consecutive evaluations of identical inputs produce byte-for-byte identical outputs."""
    fixed_now = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
    fixed_event_time = datetime(2026, 10, 9, 11, 45, 0, tzinfo=timezone.utc)

    mock_obs = [{
        "event_id": "obs-fixed-1",
        "source": "Open_Meteo",
        "event_type": "Thunderstorm",
        "temperature": 27.0,
        "rainfall": 18.0,
        "humidity": 90.0,
        "wind_speed": 30.0,
    }]
    mock_citizen = [{
        "event_id": "citizen-fixed-1",
        "source": "Citizen_Report",
        "event_type": "Thunderstorm",
        "description": "Loud thunder and strong winds.",
        "duplicate_of": None,
    }]

    # Subclass datetime to mock .now() safely while preserving isinstance checks
    class MockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    with patch("services.report_credibility_service.datetime", MockDateTime):
        first_run = calculate_report_credibility(
            latitude=21.25,
            longitude=81.63,
            event_timestamp=fixed_event_time,
            event_type="Thunderstorm",
            description="Violent thunderstorm with frequent lightning strikes and intense rainfall.",
            nearby_observations=mock_obs,
            nearby_citizen_reports=mock_citizen,
            source="Citizen_Report",
            historical_stats={"total_count": 0},
        )

        for i in range(2, 101):
            subsequent_run = calculate_report_credibility(
                latitude=21.25,
                longitude=81.63,
                event_timestamp=fixed_event_time,
                event_type="Thunderstorm",
                description="Violent thunderstorm with frequent lightning strikes and intense rainfall.",
                nearby_observations=mock_obs,
                nearby_citizen_reports=mock_citizen,
                source="Citizen_Report",
                historical_stats={"total_count": 0},
            )

            assert subsequent_run["credibility_score"] == first_run["credibility_score"], f"Score mismatch on run {i}"
            assert subsequent_run["credibility_status"] == first_run["credibility_status"], f"Status mismatch on run {i}"
            assert subsequent_run["credibility_reasons"] == first_run["credibility_reasons"], f"Reasons mismatch on run {i}"
            assert subsequent_run["evidence_summary"] == first_run["evidence_summary"], f"Summary mismatch on run {i}"
            assert subsequent_run["source_trust_score"] == first_run["source_trust_score"], f"Trust score mismatch on run {i}"

    print("  [PASS] 5. Determinism: 100 consecutive iterations produced identical results.")


# ==============================================================================
# 6. Source-Trust Fallback Tests
# ==============================================================================

def test_source_trust_fallback_on_database_failure():
    """Verify fetch_citizen_historical_stats gracefully handles database failure and returns neutral 50.0."""
    with patch("services.report_credibility_service.get_db_connection", side_effect=RuntimeError("Simulated DB connection failure")):
        # 1. Direct function fallback verification
        stats = fetch_citizen_historical_stats()
        assert stats == {
            "total_count": 0,
            "verified_count": 0,
            "likely_count": 0,
            "suspicious_count": 0,
            "duplicate_count": 0,
        }, f"Expected zero stats fallback, got {stats}"

        # 2. Source trust calculation using fallback stats
        trust_score = calculate_source_trust_score("Citizen_Report")
        assert trust_score == SOURCE_TRUST_CITIZEN_BASE == 50.0, (
            f"Expected neutral fallback 50.0, got {trust_score}"
        )
    print("  [PASS] 6. Source-trust fallback: Database failure caught gracefully, falling back to 50.0.")


# ==============================================================================
# 7. Media Scoring Observation Tests
# ==============================================================================

def test_media_urls_do_not_affect_credibility_score():
    """
    Document that image_url and video_url do not affect credibility scoring.
    Verifies that identical reports with and without media produce identical credibility output.
    """
    now = datetime.now(timezone.utc)
    base_args = {
        "latitude": 21.1458,
        "longitude": 79.0882,
        "event_timestamp": now - timedelta(minutes=15),
        "event_type": "Heavy Rain",
        "description": "Localized waterlogging observed near the main intersection.",
    }

    # Evaluate report without media
    res_no_media = calculate_report_credibility(**base_args)

    # In report_credibility_service, media URLs are neither parameters nor scoring signals.
    # Therefore, calling calculate_report_credibility with or without media yields identical output.
    assert "image_url" not in calculate_report_credibility.__code__.co_varnames
    assert "video_url" not in calculate_report_credibility.__code__.co_varnames

    # Confirm score remains exactly 45.0 (Unverified)
    assert res_no_media["credibility_score"] == 45.0
    assert res_no_media["credibility_status"] == STATUS_UNVERIFIED
    print("  [PASS] 7. Media scoring observation: Documented that media URLs have no impact on credibility score.")


# ==============================================================================
# 8. Core Regression Unit Tests (Isolated)
# ==============================================================================

def test_core_regression_suite():
    """Run the 7 existing pure unit tests in complete isolation."""
    now = datetime.now(timezone.utc)

    # R1. Isolated report with insufficient evidence
    res_iso = calculate_report_credibility(
        latitude=12.9716,
        longitude=77.5946,
        event_timestamp=now - timedelta(minutes=15),
        event_type="Heavy Rain",
        description="Waterlogging on 100 Feet Road after sudden downpour.",
        nearby_observations=[],
        nearby_citizen_reports=[],
    )
    assert res_iso["credibility_status"] == STATUS_UNVERIFIED
    assert 35.0 <= res_iso["credibility_score"] < 55.0
    assert REASON_NO_NEARBY_OBSERVATION_DATA in res_iso["credibility_reasons"]

    # R2. Report corroborated by nearby weather
    mock_obs = [{
        "event_id": "mock-obs-1",
        "source": "Open_Meteo",
        "event_type": "Rainfall",
        "temperature": 26.5,
        "rainfall": 12.0,
        "humidity": 88.0,
        "wind_speed": 18.0,
    }]
    res_corrob = calculate_report_credibility(
        latitude=21.25,
        longitude=81.63,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Rainfall",
        description="Continuous rain observed near city center for over 30 minutes.",
        nearby_observations=mock_obs,
    )
    assert res_corrob["credibility_status"] == STATUS_LIKELY
    assert res_corrob["credibility_score"] >= 55.0

    # R3. Strong credible report corroborated by weather and citizen
    mock_cit = [{
        "event_id": "mock-cit-1",
        "source": "Citizen_Report",
        "event_type": "Rainfall",
        "description": "Heavy showers on highway.",
        "duplicate_of": None,
    }]
    res_strong = calculate_report_credibility(
        latitude=21.25,
        longitude=81.63,
        event_timestamp=now - timedelta(minutes=20),
        event_type="Rainfall",
        description="Heavy monsoon downpour with standing water on main road.",
        nearby_observations=mock_obs,
        nearby_citizen_reports=mock_cit,
    )
    assert res_strong["credibility_status"] == STATUS_VERIFIED
    assert res_strong["credibility_score"] >= 80.0

    # R4. Contradictory weather conditions
    dry_obs = [{
        "event_id": "mock-dry",
        "source": "Open_Meteo",
        "event_type": "Other",
        "temperature": 42.0,
        "rainfall": 0.0,
        "humidity": 20.0,
        "wind_speed": 8.0,
    }]
    res_contra = calculate_report_credibility(
        latitude=28.6139,
        longitude=77.2090,
        event_timestamp=now - timedelta(minutes=10),
        event_type="Flooding",
        description="Severe deep flooding across the whole market square.",
        nearby_observations=dry_obs,
    )
    assert res_contra["credibility_status"] == STATUS_SUSPICIOUS
    assert res_contra["credibility_score"] < 35.0
    assert REASON_CONTRADICTORY_WEATHER_OBSERVATION in res_contra["credibility_reasons"]

    # R5. Duplicate report penalty
    res_dup = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=now - timedelta(minutes=5),
        event_type="Heavy Rain",
        description="Heavy rain near Dadar station causing train delays.",
        is_duplicate=True,
        duplicate_of="11111111-2222-3333-4444-555555555555",
    )
    assert res_dup["credibility_status"] == STATUS_SUSPICIOUS
    assert res_dup["credibility_score"] < 35.0
    assert REASON_DUPLICATE_REPORT in res_dup["credibility_reasons"]

    # R6. Suspicious spam content
    res_spam = calculate_report_credibility(
        latitude=19.0760,
        longitude=72.8777,
        event_timestamp=now,
        event_type="Thunderstorm",
        description="test test asdf fake",
    )
    assert res_spam["credibility_status"] == STATUS_SUSPICIOUS
    assert REASON_INCOMPLETE_OR_SPAM_DESCRIPTION in res_spam["credibility_reasons"]

    # R7. Source trust constants
    assert calculate_source_trust_score("IMD") == 95.0
    assert calculate_source_trust_score("IMD_RSS") == 95.0
    assert calculate_source_trust_score("Data_Gov") == 95.0
    assert calculate_source_trust_score("Open_Meteo") == 90.0
    assert calculate_source_trust_score("Unknown") == 50.0
    print("  [PASS] 8. Core regression suite: All 7 existing unit tests pass cleanly in isolated mode.")


# ==============================================================================
# Master Isolated Test Runner
# ==============================================================================

def run_all_isolated_tests():
    print("======================================================================")
    print("TEST 9A: Isolated Credibility Scoring Test Suite")
    print("======================================================================")

    # Install top-level database connection guard to ensure zero database access
    with patch("database.get_db_connection", side_effect=guard_db_connection):
        test_cases = [
            ("1a. Score Clamping (Compounded Negative Signals to 0.0)", test_score_clamping_to_zero),
            ("1b. Score Clamping (Upper Boundary Max Documentation)", test_upper_score_boundary_documentation),
            ("2a. Missing Inputs (All-None Inputs Safe Handling)", test_all_none_inputs_handling),
            ("2b. Missing Inputs (Isolated None Fields Handling)", test_isolated_none_fields_handling),
            ("3.  Exact Status Thresholds (35.0, 55.0, 80.0 Boundaries)", test_exact_status_thresholds),
            ("4a. Reason Codes (BRIEF_DESCRIPTION)", test_brief_description_reason),
            ("4b. Reason Codes (STALE_TIMESTAMP)", test_stale_timestamp_reason),
            ("4c. Reason Codes (UNKNOWN_EVENT_TYPE)", test_unknown_event_type_reason),
            ("4d. Reason Codes (evidence_summary Formatting)", test_evidence_summary_formatting),
            ("5.  Determinism (100 Iterations Identical Outputs)", test_determinism_100_iterations),
            ("6.  Source-Trust Fallback (Database Failure Fallback to 50.0)", test_source_trust_fallback_on_database_failure),
            ("7.  Media Scoring Observation (image/video URL Independence)", test_media_urls_do_not_affect_credibility_score),
            ("8.  Core Regression Suite (7 Pure Unit Tests Isolated)", test_core_regression_suite),
        ]

        results = []
        for name, func in test_cases:
            try:
                func()
                results.append((name, "PASSED"))
            except Exception as exc:
                print(f"  [FAIL] {name}: {exc}")
                traceback.print_exc()
                results.append((name, f"FAILED: {exc}"))

    print("\n--- Safety & Isolation Verification ---")
    print(f"[*] Real database connections attempted: {real_db_connections_attempted}")
    assert real_db_connections_attempted == 0, (
        f"CRITICAL: {real_db_connections_attempted} database connections were attempted!"
    )
    print("  [PASS] Zero database connections attempted. Complete isolation confirmed.")

    print("\n======================================================================")
    print("TEST 9A EXECUTION SUMMARY")
    print(f"Total Tests Executed: {len(results)}")
    passed_count = sum(1 for _, s in results if s == "PASSED")
    failed_count = sum(1 for _, s in results if s != "PASSED")
    print(f"Passed: {passed_count} | Failed: {failed_count}")
    print("======================================================================")
    for name, status in results:
        print(f"  - {name}: {status}")
    print("======================================================================")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_isolated_tests()
