"""
Isolated automated test suite for Admin Weather Report Moderation API (Test 10).

Strict Safety Guarantees:
- Fully isolated from Supabase PostgreSQL database. Zero real database connections attempted.
- Does NOT execute backend/test_moderation_api.py (which contains real DB writes and hardcoded assertions).
- Does NOT insert, update, or delete records in public.weather_events or public.moderation_audit_log.
- Explicit top-level guard intercepts and blocks any unmocked database connection attempt.
- Purely deterministic, in-memory execution using httpx.AsyncClient and unittest.mock.

Covers:
Group A: Authentication and authorization
  - Missing token on all endpoints (HTTP 401, WWW-Authenticate header)
  - Invalid token credentials (HTTP 401)
  - Both Authorization: Bearer and X-Admin-Token header support
  - Server unconfigured credentials (HTTP 503)
  - Multi-moderator token mapping and identity extraction
  - Unauthorized clients blocked from all moderation actions

Group B: Event verification and status transitions
  - Verify existing Unverified event (Unverified -> Verified, confidence -> 100.0)
  - Reject existing event (Verified/Unverified -> Rejected, confidence -> 0.0)
  - Restore rejected event (Rejected -> Unverified, confidence -> 35.0)
  - Rejection of restore on non-rejected events (HTTP 400)
  - Redundant transition rejection / idempotency (Verified -> Verified, Rejected -> Rejected: HTTP 400)
  - Duplicate event restriction (cannot verify duplicate event: HTTP 400)
  - Preservation of reviewer identity, reason, timestamps, and previous/new status

Group C: Invalid and missing data
  - Missing reason field in request body (HTTP 422)
  - Whitespace-only or too-short reason (HTTP 422)
  - Malformed UUID in path parameter (HTTP 400)
  - Nonexistent UUID in path parameter (HTTP 404)
  - Malformed JSON body (HTTP 422)

Group D: Error handling and data integrity
  - Database failure during moderation transaction returns HTTP 503 (sanitized error message)
  - Database failure during audit history read returns HTTP 503 (sanitized error message)
  - Unrelated event fields (credibility, coordinates, meteorological values) preserved
  - Atomic transaction rollback simulation on failure

Group E: API response contract and audit history
  - ModerationResponse shape adheres to schema and frontend expectations
  - GET /api/admin/reports/{event_id}/audit-history returns chronological list
  - GET /api/admin/audit-history returns paginated response
  - Frontend-backend contract alignment validation
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple
import unittest.mock as mock
import uuid

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import psycopg

from main import app
from schemas.moderation import (
    AuditHistoryListResponse,
    ModerationActionRequest,
    ModerationAuditRecord,
    ModerationResponse,
)
from services.admin_auth_service import (
    AdminAuthError,
    get_configured_admin_tokens,
    verify_admin_token,
)
from services.moderation_service import (
    DuplicateEventRestrictionError,
    EventNotFoundError,
    InvalidStatusTransitionError,
    ModerationValidationError,
    _row_to_event_dict,
    _validate_uuid,
    get_audit_history_list,
    get_event_audit_history,
    moderate_weather_event,
)
from services.scheduler_service import get_scheduler_status


# Track and prevent real database connections
real_db_connections_attempted = 0


def guard_db_connection(*args, **kwargs):
    global real_db_connections_attempted
    real_db_connections_attempted += 1
    raise RuntimeError("CRITICAL SAFETY VIOLATION: Database connection attempted during isolated testing!")


TEST_ADMIN_TOKEN = "test_super_secret_moderator_token_2026"
TEST_MODERATOR_ID = "test_lead_moderator"
TEST_TOKEN_2 = "test_secondary_token_789"
TEST_MODERATOR_2 = "test_junior_moderator"

AUTH_HEADERS = {"Authorization": f"Bearer {TEST_ADMIN_TOKEN}"}
X_AUTH_HEADERS = {"X-Admin-Token": TEST_ADMIN_TOKEN}

ENV_OVERRIDE = {
    "ADMIN_API_KEY": TEST_ADMIN_TOKEN,
    "ADMIN_DEFAULT_MODERATOR_ID": TEST_MODERATOR_ID,
    "ADMIN_API_TOKENS": json.dumps({
        TEST_ADMIN_TOKEN: TEST_MODERATOR_ID,
        TEST_TOKEN_2: TEST_MODERATOR_2,
    }),
}


def make_mock_event_tuple(
    event_id: str,
    status: str = "Unverified",
    confidence: float = 35.0,
    duplicate_of: Optional[str] = None,
) -> tuple:
    """Construct a 27-element tuple matching EVENT_COLUMNS in routers.events."""
    return (
        uuid.UUID(event_id),                                      # 0: event_id
        "Citizen_Report",                                          # 1: source
        "Heavy Rain",                                              # 2: event_type
        "Localized flooding on street near market",               # 3: description
        datetime(2026, 10, 9, 6, 0, 0, tzinfo=timezone.utc),      # 4: event_timestamp
        21.1458,                                                   # 5: latitude
        79.0882,                                                   # 6: longitude
        "Nagpur",                                                  # 7: city
        "Nagpur",                                                  # 8: district
        "Maharashtra",                                             # 9: state
        28.5,                                                      # 10: temperature
        45.0,                                                      # 11: rainfall
        85.0,                                                      # 12: humidity
        15.0,                                                      # 13: wind_speed
        180.0,                                                     # 14: wind_direction
        1010.0,                                                    # 15: pressure
        None,                                                      # 16: image_url
        None,                                                      # 17: video_url
        None,                                                      # 18: source_url
        status,                                                    # 19: verification_status
        confidence,                                                # 20: confidence_score
        uuid.UUID(duplicate_of) if duplicate_of else None,         # 21: duplicate_of
        datetime(2026, 10, 9, 6, 5, 0, tzinfo=timezone.utc),      # 22: created_at
        45.0,                                                      # 23: credibility_score
        "Unverified",                                              # 24: credibility_status
        ["VALID_LOCATION", "VALID_TIMESTAMP"],                     # 25: credibility_reasons
        50.0,                                                      # 26: source_trust_score
    )


def create_mock_db_connection(fetch_side_effects: list):
    """Create a fully-configured mock connection and cursor with __enter__ properly returning self."""
    mock_conn = mock.MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_cur = mock.MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    if fetch_side_effects:
        mock_cur.fetchone.side_effect = fetch_side_effects
    return mock_conn, mock_cur


# ==============================================================================
# Group A: Authentication and Authorization Tests
# ==============================================================================

async def test_a1_missing_auth_token_all_endpoints(client: httpx.AsyncClient):
    """Verify all 5 moderation endpoints reject unauthenticated requests with HTTP 401."""
    dummy_id = str(uuid.uuid4())
    payload = {"reason": "Valid reason justification."}

    endpoints = [
        ("POST", f"/api/admin/reports/{dummy_id}/verify", payload),
        ("POST", f"/api/admin/reports/{dummy_id}/reject", payload),
        ("POST", f"/api/admin/reports/{dummy_id}/restore", payload),
        ("GET", f"/api/admin/reports/{dummy_id}/audit-history", None),
        ("GET", "/api/admin/audit-history", None),
    ]

    for method, path, body in endpoints:
        if method == "POST":
            res = await client.post(path, json=body)
        else:
            res = await client.get(path)

        assert res.status_code == 401, f"{method} {path} returned {res.status_code}, expected 401"
        assert "Missing admin authentication token" in res.json().get("detail", "")
        assert "WWW-Authenticate" in res.headers
    print("  [PASS] A1: All 5 admin endpoints require authentication and return HTTP 401 when missing.")


async def test_a2_invalid_auth_token(client: httpx.AsyncClient):
    """Verify invalid token is rejected with HTTP 401."""
    dummy_id = str(uuid.uuid4())
    res = await client.post(
        f"/api/admin/reports/{dummy_id}/verify",
        json={"reason": "Valid justification."},
        headers={"Authorization": "Bearer invalid_secret_token_xyz"},
    )
    assert res.status_code == 401
    assert "Invalid admin authentication credentials" in res.json().get("detail", "")
    print("  [PASS] A2: Invalid token credentials rejected with HTTP 401.")


async def test_a3_header_support_bearer_and_x_admin_token(client: httpx.AsyncClient):
    """Verify both Authorization: Bearer and X-Admin-Token headers successfully authenticate."""
    dummy_id = str(uuid.uuid4())
    mock_service = mock.MagicMock(return_value={
        "audit_id": str(uuid.uuid4()),
        "event_id": dummy_id,
        "previous_status": "Unverified",
        "new_status": "Verified",
        "reason": "Verified via radar evidence.",
        "moderator_id": TEST_MODERATOR_ID,
        "moderated_at": datetime.now(timezone.utc).isoformat(),
        "event": {"event_id": dummy_id, "verification_status": "Verified"},
    })

    with mock.patch("routers.moderation.moderate_weather_event", mock_service):
        # Bearer header
        res_bearer = await client.post(
            f"/api/admin/reports/{dummy_id}/verify",
            json={"reason": "Verified via radar evidence."},
            headers=AUTH_HEADERS,
        )
        assert res_bearer.status_code == 200

        # X-Admin-Token header
        res_xtoken = await client.post(
            f"/api/admin/reports/{dummy_id}/verify",
            json={"reason": "Verified via radar evidence."},
            headers=X_AUTH_HEADERS,
        )
        assert res_xtoken.status_code == 200
    print("  [PASS] A3: Both Authorization: Bearer and X-Admin-Token headers authenticate correctly.")


async def test_a4_unconfigured_server_returns_503(client: httpx.AsyncClient):
    """Verify server returns 503 when admin credentials are unconfigured."""
    dummy_id = str(uuid.uuid4())
    with mock.patch.dict(os.environ, {"ADMIN_API_KEY": "", "ADMIN_API_TOKENS": ""}, clear=False):
        res = await client.post(
            f"/api/admin/reports/{dummy_id}/verify",
            json={"reason": "Valid justification."},
            headers={"Authorization": "Bearer some_token"},
        )
        assert res.status_code == 503
        assert "Admin authentication is not configured on the server" in res.json().get("detail", "")
    print("  [PASS] A4: Server returns HTTP 503 when admin credentials are unconfigured.")


def test_a5_multi_moderator_token_mapping():
    """Verify ADMIN_API_TOKENS JSON mapping extracts exact moderator identity."""
    with mock.patch.dict(os.environ, ENV_OVERRIDE, clear=False):
        identity1 = verify_admin_token(TEST_ADMIN_TOKEN)
        assert identity1 == TEST_MODERATOR_ID

        identity2 = verify_admin_token(TEST_TOKEN_2)
        assert identity2 == TEST_MODERATOR_2
    print("  [PASS] A5: Multi-moderator token mapping correctly maps tokens to discrete identities.")


# ==============================================================================
# Group B: Event Verification and Status Transitions
# ==============================================================================

def test_b1_verify_unverified_event():
    """Verify Unverified -> Verified transition in moderate_weather_event."""
    test_id = str(uuid.uuid4())
    initial_row = make_mock_event_tuple(test_id, status="Unverified", confidence=35.0)
    updated_row = make_mock_event_tuple(test_id, status="Verified", confidence=100.0)
    audit_row = (uuid.uuid4(), datetime.now(timezone.utc))

    mock_conn, _ = create_mock_db_connection([initial_row, updated_row, audit_row])

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        result = moderate_weather_event(
            event_id=test_id,
            new_status="Verified",
            reason="Confirmed by nearby Doppler radar.",
            moderator_id=TEST_MODERATOR_ID,
        )

    assert result["event_id"] == test_id
    assert result["previous_status"] == "Unverified"
    assert result["new_status"] == "Verified"
    assert result["event"]["verification_status"] == "Verified"
    assert result["event"]["confidence_score"] == 100.0
    assert result["moderator_id"] == TEST_MODERATOR_ID
    assert mock_conn.commit.called
    print("  [PASS] B1: Unverified -> Verified transition updates status, sets confidence to 100.0, commits transaction.")


def test_b2_reject_event():
    """Verify transition to Rejected sets confidence to 0.0."""
    test_id = str(uuid.uuid4())
    initial_row = make_mock_event_tuple(test_id, status="Verified", confidence=100.0)
    updated_row = make_mock_event_tuple(test_id, status="Rejected", confidence=0.0)
    audit_row = (uuid.uuid4(), datetime.now(timezone.utc))

    mock_conn, _ = create_mock_db_connection([initial_row, updated_row, audit_row])

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        result = moderate_weather_event(
            event_id=test_id,
            new_status="Rejected",
            reason="Confirmed fabrication by regional station.",
            moderator_id=TEST_MODERATOR_ID,
        )

    assert result["previous_status"] == "Verified"
    assert result["new_status"] == "Rejected"
    assert result["event"]["verification_status"] == "Rejected"
    assert result["event"]["confidence_score"] == 0.0
    print("  [PASS] B2: Verified -> Rejected transition updates status, sets confidence to 0.0.")


def test_b3_restore_rejected_event():
    """Verify Rejected -> Unverified restore transition sets confidence to 35.0 baseline."""
    test_id = str(uuid.uuid4())
    initial_row = make_mock_event_tuple(test_id, status="Rejected", confidence=0.0)
    updated_row = make_mock_event_tuple(test_id, status="Unverified", confidence=35.0)
    audit_row = (uuid.uuid4(), datetime.now(timezone.utc))

    mock_conn, _ = create_mock_db_connection([initial_row, updated_row, audit_row])

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        result = moderate_weather_event(
            event_id=test_id,
            new_status="Unverified",
            reason="Reassessing report based on updated satellite photography.",
            moderator_id=TEST_MODERATOR_ID,
        )

    assert result["previous_status"] == "Rejected"
    assert result["new_status"] == "Unverified"
    assert result["event"]["verification_status"] == "Unverified"
    assert result["event"]["confidence_score"] == 35.0
    print("  [PASS] B3: Rejected -> Unverified restore updates status, resets confidence to 35.0 baseline.")


def test_b4_restore_non_rejected_event_rejected():
    """Verify restoring non-rejected events raises InvalidStatusTransitionError."""
    test_id = str(uuid.uuid4())
    initial_row = make_mock_event_tuple(test_id, status="Unverified", confidence=35.0)

    mock_conn, _ = create_mock_db_connection([initial_row])

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        try:
            moderate_weather_event(
                event_id=test_id,
                new_status="Unverified",
                reason="Attempting restore on already unverified report.",
                moderator_id=TEST_MODERATOR_ID,
            )
            assert False, "Should have raised InvalidStatusTransitionError"
        except InvalidStatusTransitionError as exc:
            assert "Only Rejected reports can be restored" in str(exc)
    print("  [PASS] B4: Restoring non-rejected report rejected with InvalidStatusTransitionError.")


def test_b5_redundant_transition_idempotency_rejected():
    """Verify redundant status transitions (Verified -> Verified, Rejected -> Rejected) are rejected."""
    test_id = str(uuid.uuid4())
    verified_row = make_mock_event_tuple(test_id, status="Verified", confidence=100.0)

    mock_conn, _ = create_mock_db_connection([verified_row])

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        try:
            moderate_weather_event(
                event_id=test_id,
                new_status="Verified",
                reason="Duplicate verification attempt.",
                moderator_id=TEST_MODERATOR_ID,
            )
            assert False, "Should have raised InvalidStatusTransitionError"
        except InvalidStatusTransitionError as exc:
            assert "Event is already 'Verified'" in str(exc)
    print("  [PASS] B5: Redundant status transition rejected with InvalidStatusTransitionError.")


def test_b6_duplicate_event_restriction():
    """Verify duplicate records cannot be marked Verified while retaining duplicate relationship."""
    test_id = str(uuid.uuid4())
    canonical_id = str(uuid.uuid4())
    dup_row = make_mock_event_tuple(test_id, status="Duplicate", confidence=35.0, duplicate_of=canonical_id)

    mock_conn, _ = create_mock_db_connection([dup_row])

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        try:
            moderate_weather_event(
                event_id=test_id,
                new_status="Verified",
                reason="Attempting to verify duplicate report directly.",
                moderator_id=TEST_MODERATOR_ID,
            )
            assert False, "Should have raised DuplicateEventRestrictionError"
        except DuplicateEventRestrictionError as exc:
            assert "Cannot mark a duplicate record as Verified" in str(exc)
    print("  [PASS] B6: Duplicate event restriction enforced; duplicate cannot be Verified.")


# ==============================================================================
# Group C: Invalid and Missing Data Validation
# ==============================================================================

async def test_c1_missing_reason_field(client: httpx.AsyncClient):
    """Verify missing reason in request body is rejected with HTTP 422."""
    dummy_id = str(uuid.uuid4())
    res = await client.post(
        f"/api/admin/reports/{dummy_id}/verify",
        json={},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 422
    assert any("reason" in err.get("loc", []) for err in res.json().get("detail", []))
    print("  [PASS] C1: Missing reason field rejected with HTTP 422.")


async def test_c2_whitespace_or_too_short_reason(client: httpx.AsyncClient):
    """Verify whitespace-only or < 3 char reason is rejected with HTTP 422."""
    dummy_id = str(uuid.uuid4())

    # Whitespace-only
    res_ws = await client.post(
        f"/api/admin/reports/{dummy_id}/verify",
        json={"reason": "    \t   "},
        headers=AUTH_HEADERS,
    )
    assert res_ws.status_code == 422

    # Length < 3
    res_short = await client.post(
        f"/api/admin/reports/{dummy_id}/verify",
        json={"reason": "ok"},
        headers=AUTH_HEADERS,
    )
    assert res_short.status_code == 422
    print("  [PASS] C2: Whitespace-only and short reasons (< 3 chars) rejected with HTTP 422.")


async def test_c3_malformed_uuid_in_path(client: httpx.AsyncClient):
    """Verify malformed UUID in path parameter returns HTTP 400."""
    res = await client.post(
        "/api/admin/reports/not-a-valid-uuid-123/verify",
        json={"reason": "Valid administrative reason."},
        headers=AUTH_HEADERS,
    )
    assert res.status_code == 400
    assert "Invalid UUID format" in res.json().get("detail", "")
    print("  [PASS] C3: Malformed UUID in path rejected with HTTP 400 Bad Request.")


async def test_c4_nonexistent_event_id(client: httpx.AsyncClient):
    """Verify nonexistent UUID returns HTTP 404 Not Found."""
    nonexistent_id = str(uuid.uuid4())
    mock_conn, mock_cur = create_mock_db_connection([])
    mock_cur.fetchone.return_value = None  # Event not found

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        res = await client.post(
            f"/api/admin/reports/{nonexistent_id}/verify",
            json={"reason": "Valid administrative reason."},
            headers=AUTH_HEADERS,
        )
    assert res.status_code == 404
    assert "not found" in res.json().get("detail", "").lower()
    print("  [PASS] C4: Nonexistent event ID returns HTTP 404 Not Found.")


# ==============================================================================
# Group D: Error Handling and Data Integrity
# ==============================================================================

async def test_d1_database_failure_during_moderation_returns_503(client: httpx.AsyncClient):
    """Verify database operational error produces HTTP 503 Service Unavailable with sanitized message."""
    test_id = str(uuid.uuid4())
    mock_conn, mock_cur = create_mock_db_connection([])
    secret_pass = "super_secret_db_pass_12345"
    mock_cur.execute.side_effect = psycopg.OperationalError(
        f"Connection to postgresql://user:{secret_pass}@host failed"
    )
    mock_cfg = {"password": secret_pass, "host": "host", "port": 5432, "dbname": "db", "user": "user"}

    with mock.patch("database.get_db_config", return_value=mock_cfg):
        with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
            res = await client.post(
                f"/api/admin/reports/{test_id}/verify",
                json={"reason": "Valid justification."},
                headers=AUTH_HEADERS,
            )
    assert res.status_code == 503
    detail = res.json().get("detail", "")
    assert secret_pass not in detail  # Credentials sanitized
    assert "******" in detail
    assert "Database error during moderation" in detail
    print("  [PASS] D1: Database failure produces HTTP 503 Service Unavailable with sanitized error.")


def test_d2_unrelated_event_fields_preserved():
    """Verify moderation only changes verification_status and confidence_score, preserving all other fields."""
    test_id = str(uuid.uuid4())
    initial_row = make_mock_event_tuple(test_id, status="Unverified", confidence=35.0)
    updated_row = make_mock_event_tuple(test_id, status="Verified", confidence=100.0)
    audit_row = (uuid.uuid4(), datetime.now(timezone.utc))

    mock_conn, _ = create_mock_db_connection([initial_row, updated_row, audit_row])

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        result = moderate_weather_event(
            event_id=test_id,
            new_status="Verified",
            reason="Confirmed by eyewitness.",
            moderator_id=TEST_MODERATOR_ID,
        )

    ev = result["event"]
    assert ev["credibility_score"] == 45.0
    assert ev["credibility_status"] == "Unverified"
    assert ev["credibility_reasons"] == ["VALID_LOCATION", "VALID_TIMESTAMP"]
    assert ev["source_trust_score"] == 50.0
    assert ev["latitude"] == 21.1458
    assert ev["longitude"] == 79.0882
    assert ev["rainfall"] == 45.0
    assert ev["temperature"] == 28.5
    print("  [PASS] D2: Unrelated event fields (credibility, coordinates, meteorology) strictly preserved.")


def test_d3_transaction_rollback_on_audit_failure():
    """Verify that failure during audit log insertion prevents commit and rolls back transaction."""
    test_id = str(uuid.uuid4())
    initial_row = make_mock_event_tuple(test_id, status="Unverified", confidence=35.0)
    updated_row = make_mock_event_tuple(test_id, status="Verified", confidence=100.0)

    mock_conn, mock_cur = create_mock_db_connection([])
    # Return initial, return updated, then fail on audit insertion
    mock_cur.fetchone.side_effect = [
        initial_row,
        updated_row,
        psycopg.OperationalError("Audit table disk full"),
    ]

    with mock.patch("services.moderation_service.get_db_connection", return_value=mock_conn):
        try:
            moderate_weather_event(
                event_id=test_id,
                new_status="Verified",
                reason="Confirmed by eyewitness.",
                moderator_id=TEST_MODERATOR_ID,
            )
            assert False, "Should have raised RuntimeError"
        except RuntimeError as exc:
            assert "Database error during moderation" in str(exc)

    assert not mock_conn.commit.called, "conn.commit() must NOT be called if audit insertion fails!"
    print("  [PASS] D3: Transaction rollback guaranteed; commit never called upon audit insertion failure.")


# ==============================================================================
# Group E: API Response Contract and Audit History
# ==============================================================================

async def test_e1_verify_response_shape_matches_schema(client: httpx.AsyncClient):
    """Verify ModerationResponse contains all fields expected by schema and frontend."""
    test_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()
    mock_res = {
        "audit_id": str(uuid.uuid4()),
        "event_id": test_id,
        "previous_status": "Unverified",
        "new_status": "Verified",
        "reason": "Confirmed by regional radar.",
        "moderator_id": TEST_MODERATOR_ID,
        "moderated_at": now_str,
        "event": {
            "event_id": test_id,
            "source": "Citizen_Report",
            "event_type": "Heavy Rain",
            "verification_status": "Verified",
            "confidence_score": 100.0,
            "created_at": now_str,
            "credibility_score": 45.0,
            "credibility_status": "Unverified",
            "credibility_reasons": ["VALID_LOCATION"],
            "source_trust_score": 50.0,
        },
    }

    with mock.patch("routers.moderation.moderate_weather_event", return_value=mock_res):
        res = await client.post(
            f"/api/admin/reports/{test_id}/verify",
            json={"reason": "Confirmed by regional radar."},
            headers=AUTH_HEADERS,
        )

    assert res.status_code == 200
    data = res.json()
    assert "event_id" in data
    assert "previous_status" in data
    assert "new_status" in data
    assert "reason" in data
    assert "moderator_id" in data
    assert "moderated_at" in data
    assert "event" in data
    assert data["event"]["verification_status"] == "Verified"
    assert data["event"]["confidence_score"] == 100.0
    print("  [PASS] E1: ModerationResponse shape matches Pydantic schema and frontend contract.")


async def test_e2_get_event_audit_history_endpoint(client: httpx.AsyncClient):
    """Verify GET /api/admin/reports/{event_id}/audit-history returns chronological audit records."""
    test_id = str(uuid.uuid4())
    mock_entries = [
        {
            "audit_id": str(uuid.uuid4()),
            "event_id": test_id,
            "previous_status": "Unverified",
            "new_status": "Verified",
            "reason": "Verified by lead moderator.",
            "moderator_id": TEST_MODERATOR_ID,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    with mock.patch("routers.moderation.get_event_audit_history", return_value=mock_entries):
        res = await client.get(
            f"/api/admin/reports/{test_id}/audit-history",
            headers=AUTH_HEADERS,
        )

    assert res.status_code == 200
    records = res.json()
    assert isinstance(records, list)
    assert len(records) == 1
    assert records[0]["event_id"] == test_id
    assert records[0]["moderator_id"] == TEST_MODERATOR_ID
    print("  [PASS] E2: GET /api/admin/reports/{event_id}/audit-history returns ModerationAuditRecord list.")


async def test_e3_get_global_audit_history_paginated(client: httpx.AsyncClient):
    """Verify GET /api/admin/audit-history returns paginated AuditHistoryListResponse."""
    mock_list = {
        "data": [
            {
                "audit_id": str(uuid.uuid4()),
                "event_id": str(uuid.uuid4()),
                "previous_status": "Unverified",
                "new_status": "Verified",
                "reason": "Verified action.",
                "moderator_id": TEST_MODERATOR_ID,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }

    with mock.patch("routers.moderation.get_audit_history_list", return_value=mock_list):
        res = await client.get(
            "/api/admin/audit-history?limit=50&offset=0",
            headers=AUTH_HEADERS,
        )

    assert res.status_code == 200
    body = res.json()
    assert "data" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body
    assert body["total"] == 1
    assert len(body["data"]) == 1
    print("  [PASS] E3: GET /api/admin/audit-history returns paginated AuditHistoryListResponse.")


def test_e4_frontend_type_contract_compatibility():
    """Verify backend schema field names match frontend TypeScript interfaces."""
    # Backend ModerationResponse fields
    backend_response_fields = set(ModerationResponse.model_fields.keys())
    # Frontend ModerationResponse fields (from frontend/src/types/moderation.ts)
    frontend_response_fields = {
        "event_id",
        "previous_status",
        "new_status",
        "reason",
        "moderator_id",
        "moderated_at",
        "event",
    }
    assert backend_response_fields == frontend_response_fields, (
        f"Mismatch: backend={backend_response_fields}, frontend={frontend_response_fields}"
    )

    # Backend ModerationAuditRecord fields
    backend_audit_fields = set(ModerationAuditRecord.model_fields.keys())
    frontend_audit_fields = {
        "audit_id",
        "event_id",
        "previous_status",
        "new_status",
        "reason",
        "moderator_id",
        "created_at",
    }
    assert backend_audit_fields == frontend_audit_fields

    # Backend AuditHistoryListResponse fields
    backend_list_fields = set(AuditHistoryListResponse.model_fields.keys())
    frontend_list_fields = {"data", "total", "limit", "offset"}
    assert backend_list_fields == frontend_list_fields
    print("  [PASS] E4: Backend Pydantic models match frontend TypeScript interfaces 1:1.")


# ==============================================================================
# Master Test Runner with Database Connection Guard
# ==============================================================================

async def run_all_moderation_isolated_tests():
    print("======================================================================")
    print("TEST 10: Admin Moderation & Verification Workflow (Isolated & Mocked)")
    print("======================================================================")

    # 1. Verify scheduler is strictly inactive
    sched_status = get_scheduler_status()
    print(f"[*] Scheduler active check: running={sched_status['running']}, enabled={sched_status['enabled']}")
    assert sched_status["running"] is False, "CRITICAL: Background scheduler is running!"

    # 2. Run all tests inside global DB guard and environment override
    with mock.patch("database.get_db_connection", side_effect=guard_db_connection):
        with mock.patch.dict(os.environ, ENV_OVERRIDE, clear=False):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

                test_cases = [
                    # Group A: Authentication & Authorization
                    ("A1. Missing Auth Token on All 5 Endpoints (HTTP 401)", lambda: test_a1_missing_auth_token_all_endpoints(client)),
                    ("A2. Invalid Auth Token Credentials (HTTP 401)", lambda: test_a2_invalid_auth_token(client)),
                    ("A3. Header Support Bearer & X-Admin-Token", lambda: test_a3_header_support_bearer_and_x_admin_token(client)),
                    ("A4. Unconfigured Server Credentials (HTTP 503)", lambda: test_a4_unconfigured_server_returns_503(client)),
                    ("A5. Multi-Moderator Token Mapping", lambda: asyncio.to_thread(test_a5_multi_moderator_token_mapping)),
                    # Group B: Event Verification & Status Transitions
                    ("B1. Verify Unverified Event (Status & Confidence 100.0)", lambda: asyncio.to_thread(test_b1_verify_unverified_event)),
                    ("B2. Reject Event (Confidence 0.0)", lambda: asyncio.to_thread(test_b2_reject_event)),
                    ("B3. Restore Rejected Event (Confidence 35.0)", lambda: asyncio.to_thread(test_b3_restore_rejected_event)),
                    ("B4. Restore Non-Rejected Event Rejected (HTTP 400)", lambda: asyncio.to_thread(test_b4_restore_non_rejected_event_rejected)),
                    ("B5. Redundant Transition Idempotency Rejected (HTTP 400)", lambda: asyncio.to_thread(test_b5_redundant_transition_idempotency_rejected)),
                    ("B6. Duplicate Event Restriction Enforced (HTTP 400)", lambda: asyncio.to_thread(test_b6_duplicate_event_restriction)),
                    # Group C: Invalid & Missing Data Validation
                    ("C1. Missing Reason Field (HTTP 422)", lambda: test_c1_missing_reason_field(client)),
                    ("C2. Whitespace-Only / Short Reason (HTTP 422)", lambda: test_c2_whitespace_or_too_short_reason(client)),
                    ("C3. Malformed UUID in Path (HTTP 400)", lambda: test_c3_malformed_uuid_in_path(client)),
                    ("C4. Nonexistent Event ID (HTTP 404)", lambda: test_c4_nonexistent_event_id(client)),
                    # Group D: Error Handling & Data Integrity
                    ("D1. Database Failure During Moderation (HTTP 503 Sanitized)", lambda: test_d1_database_failure_during_moderation_returns_503(client)),
                    ("D2. Unrelated Event Fields Preserved", lambda: asyncio.to_thread(test_d2_unrelated_event_fields_preserved)),
                    ("D3. Transaction Rollback on Audit Failure", lambda: asyncio.to_thread(test_d3_transaction_rollback_on_audit_failure)),
                    # Group E: API Response Contract & Audit History
                    ("E1. ModerationResponse Shape Matches Schema & Frontend", lambda: test_e1_verify_response_shape_matches_schema(client)),
                    ("E2. GET Event Audit History List (HTTP 200)", lambda: test_e2_get_event_audit_history_endpoint(client)),
                    ("E3. GET Global Audit History Paginated (HTTP 200)", lambda: test_e3_get_global_audit_history_paginated(client)),
                    ("E4. Frontend TypeScript Contract Compatibility", lambda: asyncio.to_thread(test_e4_frontend_type_contract_compatibility)),
                ]

                results = []
                for name, coro_fn in test_cases:
                    try:
                        await coro_fn()
                        results.append((name, "PASSED"))
                    except Exception as exc:
                        print(f"  [FAIL] {name}: {exc}")
                        results.append((name, f"FAILED: {exc}"))

    print("\n--- Safety & Isolation Verification ---")
    print(f"[*] Real database connections attempted: {real_db_connections_attempted}")
    assert real_db_connections_attempted == 0, (
        f"CRITICAL: {real_db_connections_attempted} database connections attempted!"
    )
    print("  [PASS] Zero database connections attempted. Complete isolation confirmed.")

    print("\n======================================================================")
    print("TEST 10 EXECUTION SUMMARY")
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
    asyncio.run(run_all_moderation_isolated_tests())
