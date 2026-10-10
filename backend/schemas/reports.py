"""
Pydantic schemas for Citizen Weather Reports.
Adheres strictly to docs/api-contract.md.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class CitizenReportCreate(BaseModel):
    """
    Schema for citizen weather report submission.
    Supports either direct coordinates or administrative dropdown location (state + district).
    Observation timestamp defaults automatically to submission time if omitted.
    """
    event_type: str = Field(
        ...,
        description="Type of observed weather event (e.g., Heavy Rain, Flooding, Thunderstorm).",
        examples=["Heavy Rain"],
    )
    description: str = Field(
        ...,
        description="Detailed eyewitness description of the weather event.",
        examples=["Waterlogging up to 2 feet near local market after sudden torrential downpour."],
    )
    latitude: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Latitude coordinate between -90.0 and 90.0 degrees.",
        examples=[19.0760],
    )
    longitude: Optional[float] = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Longitude coordinate between -180.0 and 180.0 degrees.",
        examples=[72.8777],
    )
    state: Optional[str] = Field(
        default=None,
        description="Administrative state name.",
        examples=["Maharashtra"],
    )
    district: Optional[str] = Field(
        default=None,
        description="Administrative district name.",
        examples=["Mumbai Suburban"],
    )
    city: Optional[str] = Field(
        default=None,
        description="Administrative city name.",
        examples=["Mumbai"],
    )
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO-8601 submission/observation timestamp. Defaults to current UTC time.",
        examples=["2026-10-08T18:30:00Z"],
    )
    image_url: Optional[str] = Field(
        default=None,
        description="Optional URL linking to an uploaded photo evidence.",
        examples=["https://example.com/images/waterlogging_mumbai.jpg"],
    )
    video_url: Optional[str] = Field(
        default=None,
        description="Optional URL linking to an uploaded video clip.",
        examples=[None],
    )

    @field_validator("event_type", mode="before")
    @classmethod
    def validate_event_type(cls, value: Any) -> str:
        """Validate that event_type is a non-empty string."""
        if not isinstance(value, str):
            raise ValueError("event_type must be a valid string.")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("event_type cannot be empty or blank.")
        return trimmed

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: Any) -> str:
        """Validate that description is a non-empty string."""
        if not isinstance(value, str):
            raise ValueError("description must be a valid string.")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("description cannot be empty or blank.")
        return trimmed

    @field_validator("state", "district", "city", mode="before")
    @classmethod
    def sanitize_administrative_fields(cls, value: Any) -> Optional[str]:
        """Trim and convert empty administrative location strings to None."""
        if value is None:
            return None
        trimmed = str(value).strip()
        return trimmed if trimmed else None

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone(cls, value: Optional[datetime]) -> datetime:
        """Ensure observation timestamp has timezone awareness (defaults to UTC)."""
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_validator("image_url", "video_url", mode="before")
    @classmethod
    def sanitize_media_url(cls, value: Any) -> Optional[str]:
        """Convert empty or whitespace-only media URLs to None."""
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed if trimmed else None
        return str(value)

    @model_validator(mode="after")
    def validate_location_presence(self) -> "CitizenReportCreate":
        """Ensure either coordinates (latitude & longitude) or administrative location (state & district) exist."""
        has_coords = self.latitude is not None and self.longitude is not None
        has_dropdown = bool(self.state and (self.district or self.city))
        if not has_coords and not has_dropdown:
            raise ValueError(
                "Either geographical coordinates (latitude and longitude) or "
                "administrative location (state and district) must be provided."
            )
        return self


class CitizenReportResponse(BaseModel):
    """
    Response schema following docs/api-contract.md section 7.
    """
    event_id: str = Field(
        ...,
        description="Unique identifier (UUID) assigned to the created weather event.",
    )
    status: str = Field(
        default="received",
        description="Status of the submitted citizen report.",
    )


class MediaUploadResponse(BaseModel):
    """
    Response schema for uploaded media evidence.
    """
    url: str = Field(..., description="Persistent URL to access uploaded media.")
    relative_url: str = Field(..., description="Relative URL path to access uploaded media.")
    filename: str = Field(..., description="Unique stored filename.")
    media_type: str = Field(..., description="Media category: 'image' or 'video'.")
    content_type: str = Field(..., description="MIME content type.")
    size_bytes: int = Field(..., description="File size in bytes.")

