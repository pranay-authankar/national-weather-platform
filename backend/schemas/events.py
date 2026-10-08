"""
Pydantic schemas for Weather Events API.
Defines data structures for single and paginated weather events adhering to docs/api-contract.md.
"""

from datetime import datetime
from typing import Any, List, Optional, Set
from pydantic import BaseModel, Field


# Canonical system value sets for validation
VALID_EVENT_TYPES: Set[str] = {
    "Rainfall",
    "Heavy Rain",
    "Thunderstorm",
    "Flooding",
    "Heatwave",
    "Fog",
    "Dust Storm",
    "Strong Wind",
    "Cyclone",
    "Other",
}

VALID_SOURCES: Set[str] = {
    "IMD",
    "IMD_RSS",
    "Open_Meteo",
    "Data_Gov",
    "Citizen_Report",
    "Other",
}

VALID_VERIFICATION_STATUSES: Set[str] = {
    "Verified",
    "Likely",
    "Unverified",
    "Rejected",
    "Duplicate",
}


class WeatherEventResponse(BaseModel):
    """
    Representation of a single weather event record returned by the API.
    """
    event_id: str = Field(..., description="Unique UUID identifier for the weather event.")
    source: str = Field(..., description="Origin of the observation (e.g. Open_Meteo, Citizen_Report).")
    event_type: str = Field(..., description="Canonical weather event classification.")
    description: Optional[str] = Field(default=None, description="Detailed observation or eyewitness notes.")
    event_timestamp: datetime = Field(..., description="ISO-8601 observation timestamp.")
    latitude: Optional[float] = Field(default=None, description="Geographic latitude coordinate.")
    longitude: Optional[float] = Field(default=None, description="Geographic longitude coordinate.")
    city: Optional[str] = Field(default=None, description="City name derived via geocoding.")
    district: Optional[str] = Field(default=None, description="District name derived via geocoding.")
    state: Optional[str] = Field(default=None, description="State name derived via geocoding.")
    temperature: Optional[float] = Field(default=None, description="Surface temperature in Celsius.")
    rainfall: Optional[float] = Field(default=None, description="Precipitation measurement in mm.")
    humidity: Optional[float] = Field(default=None, description="Relative humidity percentage.")
    wind_speed: Optional[float] = Field(default=None, description="Wind speed in km/h.")
    wind_direction: Optional[float] = Field(default=None, description="Wind direction in degrees.")
    pressure: Optional[float] = Field(default=None, description="Atmospheric pressure in hPa.")
    image_url: Optional[str] = Field(default=None, description="Optional photo evidence URL.")
    video_url: Optional[str] = Field(default=None, description="Optional video clip URL.")
    source_url: Optional[str] = Field(default=None, description="External origin URL.")
    verification_status: str = Field(..., description="Verification status (Verified, Likely, Unverified, Rejected, Duplicate).")
    confidence_score: Optional[float] = Field(default=None, description="System confidence score between 0.0 and 100.0.")
    duplicate_of: Optional[str] = Field(default=None, description="UUID of original event if this is a duplicate.")
    created_at: datetime = Field(..., description="ISO-8601 timestamp when record was persisted.")


class PaginationMetadata(BaseModel):
    """
    Metadata describing paginated query results.
    """
    page: int = Field(..., description="Current page number (1-indexed).")
    page_size: int = Field(..., description="Number of records requested per page.")
    total: int = Field(..., description="Total matching records across all pages.")
    total_pages: int = Field(..., description="Total available pages.")


class PaginatedEventsResponse(BaseModel):
    """
    Paginated response payload wrapping event data and pagination metadata.
    """
    data: List[WeatherEventResponse] = Field(..., description="List of matching weather event records.")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata.")
