"""
Pydantic schemas for Weather Events Map API.
Defines lightweight models specifically tailored for map markers and geospatial queries.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class MapEvent(BaseModel):
    """
    Lightweight geospatial representation of a weather event for map rendering.
    Excludes heavy descriptions, image/video URLs, and non-essential attributes.
    """
    event_id: str = Field(..., description="Unique UUID identifier for the weather event.")
    latitude: float = Field(..., description="Geographic latitude coordinate (-90.0 to 90.0).")
    longitude: float = Field(..., description="Geographic longitude coordinate (-180.0 to 180.0).")
    event_type: str = Field(..., description="Canonical weather event classification.")
    source: str = Field(..., description="Origin data source (e.g. Open_Meteo, Citizen_Report).")
    event_timestamp: datetime = Field(..., description="ISO-8601 observation timestamp.")
    city: Optional[str] = Field(default=None, description="City name derived via geocoding.")
    district: Optional[str] = Field(default=None, description="District name derived via geocoding.")
    state: Optional[str] = Field(default=None, description="State name derived via geocoding.")
    verification_status: str = Field(..., description="Verification status (Verified, Likely, Unverified, Rejected, Duplicate).")
    confidence_score: Optional[float] = Field(default=None, description="System confidence score between 0.0 and 100.0.")


class MapEventResponse(BaseModel):
    """
    Response envelope for GET /api/events/map containing marker data and total count.
    """
    data: List[MapEvent] = Field(..., description="List of lightweight map event markers.")
    count: int = Field(..., description="Total count of map event markers returned.")
