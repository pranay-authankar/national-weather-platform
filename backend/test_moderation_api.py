"""
Automated test suite for Admin Weather Report Moderation API.

Covers:
- Test 1: Admin authentication enforcement (missing token, invalid token, unconfigured server)
- Test 2: Support for both Authorization: Bearer and X-Admin-Token headers
- Test 3: Input validation (missing event ID, malformed UUID, missing or whitespace reason)
- Test 4: Authorized verify request (Unverified -> Verified) with field preservation
- Test 5: Rejection of redundant/invalid transitions (Verified -> Verified)
- Test 6: Authorized reject request (Verified -> Rejected) and rejection idempotency
- Test 7: Authorized restore request (Rejected -> Unverified) for reassessment
- Test 8: Rejection of restore on non-rejected events (Unverified -> Unverified)
- Test 9: Duplicate-event restrictions (cannot verify duplicate with active relationship)
- Test 10: Audit history persistence and descending chronological ordering
- Test 11: Audit history read endpoints (/reports/{id}/audit-history and /audit-history)
- Test 12: Backward compatibility of existing public APIs (/api/events, /api/analytics, /api/events/map)
- Test 13: Final database cleanliness check (strictly 2 baseline records in weather_events, 0 in audit log)
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Any, Dict, List
import unittest.mock as mock
import uuid

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncio
import httpx
from main import app
from database import get_db_connection
from services.admin_auth_service import verify_admin_token, AdminAuthError
from services.moderation_service import (
    moderate_weather_event,
    get_event_audit_history,
    get_audit_history_list,
    EventNotFoundError,
    InvalidStatusTransitionError,
    DuplicateEventRestrictionError,
    ModerationValidationError,
)

TEST_ADMIN_TOKEN = "test_super_secret_moderator_token_2026"
TEST_MODERATOR_ID = "test_lead_moderator"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_ADMIN_TOKEN}"}
X_AUTH_HEADERS = {"X-Admin-Token": TEST_ADMIN_TOKEN}


def get_weather_events_count() -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.weather_events;")
            return cur.fetchone()[0]


def get_audit_log_count() -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.moderation_audit_log;")
            return cur.fetchone()[0]


def insert_test_event(
    status: str = "Unverified",
    confidence: float = 35.0,
    duplicate_of: str = None,
    description: str = "Test moderation event",
) -> str:
    """Insert a temporary test event into weather_events for moderation testing."""
    sql = """
        INSERT INTO public.weather_events (
            source,
            source_record_id,
            event_type,
            description,
            event_timestamp,
            latitude,
            longitude,
            city,
            district,
            state,
            temperature,
            rainfall,
            verification_status,
            confidence_score,
            duplicate_of,
            credibility_score,
            credibility_status,
            credibility_reasons,
            source_trust_score
        ) VALUES (
            'Citizen_Report',
            %(source_record_id)s,
            'Heavy Rain',
            %(description)s,
            NOW(),
            18.5204,
            73.8567,
            'Pune',
            'Pune',
            'Maharashtra',
            26.5,
            42.0,
            %(verification_status)s,
            %(confidence_score)s,
            %(duplicate_of)s,
            45.0,
            'Unverified',
            ARRAY['VALID_LOCATION', 'VALID_TIMESTAMP'],
            50.0
        ) RETURNING event_id;
    """
    event_id = None
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "source_record_id": f"test_mod_{uuid.uuid4().hex[:12]}",
                    "description": description,
                    "verification_status": status,
                    "confidence_score": confidence,
                    "duplicate_of": duplicate_of,
                },
            )
            event_id = str(cur.fetchone()[0])
        conn.commit()
    return event_id


def delete_test_event(event_id: str):
    """Safely delete test event and any cascading audit log records."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.moderation_audit_log WHERE event_id = %s;", (event_id,))
            cur.execute("DELETE FROM public.weather_events WHERE event_id = %s;", (event_id,))
        conn.commit()


async def run_moderation_api_tests():
    baseline_events = get_weather_events_count()
    baseline_audits = get_audit_log_count()

    print(f"[*] Starting Moderation API Tests.")
    print(f"[*] Baseline records: weather_events={baseline_events}, moderation_audit_log={baseline_audits}")
    assert baseline_events == 2, f"Expected 2 baseline weather_events, found {baseline_events}"
    assert baseline_audits == 0, f"Expected 0 baseline moderation_audit_log, found {baseline_audits}"

    # Configure test admin environment variables
    env_patch = {
        "ADMIN_API_KEY": TEST_ADMIN_TOKEN,
        "ADMIN_DEFAULT_MODERATOR_ID": TEST_MODERATOR_ID,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        with mock.patch.dict(os.environ, env_patch, clear=False):

            # --- Test 1: Authentication enforcement ---
            print("\n--- [Test 1] Admin authentication enforcement ---")
            dummy_id = str(uuid.uuid4())
            # Missing token
            res_no_auth = await client.post(f"/api/admin/reports/{dummy_id}/verify", json={"reason": "Valid reason"})
            assert res_no_auth.status_code == 401
            assert "Missing admin authentication token" in res_no_auth.json()["detail"]
            assert "WWW-Authenticate" in res_no_auth.headers

            # Invalid token
            res_bad_auth = await client.post(
                f"/api/admin/reports/{dummy_id}/verify",
                json={"reason": "Valid reason"},
                headers={"Authorization": "Bearer wrong_token_xyz"},
            )
            assert res_bad_auth.status_code == 401
            assert "Invalid admin authentication credentials" in res_bad_auth.json()["detail"]

            # Unconfigured server
            with mock.patch.dict(os.environ, {"ADMIN_API_KEY": "", "ADMIN_API_TOKENS": ""}, clear=False):
                res_unconf = await client.post(
                    f"/api/admin/reports/{dummy_id}/verify",
                    json={"reason": "Valid reason"},
                    headers=AUTH_HEADERS,
                )
                assert res_unconf.status_code == 503
                assert "not configured on the server" in res_unconf.json()["detail"]
            print("[OK] Test 1 passed: Unauthenticated and unauthorized requests rejected properly.")

            # --- Test 2: Support for Authorization Bearer and X-Admin-Token ---
            print("\n--- [Test 2] Header support: Bearer vs X-Admin-Token ---")
            # Bearer token check
            auth_ident_1 = verify_admin_token(TEST_ADMIN_TOKEN)
            assert auth_ident_1 == TEST_MODERATOR_ID

            # X-Admin-Token header check via endpoint
            res_x_tok = await client.get("/api/admin/audit-history", headers=X_AUTH_HEADERS)
            assert res_x_tok.status_code == 200
            assert "data" in res_x_tok.json()
            print("[OK] Test 2 passed: Both Authorization: Bearer and X-Admin-Token headers accepted.")

            # --- Test 3: Input validation ---
            print("\n--- [Test 3] Input validation (missing ID, malformed UUID, missing reason) ---")
            # Non-existent event
            non_existent_id = str(uuid.uuid4())
            res_404 = await client.post(
                f"/api/admin/reports/{non_existent_id}/verify",
                json={"reason": "Valid reason"},
                headers=AUTH_HEADERS,
            )
            assert res_404.status_code == 404
            assert "not found" in res_404.json()["detail"]

            # Malformed UUID
            res_bad_uuid = await client.post(
                "/api/admin/reports/not-a-valid-uuid/verify",
                json={"reason": "Valid reason"},
                headers=AUTH_HEADERS,
            )
            assert res_bad_uuid.status_code == 400
            assert "Invalid UUID" in res_bad_uuid.json()["detail"]

            # Missing reason field (HTTP 422)
            res_missing_reason = await client.post(
                f"/api/admin/reports/{dummy_id}/verify",
                json={},
                headers=AUTH_HEADERS,
            )
            assert res_missing_reason.status_code == 422

            # Whitespace-only reason (HTTP 422)
            res_blank_reason = await client.post(
                f"/api/admin/reports/{dummy_id}/verify",
                json={"reason": "   "},
                headers=AUTH_HEADERS,
            )
            assert res_blank_reason.status_code == 422
            print("[OK] Test 3 passed: Event ID and moderation reason validation strictly enforced.")

            # --- Test 4: Authorized verify request (Unverified -> Verified) ---
            print("\n--- [Test 4] Authorized verify request (Unverified -> Verified) ---")
            temp_event_1 = insert_test_event(status="Unverified", confidence=35.0)
            try:
                verify_reason = "Confirmed through official radar feed and local eyewitness validation."
                res_verify = await client.post(
                    f"/api/admin/reports/{temp_event_1}/verify",
                    json={"reason": verify_reason},
                    headers=AUTH_HEADERS,
                )
                assert res_verify.status_code == 200
                v_body = res_verify.json()
                assert v_body["event_id"] == temp_event_1
                assert v_body["previous_status"] == "Unverified"
                assert v_body["new_status"] == "Verified"
                assert v_body["reason"] == verify_reason
                assert v_body["moderator_id"] == TEST_MODERATOR_ID
                assert "moderated_at" in v_body

                # Verify updated event in response and DB
                ev = v_body["event"]
                assert ev["verification_status"] == "Verified"
                assert ev["confidence_score"] == 100.0

                # Strict preservation of credibility and original fields
                assert ev["credibility_score"] == 45.0
                assert ev["credibility_status"] == "Unverified"
                assert ev["credibility_reasons"] == ["VALID_LOCATION", "VALID_TIMESTAMP"]
                assert ev["source_trust_score"] == 50.0
                assert ev["city"] == "Pune"
                assert ev["state"] == "Maharashtra"
                assert ev["rainfall"] == 42.0

                # Check audit log in DB
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT previous_status, new_status, reason, moderator_id FROM public.moderation_audit_log WHERE event_id = %s;",
                            (temp_event_1,),
                        )
                        audit_row = cur.fetchone()
                        assert audit_row == ("Unverified", "Verified", verify_reason, TEST_MODERATOR_ID)
                print("[OK] Test 4 passed: Event verified successfully with audit log and credibility preservation.")

                # --- Test 5: Rejection of redundant/invalid transitions ---
                print("\n--- [Test 5] Redundant transition rejection (Verified -> Verified) ---")
                res_v_again = await client.post(
                    f"/api/admin/reports/{temp_event_1}/verify",
                    json={"reason": "Attempting to verify already verified event"},
                    headers=AUTH_HEADERS,
                )
                assert res_v_again.status_code == 400
                assert "already 'Verified'" in res_v_again.json()["detail"]
                print("[OK] Test 5 passed: Verified -> Verified correctly rejected with HTTP 400.")

                # --- Test 6: Authorized reject request (Verified -> Rejected) ---
                print("\n--- [Test 6] Authorized reject request (Verified -> Rejected) ---")
                reject_reason = "Fabricated submission contradicted by Doppler radar."
                res_reject = await client.post(
                    f"/api/admin/reports/{temp_event_1}/reject",
                    json={"reason": reject_reason},
                    headers=AUTH_HEADERS,
                )
                assert res_reject.status_code == 200
                r_body = res_reject.json()
                assert r_body["previous_status"] == "Verified"
                assert r_body["new_status"] == "Rejected"
                assert r_body["event"]["verification_status"] == "Rejected"
                assert r_body["event"]["confidence_score"] == 0.0
                assert r_body["event"]["credibility_score"] == 45.0  # Preserved

                # Rejecting an already rejected event -> HTTP 400
                res_r_again = await client.post(
                    f"/api/admin/reports/{temp_event_1}/reject",
                    json={"reason": "Rejecting again"},
                    headers=AUTH_HEADERS,
                )
                assert res_r_again.status_code == 400
                assert "already 'Rejected'" in res_r_again.json()["detail"]
                print("[OK] Test 6 passed: Event rejected with HTTP 200 and redundant rejection rejected with HTTP 400.")

                # --- Test 7: Authorized restore request (Rejected -> Unverified) ---
                print("\n--- [Test 7] Authorized restore request (Rejected -> Unverified) ---")
                restore_reason = "Restoring for secondary sensor review following new evidence."
                res_restore = await client.post(
                    f"/api/admin/reports/{temp_event_1}/restore",
                    json={"reason": restore_reason},
                    headers=AUTH_HEADERS,
                )
                assert res_restore.status_code == 200
                res_body = res_restore.json()
                assert res_body["previous_status"] == "Rejected"
                assert res_body["new_status"] == "Unverified"
                assert res_body["event"]["verification_status"] == "Unverified"
                assert res_body["event"]["confidence_score"] == 35.0
                assert res_body["event"]["credibility_score"] == 45.0  # Preserved
                print("[OK] Test 7 passed: Rejected event restored to Unverified with audit log.")

                # --- Test 8: Rejection of restore on non-rejected events ---
                print("\n--- [Test 8] Rejection of restore on non-rejected events ---")
                # Now the event is Unverified, attempting to restore again must fail
                res_res_bad = await client.post(
                    f"/api/admin/reports/{temp_event_1}/restore",
                    json={"reason": "Attempt restore on unverified event"},
                    headers=AUTH_HEADERS,
                )
                assert res_res_bad.status_code == 400
                assert "Only Rejected reports can be restored" in res_res_bad.json()["detail"]
                print("[OK] Test 8 passed: Inappropriate restore call safely rejected.")

                # --- Test 10: Audit history persistence and ordering ---
                print("\n--- [Test 10] Audit history persistence and chronological ordering ---")
                res_history = await client.get(
                    f"/api/admin/reports/{temp_event_1}/audit-history",
                    headers=AUTH_HEADERS,
                )
                assert res_history.status_code == 200
                hist_logs = res_history.json()
                assert len(hist_logs) == 3

                # Order is DESC (most recent first):
                # 1. Rejected -> Unverified (restore)
                # 2. Verified -> Rejected (reject)
                # 3. Unverified -> Verified (verify)
                assert hist_logs[0]["previous_status"] == "Rejected" and hist_logs[0]["new_status"] == "Unverified"
                assert hist_logs[1]["previous_status"] == "Verified" and hist_logs[1]["new_status"] == "Rejected"
                assert hist_logs[2]["previous_status"] == "Unverified" and hist_logs[2]["new_status"] == "Verified"
                assert all(h["moderator_id"] == TEST_MODERATOR_ID for h in hist_logs)
                print("[OK] Test 10 passed: Audit log persists all transitions in reverse-chronological order.")

                # --- Test 11: Audit history list endpoint ---
                print("\n--- [Test 11] Global audit history endpoint with filtering ---")
                res_all_hist = await client.get(
                    f"/api/admin/audit-history?event_id={temp_event_1}&limit=10",
                    headers=AUTH_HEADERS,
                )
                assert res_all_hist.status_code == 200
                all_body = res_all_hist.json()
                assert all_body["total"] == 3
                assert len(all_body["data"]) == 3
                print("[OK] Test 11 passed: Global audit history endpoint queries and filters accurately.")

            finally:
                delete_test_event(temp_event_1)

            # --- Test 9: Duplicate-event restrictions ---
            print("\n--- [Test 9] Duplicate-event restrictions ---")
            original_event_id = insert_test_event(status="Unverified", description="Original event")
            dup_event_id = insert_test_event(
                status="Duplicate",
                duplicate_of=original_event_id,
                description="Duplicate report",
            )
            try:
                # Attempt to verify duplicate event must be strictly rejected
                res_dup_verify = await client.post(
                    f"/api/admin/reports/{dup_event_id}/verify",
                    json={"reason": "Attempting to mark duplicate as verified"},
                    headers=AUTH_HEADERS,
                )
                assert res_dup_verify.status_code == 400
                assert "Cannot mark a duplicate record as Verified" in res_dup_verify.json()["detail"]

                # Ensure duplicate status and relationship were NOT modified
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT verification_status, duplicate_of FROM public.weather_events WHERE event_id = %s;", (dup_event_id,))
                        row = cur.fetchone()
                        assert row[0] == "Duplicate"
                        assert str(row[1]) == original_event_id

                # Attempting to reject a duplicate IS permitted (e.g. fraudulent duplicate)
                res_dup_reject = await client.post(
                    f"/api/admin/reports/{dup_event_id}/reject",
                    json={"reason": "Duplicate report is invalid spam"},
                    headers=AUTH_HEADERS,
                )
                assert res_dup_reject.status_code == 200
                assert res_dup_reject.json()["new_status"] == "Rejected"
                # Relationship preserved
                assert res_dup_reject.json()["event"]["duplicate_of"] == original_event_id
                print("[OK] Test 9 passed: Duplicate records cannot be verified while duplicate relationship is preserved.")

            finally:
                delete_test_event(dup_event_id)
                delete_test_event(original_event_id)

            # --- Test 12: Backward compatibility of existing public APIs ---
            print("\n--- [Test 12] Backward compatibility of public read APIs ---")
            res_events = await client.get("/api/events")
            assert res_events.status_code == 200
            assert res_events.json()["pagination"]["total"] == baseline_events

            res_analytics = await client.get("/api/analytics/summary")
            assert res_analytics.status_code == 200
            assert res_analytics.json()["total_events"] == baseline_events

            res_map = await client.get("/api/events/map")
            assert res_map.status_code == 200
            assert res_map.json()["count"] == baseline_events
            print("[OK] Test 12 passed: Existing public APIs remain 100% backward compatible.")

            # --- Test 13: Final database cleanliness check ---
            print("\n--- [Test 13] Final database cleanliness check ---")
            final_events = get_weather_events_count()
            final_audits = get_audit_log_count()
            print(f"[*] Final records in Supabase: weather_events={final_events}, moderation_audit_log={final_audits}")
            assert final_events == 2, f"weather_events altered! Expected 2, found {final_events}"
            assert final_audits == 0, f"moderation_audit_log altered! Expected 0, found {final_audits}"
            print("[OK] Test 13 passed: Zero dummy records remain in Supabase. Real baseline records preserved intact.")

    print("\n==================================================")
    print("ALL 13 MODERATION API TESTS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_moderation_api_tests())
