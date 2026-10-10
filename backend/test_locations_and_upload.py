"""
Unit and integration tests for locations service and media upload endpoint.
Guarantees zero database mutation and isolated execution.
"""

import io
from pathlib import Path
import pytest
import httpx

from main import app
from schemas.reports import CitizenReportCreate
from services.location_service import (
    get_all_states,
    get_districts_for_state,
    resolve_district_coordinates,
)


def test_location_service_unit():
    """Verify authoritative location service methods."""
    states = get_all_states()
    assert len(states) >= 30, f"Expected at least 30 states/UTs, got {len(states)}"
    assert "Maharashtra" in states
    assert "Delhi (NCT)" in states
    assert "Tamil Nadu" in states

    # Districts for Maharashtra
    mh_districts = get_districts_for_state("Maharashtra")
    assert len(mh_districts) > 0
    dist_names = [d["district"] for d in mh_districts]
    assert any("Mumbai" in d for d in dist_names)
    assert any("Pune" in d for d in dist_names)
    assert any("Nagpur" in d for d in dist_names)

    # Coordinate resolution
    coords = resolve_district_coordinates("Maharashtra", "Pune")
    assert coords is not None
    lat, lon = coords
    assert 18.0 <= lat <= 19.0
    assert 73.0 <= lon <= 74.5

    # Case insensitivity
    coords_ci = resolve_district_coordinates("maharashtra", "pune")
    assert coords_ci == coords

    # Unknown state
    assert get_districts_for_state("Atlantis") == []
    assert resolve_district_coordinates("Atlantis", "City") is None


def test_citizen_report_schema_location_dropdowns():
    """Verify that CitizenReportCreate accepts state/district without manual lat/lon."""
    payload = {
        "event_type": "Flooding",
        "description": "Heavy waterlogging near market area",
        "state": "Maharashtra",
        "district": "Mumbai Suburban",
    }
    report = CitizenReportCreate(**payload)
    assert report.state == "Maharashtra"
    assert report.district == "Mumbai Suburban"
    assert report.latitude is None
    assert report.longitude is None
    assert report.timestamp is not None  # Auto-generated submission timestamp

    # Coordinates-only still accepted
    payload_coords = {
        "event_type": "Flooding",
        "description": "Heavy waterlogging near market area",
        "latitude": 19.0760,
        "longitude": 72.8777,
    }
    report_coords = CitizenReportCreate(**payload_coords)
    assert report_coords.latitude == 19.0760
    assert report_coords.longitude == 72.8777

    # Missing both must fail
    with pytest.raises(Exception):
        CitizenReportCreate(
            event_type="Flooding",
            description="Waterlogging",
        )


@pytest.mark.asyncio
async def test_locations_api_endpoints():
    """Verify /api/locations endpoints via ASGI transport."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. States endpoint
        res = await client.get("/api/locations/states")
        assert res.status_code == 200
        states = res.json()
        assert isinstance(states, list)
        assert "Maharashtra" in states

        # 2. Districts endpoint
        res = await client.get("/api/locations/districts?state=Maharashtra")
        assert res.status_code == 200
        districts = res.json()
        assert isinstance(districts, list)
        assert len(districts) > 0
        first = districts[0]
        assert "district" in first
        assert "latitude" in first
        assert "longitude" in first

        # 3. Non-existent state
        res_404 = await client.get("/api/locations/districts?state=UnknownLand")
        assert res_404.status_code == 404

        # 4. Full hierarchy endpoint
        res_full = await client.get("/api/locations")
        assert res_full.status_code == 200
        data = res_full.json()
        assert "Maharashtra" in data
        assert len(data["Maharashtra"]) > 0


@pytest.mark.asyncio
async def test_media_upload_endpoint():
    """Verify POST /api/reports/upload handling."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Upload valid image
        image_bytes = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 200
        files = {"file": ("test_rain.jpg", io.BytesIO(image_bytes), "image/jpeg")}
        res = await client.post("/api/reports/upload", files=files)
        assert res.status_code == 201
        data = res.json()
        assert "url" in data
        assert data["media_type"] == "image"
        assert data["content_type"] == "image/jpeg"
        assert data["size_bytes"] == len(image_bytes)

        # Check file exists in uploads dir
        saved_filename = data["filename"]
        uploads_dir = Path(__file__).resolve().parent / "uploads"
        saved_path = uploads_dir / saved_filename
        assert saved_path.exists()
        # Clean up test artifact
        try:
            saved_path.unlink()
        except Exception:
            pass

        # 2. Upload valid video
        video_bytes = b"\x00\x00\x00 ftypisom" + b"\x00" * 300
        files_v = {"file": ("storm.mp4", io.BytesIO(video_bytes), "video/mp4")}
        res_v = await client.post("/api/reports/upload", files=files_v)
        assert res_v.status_code == 201
        data_v = res_v.json()
        assert data_v["media_type"] == "video"
        assert data_v["content_type"] == "video/mp4"
        saved_v = uploads_dir / data_v["filename"]
        assert saved_v.exists()
        try:
            saved_v.unlink()
        except Exception:
            pass

        # 3. Reject unsupported file format (e.g. PDF)
        pdf_bytes = b"%PDF-1.4 test document"
        files_pdf = {"file": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        res_pdf = await client.post("/api/reports/upload", files=files_pdf)
        assert res_pdf.status_code == 400
        assert "Unsupported media format" in res_pdf.json()["detail"]

        # 4. Reject empty file
        files_empty = {"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
        res_empty = await client.post("/api/reports/upload", files=files_empty)
        assert res_empty.status_code == 400


if __name__ == "__main__":
    test_location_service_unit()
    test_citizen_report_schema_location_dropdowns()
    print("All sync tests passed!")
