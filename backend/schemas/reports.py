"""
Pydantic schemas for Citizen Weather Reports.
Adheres strictly to docs/api-contract.md.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class CitizenReportCreate(BaseModel):
    """
    Schema for citizen weather report submission.
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
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude coordinate between -90.0 and 90.0 degrees.",
        examples=[19.0760],
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude coordinate between -180.0 and 180.0 degrees.",
        examples=[72.8777],
    )
    timestamp: datetime = Field(
        ...,
        description="ISO-8601 observation timestamp.",
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

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        """Ensure observation timestamp has timezone awareness (defaults to UTC)."""
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
