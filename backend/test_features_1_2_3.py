"""
Comprehensive Automated Test Suite for 3 Implemented Features:
1. Feature 1: Detect My Location in Citizen Reports (geospatial resolution & API endpoint)
2. Feature 2: Exclude Rejected Reports from Maps and Analytics (DB queries & endpoints)
3. Feature 3: District Filtering on Dashboard (preserving Rejected records & filtering)

Strict Safety:
- Fully isolated execution.
- Zero mutation of production database records.
- Covers success, edge cases, bounding coordinates, and error responses.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Dict, List
import unittest.mock as mock
import uuid

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import pytest

from main import app
from services.location_service import (
    haversine_distance_km,
    match_authoritative_state,
    match_authoritative_district,
    detect_location_from_coordinates,
)


# ===========================================================================
# FEATURE 1 TESTS: Location Detection & API Endpoint
# ===========================================================================

@pytest.mark.asyncio
async def test_feature_1_haversine_and_helpers():
    """Verify haversine distance calculation and authoritative matching."""
    # Mumbai to Pune (~120 km)
    dist = haversine_distance_km(19.0760, 72.8777, 18.5204, 73.8567)
    assert 110.0 <= dist <= 140.0, f"Expected distance around 120km, got {dist}"

    # State matching including aliases
    assert match_authoritative_state("delhi") == "Delhi (NCT)"
    assert match_authoritative_state("orissa") == "Odisha"
    assert match_authoritative_state("Maharashtra") == "Maharashtra"
    assert match_authoritative_state("NonExistentState") is None

    # District matching
    assert match_authoritative_district("Maharashtra", "pune") is not None
    assert match_authoritative_district("Maharashtra", "UnknownDistrict") is None


@pytest.mark.asyncio
async def test_feature_1_detect_location_service():
    """Verify coordinate resolution across Indian cities and international locations."""
    # 1. Mumbai, Maharashtra
    mumbai_res = await detect_location_from_coordinates(19.0760, 72.8777)
    assert mumbai_res is not None
    assert mumbai_res["state"] == "Maharashtra"
    assert "district" in mumbai_res
    assert mumbai_res["latitude"] == 19.0760
    assert mumbai_res["longitude"] == 72.8777

    # 2. Bengaluru, Karnataka
    blr_res = await detect_location_from_coordinates(12.9716, 77.5946)
    assert blr_res is not None
    assert blr_res["state"] == "Karnataka"

    # 3. Outside India (London, UK) -> must return None
    london_res = await detect_location_from_coordinates(51.5074, -0.1278)
    assert london_res is None

    # 4. Out of bounds coordinates -> must return None
    invalid_res = await detect_location_from_coordinates(120.0, 72.0)
    assert invalid_res is None


@pytest.mark.asyncio
async def test_feature_1_detect_api_endpoint():
    """Verify GET /api/locations/detect HTTP contract and error codes."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Successful resolution
        res_ok = await client.get("/api/locations/detect?latitude=19.0760&longitude=72.8777")
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["state"] == "Maharashtra"
        assert "district" in data
        assert data["latitude"] == 19.0760
        assert data["longitude"] == 72.8777

        # 2. Outside India -> HTTP 404
        res_404 = await client.get("/api/locations/detect?latitude=51.5074&longitude=-0.1278")
        assert res_404.status_code == 404
        assert "Could not resolve" in res_404.json()["detail"]

        # 3. Invalid latitude query parameter (> 90) -> HTTP 422
        res_422 = await client.get("/api/locations/detect?latitude=95.0&longitude=72.8777")
        assert res_422.status_code == 422


# ===========================================================================
# FEATURE 2 TESTS: Exclude Rejected Reports from Maps and Analytics
# ===========================================================================

@pytest.mark.asyncio
async def test_feature_2_map_excludes_rejected_reports():
    """Verify GET /api/events/map enforces exclusion of rejected reports."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. If caller passes verification_status=Rejected, returns empty immediately
        res_rej = await client.get("/api/events/map?verification_status=Rejected")
        assert res_rej.status_code == 200
        rej_body = res_rej.json()
        assert rej_body["count"] == 0
        assert rej_body["data"] == []

        # 2. Normal map request: verify no returned event has verification_status == 'Rejected'
        res_all = await client.get("/api/events/map?limit=100")
        assert res_all.status_code == 200
        all_body = res_all.json()
        assert isinstance(all_body["data"], list)
        for ev in all_body["data"]:
            assert ev["verification_status"] != "Rejected", (
                f"Violation: Rejected event {ev['event_id']} was returned in map data!"
            )


@pytest.mark.asyncio
async def test_feature_2_analytics_excludes_rejected_reports():
    """Verify GET /api/analytics/summary enforces exclusion of rejected reports."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Explicit verification_status=Rejected query returns 0 counts
        res_rej = await client.get("/api/analytics/summary?verification_status=Rejected")
        assert res_rej.status_code == 200
        rej_body = res_rej.json()
        assert rej_body["total_events"] == 0
        assert rej_body["rejected_events"] == 0
        assert rej_body["events_by_type"] == []
        assert rej_body["events_by_source"] == []

        # 2. General analytics query: rejected_events is 0, total_events matches non-rejected
        res_summary = await client.get("/api/analytics/summary")
        assert res_summary.status_code == 200
        summary_body = res_summary.json()
        assert summary_body["rejected_events"] == 0, "rejected_events must be 0 in analytics"
        
        # Verify verification breakdown has Rejected count 0
        breakdown = {item["status"]: item["count"] for item in summary_body["verification_breakdown"]}
        assert breakdown.get("Rejected", 0) == 0, "Rejected count in breakdown must be 0"


# ===========================================================================
# FEATURE 3 TESTS: Dashboard District Filtering & Rejected Report Preservation
# ===========================================================================

@pytest.mark.asyncio
async def test_feature_3_dashboard_preserves_rejected_and_filters_by_district():
    """Verify GET /api/events continues to support Rejected status and filters by district."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Calling /api/events with verification_status=Rejected must NOT be blocked (preserves Dashboard)
        res_dashboard_rej = await client.get("/api/events?verification_status=Rejected")
        assert res_dashboard_rej.status_code == 200
        rej_data = res_dashboard_rej.json()
        assert "data" in rej_data
        assert "pagination" in rej_data

        # 2. Calling /api/events with district filter
        res_district = await client.get("/api/events?district=Mumbai")
        assert res_district.status_code == 200
        district_data = res_district.json()
        assert "data" in district_data
        # If any records match Mumbai, their district must match case-insensitively
        for ev in district_data["data"]:
            if ev.get("district"):
                assert "mumbai" in ev["district"].lower()


if __name__ == "__main__":
    print("[*] Running all tests synchronously via pytest...")
    pytest.main(["-v", __file__])
