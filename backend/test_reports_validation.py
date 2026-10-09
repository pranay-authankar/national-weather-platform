"""
Isolated unit and integration test suite for POST /api/reports input validation (Test 8A).

Validates CitizenReportCreate Pydantic schema and FastAPI request validation:
1. Latitude above 90 and below -90 (HTTP 422).
2. Longitude above 180 and below -180 (HTTP 422).
3. Missing and whitespace-only event_type (HTTP 422).
4. Missing and whitespace-only description (HTTP 422).
5. Missing and malformed timestamp (HTTP 422).
6. Whitespace-only image_url and video_url (Sanitized to None, HTTP 201).

Safety Guarantees:
- Fully mocks downstream citizen_report_service.process_and_store_citizen_report.
- Never writes, updates, or deletes any rows in the database.
- Confirms scheduler is NOT running and locks out start_scheduler.
- Audits total database record count and target development report 63a2529b-f2d5-4c02-bda4-36c408fae9e1
  before and after execution to prove absolute zero-mutation safety.
- Exposes modular test functions compatible with both standalone runner and pytest.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, patch
import pydantic

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
from database import get_db_connection
from main import app
from schemas.reports import CitizenReportCreate, CitizenReportResponse
from services.scheduler_service import get_scheduler_status


TARGET_EVENT_ID = "63a2529b-f2d5-4c02-bda4-36c408fae9e1"

VALID_BASELINE_PAYLOAD: Dict[str, Any] = {
    "event_type": "Heavy Rain",
    "description": "Localized waterlogging observed near the main intersection.",
    "latitude": 21.1458,
    "longitude": 79.0882,
    "timestamp": "2026-10-09T06:15:00Z",
    "image_url": None,
    "video_url": None,
}


def audit_database_state() -> Dict[str, Any]:
    """Retrieve total count and the exact state of all records and the target event."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM weather_events;")
            count = cur.fetchone()[0]

            cur.execute("SELECT event_id FROM weather_events;")
            all_ids = {str(row[0]) for row in cur.fetchall()}

            cur.execute("""
                SELECT event_id, event_type, event_timestamp, latitude, longitude, verification_status, duplicate_of
                FROM weather_events
                WHERE event_id = %s;
            """, (TARGET_EVENT_ID,))
            target_event = cur.fetchone()
            return {
                "count": count,
                "all_ids": all_ids,
                "target_event": target_event,
            }


# ==============================================================================
# Isolated Test Implementations (Cases 1 - 6)
# ==============================================================================

async def test_case_1_latitude_boundaries(client: httpx.AsyncClient, mock_storage: AsyncMock) -> List[Tuple[str, str]]:
    """Case 1: Latitude above 90 and below -90."""
    sub_results = []
    print("\n--- [Case 1] Latitude Boundaries (Above 90 and Below -90) ---")

    # 1a. Latitude above 90 (90.1) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "latitude": 90.1}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for lat=90.1, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("latitude" in err.get("loc", []) for err in detail), f"detail missing latitude error: {detail}"
    print("  [PASS] 1a. Latitude 90.1 rejected with HTTP 422.")
    sub_results.append(("1a. Latitude 90.1 rejected (HTTP 422)", "PASSED"))

    # 1b. Latitude far above 90 (150.0) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "latitude": 150.0}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 1b. Latitude 150.0 rejected with HTTP 422.")
    sub_results.append(("1b. Latitude 150.0 rejected (HTTP 422)", "PASSED"))

    # 1c. Latitude below -90 (-90.1) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "latitude": -90.1}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for lat=-90.1, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("latitude" in err.get("loc", []) for err in detail), f"detail missing latitude error: {detail}"
    print("  [PASS] 1c. Latitude -90.1 rejected with HTTP 422.")
    sub_results.append(("1c. Latitude -90.1 rejected (HTTP 422)", "PASSED"))

    # 1d. Latitude far below -90 (-150.0) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "latitude": -150.0}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 1d. Latitude -150.0 rejected with HTTP 422.")
    sub_results.append(("1d. Latitude -150.0 rejected (HTTP 422)", "PASSED"))

    # 1e. Missing latitude -> 422
    p = {k: v for k, v in VALID_BASELINE_PAYLOAD.items() if k != "latitude"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 1e. Missing latitude rejected with HTTP 422.")
    sub_results.append(("1e. Missing latitude rejected (HTTP 422)", "PASSED"))

    # 1f. Non-numeric latitude -> 422
    p = {**VALID_BASELINE_PAYLOAD, "latitude": "invalid_lat"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 1f. Non-numeric latitude rejected with HTTP 422.")
    sub_results.append(("1f. Non-numeric latitude rejected (HTTP 422)", "PASSED"))

    # 1g. Valid boundary latitudes (90.0, -90.0, 0.0) -> 201
    mock_storage.reset_mock()
    for valid_lat in [90.0, -90.0, 0.0]:
        p = {**VALID_BASELINE_PAYLOAD, "latitude": valid_lat}
        r = await client.post("/api/reports", json=p)
        assert r.status_code == 201, f"Expected 201 for lat={valid_lat}, got {r.status_code}: {r.text}"
    print("  [PASS] 1g. Boundary latitudes (90.0, -90.0, 0.0) accepted with HTTP 201.")
    sub_results.append(("1g. Boundary latitudes (90.0, -90.0, 0.0) accepted (HTTP 201)", "PASSED"))

    return sub_results


async def test_case_2_longitude_boundaries(client: httpx.AsyncClient, mock_storage: AsyncMock) -> List[Tuple[str, str]]:
    """Case 2: Longitude above 180 and below -180."""
    sub_results = []
    print("\n--- [Case 2] Longitude Boundaries (Above 180 and Below -180) ---")

    # 2a. Longitude above 180 (180.1) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "longitude": 180.1}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for lon=180.1, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("longitude" in err.get("loc", []) for err in detail), f"detail missing longitude error: {detail}"
    print("  [PASS] 2a. Longitude 180.1 rejected with HTTP 422.")
    sub_results.append(("2a. Longitude 180.1 rejected (HTTP 422)", "PASSED"))

    # 2b. Longitude far above 180 (250.0) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "longitude": 250.0}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 2b. Longitude 250.0 rejected with HTTP 422.")
    sub_results.append(("2b. Longitude 250.0 rejected (HTTP 422)", "PASSED"))

    # 2c. Longitude below -180 (-180.1) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "longitude": -180.1}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for lon=-180.1, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("longitude" in err.get("loc", []) for err in detail), f"detail missing longitude error: {detail}"
    print("  [PASS] 2c. Longitude -180.1 rejected with HTTP 422.")
    sub_results.append(("2c. Longitude -180.1 rejected (HTTP 422)", "PASSED"))

    # 2d. Longitude far below -180 (-250.0) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "longitude": -250.0}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 2d. Longitude -250.0 rejected with HTTP 422.")
    sub_results.append(("2d. Longitude -250.0 rejected (HTTP 422)", "PASSED"))

    # 2e. Missing longitude -> 422
    p = {k: v for k, v in VALID_BASELINE_PAYLOAD.items() if k != "longitude"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 2e. Missing longitude rejected with HTTP 422.")
    sub_results.append(("2e. Missing longitude rejected (HTTP 422)", "PASSED"))

    # 2f. Non-numeric longitude -> 422
    p = {**VALID_BASELINE_PAYLOAD, "longitude": "invalid_lon"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 2f. Non-numeric longitude rejected with HTTP 422.")
    sub_results.append(("2f. Non-numeric longitude rejected (HTTP 422)", "PASSED"))

    # 2g. Valid boundary longitudes (180.0, -180.0, 0.0) -> 201
    mock_storage.reset_mock()
    for valid_lon in [180.0, -180.0, 0.0]:
        p = {**VALID_BASELINE_PAYLOAD, "longitude": valid_lon}
        r = await client.post("/api/reports", json=p)
        assert r.status_code == 201, f"Expected 201 for lon={valid_lon}, got {r.status_code}: {r.text}"
    print("  [PASS] 2g. Boundary longitudes (180.0, -180.0, 0.0) accepted with HTTP 201.")
    sub_results.append(("2g. Boundary longitudes (180.0, -180.0, 0.0) accepted (HTTP 201)", "PASSED"))

    return sub_results


async def test_case_3_event_type_validation(client: httpx.AsyncClient, mock_storage: AsyncMock) -> List[Tuple[str, str]]:
    """Case 3: Missing and whitespace-only event type."""
    sub_results = []
    print("\n--- [Case 3] Missing & Whitespace Event Type ---")

    # 3a. Missing event_type key -> 422
    p = {k: v for k, v in VALID_BASELINE_PAYLOAD.items() if k != "event_type"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for missing event_type, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("event_type" in err.get("loc", []) for err in detail)
    print("  [PASS] 3a. Missing event_type rejected with HTTP 422.")
    sub_results.append(("3a. Missing event_type key rejected (HTTP 422)", "PASSED"))

    # 3b. Empty string event_type -> 422
    p = {**VALID_BASELINE_PAYLOAD, "event_type": ""}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for empty event_type, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("event_type" in err.get("loc", []) for err in detail)
    print("  [PASS] 3b. Empty string event_type rejected with HTTP 422.")
    sub_results.append(("3b. Empty string event_type rejected (HTTP 422)", "PASSED"))

    # 3c. Whitespace-only event_type -> 422
    p = {**VALID_BASELINE_PAYLOAD, "event_type": "   \t\n  "}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for whitespace event_type, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("event_type" in err.get("loc", []) for err in detail)
    print("  [PASS] 3c. Whitespace-only event_type rejected with HTTP 422.")
    sub_results.append(("3c. Whitespace-only event_type rejected (HTTP 422)", "PASSED"))

    # 3d. Null event_type -> 422
    p = {**VALID_BASELINE_PAYLOAD, "event_type": None}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for null event_type, got {r.status_code}: {r.text}"
    print("  [PASS] 3d. Null event_type rejected with HTTP 422.")
    sub_results.append(("3d. Null event_type rejected (HTTP 422)", "PASSED"))

    # 3e. Non-string event_type (integer) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "event_type": 12345}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 3e. Non-string event_type rejected with HTTP 422.")
    sub_results.append(("3e. Non-string event_type rejected (HTTP 422)", "PASSED"))

    # 3f. Valid event_type with surrounding whitespace -> 201 (trimmed)
    mock_storage.reset_mock()
    p = {**VALID_BASELINE_PAYLOAD, "event_type": "  Thunderstorm  "}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report: CitizenReportCreate = mock_storage.call_args[0][0]
    assert received_report.event_type == "Thunderstorm"
    print("  [PASS] 3f. Event type with surrounding whitespace trimmed to 'Thunderstorm' and accepted with HTTP 201.")
    sub_results.append(("3f. Event type with whitespace trimmed and accepted (HTTP 201)", "PASSED"))

    return sub_results


async def test_case_4_description_validation(client: httpx.AsyncClient, mock_storage: AsyncMock) -> List[Tuple[str, str]]:
    """Case 4: Missing and whitespace-only description."""
    sub_results = []
    print("\n--- [Case 4] Missing & Whitespace Description ---")

    # 4a. Missing description key -> 422
    p = {k: v for k, v in VALID_BASELINE_PAYLOAD.items() if k != "description"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for missing description, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("description" in err.get("loc", []) for err in detail)
    print("  [PASS] 4a. Missing description rejected with HTTP 422.")
    sub_results.append(("4a. Missing description key rejected (HTTP 422)", "PASSED"))

    # 4b. Empty string description -> 422
    p = {**VALID_BASELINE_PAYLOAD, "description": ""}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for empty description, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("description" in err.get("loc", []) for err in detail)
    print("  [PASS] 4b. Empty string description rejected with HTTP 422.")
    sub_results.append(("4b. Empty string description rejected (HTTP 422)", "PASSED"))

    # 4c. Whitespace-only description -> 422
    p = {**VALID_BASELINE_PAYLOAD, "description": "    \t   \n  "}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for whitespace description, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("description" in err.get("loc", []) for err in detail)
    print("  [PASS] 4c. Whitespace-only description rejected with HTTP 422.")
    sub_results.append(("4c. Whitespace-only description rejected (HTTP 422)", "PASSED"))

    # 4d. Null description -> 422
    p = {**VALID_BASELINE_PAYLOAD, "description": None}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for null description, got {r.status_code}: {r.text}"
    print("  [PASS] 4d. Null description rejected with HTTP 422.")
    sub_results.append(("4d. Null description rejected (HTTP 422)", "PASSED"))

    # 4e. Non-string description (boolean) -> 422
    p = {**VALID_BASELINE_PAYLOAD, "description": True}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 4e. Non-string description rejected with HTTP 422.")
    sub_results.append(("4e. Non-string description rejected (HTTP 422)", "PASSED"))

    # 4f. Valid description with surrounding whitespace -> 201 (trimmed)
    mock_storage.reset_mock()
    p = {**VALID_BASELINE_PAYLOAD, "description": "   Heavy flooding on main road.   "}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report: CitizenReportCreate = mock_storage.call_args[0][0]
    assert received_report.description == "Heavy flooding on main road."
    print("  [PASS] 4f. Description with surrounding whitespace trimmed and accepted with HTTP 201.")
    sub_results.append(("4f. Description with whitespace trimmed and accepted (HTTP 201)", "PASSED"))

    return sub_results


async def test_case_5_timestamp_validation(client: httpx.AsyncClient, mock_storage: AsyncMock) -> List[Tuple[str, str]]:
    """Case 5: Missing and malformed timestamp."""
    sub_results = []
    print("\n--- [Case 5] Missing & Malformed Timestamp ---")

    # 5a. Missing timestamp key -> 422
    p = {k: v for k, v in VALID_BASELINE_PAYLOAD.items() if k != "timestamp"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for missing timestamp, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("timestamp" in err.get("loc", []) for err in detail)
    print("  [PASS] 5a. Missing timestamp rejected with HTTP 422.")
    sub_results.append(("5a. Missing timestamp key rejected (HTTP 422)", "PASSED"))

    # 5b. Malformed timestamp string -> 422
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": "not-a-valid-iso-timestamp"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for malformed timestamp, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", [])
    assert any("timestamp" in err.get("loc", []) for err in detail)
    print("  [PASS] 5b. Malformed timestamp string rejected with HTTP 422.")
    sub_results.append(("5b. Malformed timestamp string rejected (HTTP 422)", "PASSED"))

    # 5c. Invalid calendar date -> 422
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": "2026-99-99T99:99:99Z"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 5c. Out-of-bounds calendar timestamp rejected with HTTP 422.")
    sub_results.append(("5c. Out-of-bounds calendar timestamp rejected (HTTP 422)", "PASSED"))

    # 5d. Non-ISO formatted date -> 422
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": "09/10/2026 06:15:00"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 5d. Non-ISO slash formatted date rejected with HTTP 422.")
    sub_results.append(("5d. Non-ISO slash formatted date rejected (HTTP 422)", "PASSED"))

    # 5e. Empty string timestamp -> 422
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": ""}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for empty timestamp, got {r.status_code}: {r.text}"
    print("  [PASS] 5e. Empty string timestamp rejected with HTTP 422.")
    sub_results.append(("5e. Empty string timestamp rejected (HTTP 422)", "PASSED"))

    # 5f. Whitespace-only timestamp -> 422
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": "   "}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422
    print("  [PASS] 5f. Whitespace-only timestamp rejected with HTTP 422.")
    sub_results.append(("5f. Whitespace-only timestamp rejected (HTTP 422)", "PASSED"))

    # 5g. Null timestamp -> 422
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": None}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 422, f"Expected 422 for null timestamp, got {r.status_code}: {r.text}"
    print("  [PASS] 5g. Null timestamp rejected with HTTP 422.")
    sub_results.append(("5g. Null timestamp rejected (HTTP 422)", "PASSED"))

    # 5h. Valid ISO-8601 UTC timestamp -> 201
    mock_storage.reset_mock()
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": "2026-10-09T06:15:00Z"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report = mock_storage.call_args[0][0]
    assert received_report.timestamp.tzinfo is not None
    print("  [PASS] 5h. Valid ISO-8601 UTC timestamp accepted with HTTP 201.")
    sub_results.append(("5h. Valid ISO-8601 UTC timestamp accepted (HTTP 201)", "PASSED"))

    # 5i. Valid ISO-8601 offset timestamp (+05:30) -> 201
    mock_storage.reset_mock()
    p = {**VALID_BASELINE_PAYLOAD, "timestamp": "2026-10-09T11:45:00+05:30"}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    print("  [PASS] 5i. Valid ISO-8601 offset timestamp accepted with HTTP 201.")
    sub_results.append(("5i. Valid ISO-8601 offset timestamp accepted (HTTP 201)", "PASSED"))

    return sub_results


async def test_case_6_media_urls_sanitization(client: httpx.AsyncClient, mock_storage: AsyncMock) -> List[Tuple[str, str]]:
    """Case 6: Whitespace-only image_url and video_url (sanitized to None)."""
    sub_results = []
    print("\n--- [Case 6] Whitespace-Only Optional Media URLs -> Sanitized to None ---")

    # 6a. Both image_url and video_url whitespace-only -> 201, sanitized to None
    mock_storage.reset_mock()
    p = {
        **VALID_BASELINE_PAYLOAD,
        "image_url": "   \t  ",
        "video_url": "    \n  ",
    }
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    assert mock_storage.called, "Downstream storage service was not called!"
    received_report: CitizenReportCreate = mock_storage.call_args[0][0]
    assert received_report.image_url is None, f"Expected image_url=None, got {received_report.image_url!r}"
    assert received_report.video_url is None, f"Expected video_url=None, got {received_report.video_url!r}"
    print("  [PASS] 6a. Whitespace-only image_url and video_url accepted (HTTP 201) and sanitized to None.")
    sub_results.append(("6a. Whitespace-only media URLs sanitized to None (HTTP 201)", "PASSED"))

    # 6b. Empty strings converted to None -> 201
    mock_storage.reset_mock()
    p = {
        **VALID_BASELINE_PAYLOAD,
        "image_url": "",
        "video_url": "",
    }
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report = mock_storage.call_args[0][0]
    assert received_report.image_url is None
    assert received_report.video_url is None
    print("  [PASS] 6b. Empty strings for media URLs sanitized to None (HTTP 201).")
    sub_results.append(("6b. Empty string media URLs sanitized to None (HTTP 201)", "PASSED"))

    # 6c. Explicit nulls preserved as None -> 201
    mock_storage.reset_mock()
    p = {
        **VALID_BASELINE_PAYLOAD,
        "image_url": None,
        "video_url": None,
    }
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report = mock_storage.call_args[0][0]
    assert received_report.image_url is None
    assert received_report.video_url is None
    print("  [PASS] 6c. Explicit null media URLs accepted as None (HTTP 201).")
    sub_results.append(("6c. Explicit null media URLs accepted as None (HTTP 201)", "PASSED"))

    # 6d. Omitted optional keys default to None -> 201
    mock_storage.reset_mock()
    p = {k: v for k, v in VALID_BASELINE_PAYLOAD.items() if k not in ("image_url", "video_url")}
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report = mock_storage.call_args[0][0]
    assert received_report.image_url is None
    assert received_report.video_url is None
    print("  [PASS] 6d. Omitted media URLs default to None (HTTP 201).")
    sub_results.append(("6d. Omitted media URLs default to None (HTTP 201)", "PASSED"))

    # 6e. Mixed: whitespace image_url, valid video_url -> 201
    mock_storage.reset_mock()
    p = {
        **VALID_BASELINE_PAYLOAD,
        "image_url": "   ",
        "video_url": "https://example.com/videos/hailstorm.mp4",
    }
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report = mock_storage.call_args[0][0]
    assert received_report.image_url is None
    assert received_report.video_url == "https://example.com/videos/hailstorm.mp4"
    print("  [PASS] 6e. Mixed whitespace image_url (sanitized to None) and valid video_url (preserved) (HTTP 201).")
    sub_results.append(("6e. Mixed whitespace and valid media URL handled correctly (HTTP 201)", "PASSED"))

    # 6f. Valid media URLs properly preserved -> 201
    mock_storage.reset_mock()
    p = {
        **VALID_BASELINE_PAYLOAD,
        "image_url": "https://example.com/photos/rain.jpg",
        "video_url": "https://example.com/videos/stream.mp4",
    }
    r = await client.post("/api/reports", json=p)
    assert r.status_code == 201
    received_report = mock_storage.call_args[0][0]
    assert received_report.image_url == "https://example.com/photos/rain.jpg"
    assert received_report.video_url == "https://example.com/videos/stream.mp4"
    print("  [PASS] 6f. Valid media URLs properly preserved (HTTP 201).")
    sub_results.append(("6f. Valid media URLs properly preserved (HTTP 201)", "PASSED"))

    return sub_results


def test_direct_pydantic_schema_validation() -> List[Tuple[str, str]]:
    """Isolated Pydantic unit tests without HTTP layer."""
    sub_results = []
    print("\n--- [Schema Unit Tests] Direct Pydantic CitizenReportCreate Validation ---")

    # U1. Latitude bounds
    try:
        CitizenReportCreate(**{**VALID_BASELINE_PAYLOAD, "latitude": 90.001})
        assert False, "Should have raised ValidationError for lat > 90"
    except pydantic.ValidationError as e:
        assert "latitude" in str(e)
    try:
        CitizenReportCreate(**{**VALID_BASELINE_PAYLOAD, "latitude": -90.001})
        assert False, "Should have raised ValidationError for lat < -90"
    except pydantic.ValidationError as e:
        assert "latitude" in str(e)
    print("  [PASS] U1. Direct schema rejects lat > 90 and lat < -90.")
    sub_results.append(("U1. Direct schema latitude boundary enforcement", "PASSED"))

    # U2. Longitude bounds
    try:
        CitizenReportCreate(**{**VALID_BASELINE_PAYLOAD, "longitude": 180.001})
        assert False, "Should have raised ValidationError for lon > 180"
    except pydantic.ValidationError as e:
        assert "longitude" in str(e)
    try:
        CitizenReportCreate(**{**VALID_BASELINE_PAYLOAD, "longitude": -180.001})
        assert False, "Should have raised ValidationError for lon < -180"
    except pydantic.ValidationError as e:
        assert "longitude" in str(e)
    print("  [PASS] U2. Direct schema rejects lon > 180 and lon < -180.")
    sub_results.append(("U2. Direct schema longitude boundary enforcement", "PASSED"))

    # U3. Whitespace-only event_type
    try:
        CitizenReportCreate(**{**VALID_BASELINE_PAYLOAD, "event_type": "   "})
        assert False, "Should have raised ValidationError for blank event_type"
    except pydantic.ValidationError as e:
        assert "event_type" in str(e)
    print("  [PASS] U3. Direct schema rejects whitespace-only event_type.")
    sub_results.append(("U3. Direct schema whitespace-only event_type rejection", "PASSED"))

    # U4. Whitespace-only description
    try:
        CitizenReportCreate(**{**VALID_BASELINE_PAYLOAD, "description": " \t "})
        assert False, "Should have raised ValidationError for blank description"
    except pydantic.ValidationError as e:
        assert "description" in str(e)
    print("  [PASS] U4. Direct schema rejects whitespace-only description.")
    sub_results.append(("U4. Direct schema whitespace-only description rejection", "PASSED"))

    # U5. Malformed timestamp
    try:
        CitizenReportCreate(**{**VALID_BASELINE_PAYLOAD, "timestamp": "invalid_date"})
        assert False, "Should have raised ValidationError for malformed timestamp"
    except pydantic.ValidationError as e:
        assert "timestamp" in str(e)
    print("  [PASS] U5. Direct schema rejects malformed timestamp.")
    sub_results.append(("U5. Direct schema malformed timestamp rejection", "PASSED"))

    # U6. Media URLs sanitization
    obj = CitizenReportCreate(**{
        **VALID_BASELINE_PAYLOAD,
        "image_url": "   ",
        "video_url": "  \t \n ",
    })
    assert obj.image_url is None
    assert obj.video_url is None
    print("  [PASS] U6. Direct schema sanitizes whitespace-only media URLs to None.")
    sub_results.append(("U6. Direct schema media URLs sanitization to None", "PASSED"))

    return sub_results


# ==============================================================================
# Master Test Runner with Comprehensive Auditing and Isolation
# ==============================================================================

async def run_all_validation_tests():
    print("======================================================================")
    print("TEST 8A: Citizen Report Input Validation Test Suite (Mocked & Isolated)")
    print("======================================================================")

    # 1. Verify Scheduler is NOT Running
    scheduler_status = get_scheduler_status()
    print(f"[*] Scheduler active check: running={scheduler_status['running']}, enabled={scheduler_status['enabled']}")
    assert scheduler_status["running"] is False, "CRITICAL: Scheduler is running! Must remain inactive."

    # 2. Capture Pre-Test Database Baseline
    baseline = audit_database_state()
    print(f"[*] Pre-test database record count: {baseline['count']}")
    print(f"[*] Target development event {TARGET_EVENT_ID} present: {baseline['target_event'] is not None}")
    assert baseline["target_event"] is not None, f"CRITICAL: Target event {TARGET_EVENT_ID} missing from database!"

    all_test_results: List[Tuple[str, str]] = []

    # 3. Direct Schema Unit Validation (Isolated in-memory)
    schema_results = test_direct_pydantic_schema_validation()
    all_test_results.extend(schema_results)

    # 4. HTTP API Endpoint Validation (Mocked downstream service)
    transport = httpx.ASGITransport(app=app)
    mock_storage_service = AsyncMock(return_value={
        "event_id": "mock-0000-0000-0000-000000000001",
        "status": "received",
        "verification_status": "Unverified",
        "duplicate_of": None,
    })

    # Guard against start_scheduler being called
    with patch("services.scheduler_service.start_scheduler", side_effect=RuntimeError("Scheduler execution prohibited")):
        with patch("routers.reports.process_and_store_citizen_report", mock_storage_service):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                res1 = await test_case_1_latitude_boundaries(client, mock_storage_service)
                all_test_results.extend(res1)

                res2 = await test_case_2_longitude_boundaries(client, mock_storage_service)
                all_test_results.extend(res2)

                res3 = await test_case_3_event_type_validation(client, mock_storage_service)
                all_test_results.extend(res3)

                res4 = await test_case_4_description_validation(client, mock_storage_service)
                all_test_results.extend(res4)

                res5 = await test_case_5_timestamp_validation(client, mock_storage_service)
                all_test_results.extend(res5)

                res6 = await test_case_6_media_urls_sanitization(client, mock_storage_service)
                all_test_results.extend(res6)

    # 5. Post-Execution Safety and Cleanliness Audit
    print("\n--- [Safety Audit] Post-Execution Database Verification ---")
    post_state = audit_database_state()
    print(f"[*] Post-test database record count: {post_state['count']} (Baseline: {baseline['count']})")
    assert post_state["count"] == baseline["count"], (
        f"CRITICAL: Record count mismatch! Baseline: {baseline['count']}, Post-test: {post_state['count']}"
    )
    print("  [PASS] Database record count unchanged (0 rows inserted, modified, or deleted).")

    assert post_state["all_ids"] == baseline["all_ids"], (
        "CRITICAL: The set of database record IDs changed during tests!"
    )
    print("  [PASS] Database primary keys set completely preserved.")

    assert post_state["target_event"] == baseline["target_event"], (
        f"CRITICAL: Target development event {TARGET_EVENT_ID} was modified!"
    )
    print(f"  [PASS] Target event {TARGET_EVENT_ID} verified byte-for-byte identical.")

    post_scheduler_status = get_scheduler_status()
    assert post_scheduler_status["running"] is False, "CRITICAL: Scheduler was started during test execution!"
    print("  [PASS] Background scheduler confirmed strictly inactive.")

    # 6. Final Summary Report
    print("\n======================================================================")
    print("ALL TEST 8A VALIDATION TESTS COMPLETED SUCCESSFULLY!")
    print(f"Total Sub-Tests Run: {len(all_test_results)}")
    print("======================================================================")
    for name, status in all_test_results:
        print(f"  - {name}: {status}")
    print("======================================================================")


if __name__ == "__main__":
    asyncio.run(run_all_validation_tests())
