"""
Pydantic schemas for Weather Analytics API.
Defines response models for aggregate metrics, verification breakdowns, and time series.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AnalyticsCountItem(BaseModel):
    """
    Generic count item for aggregated categories.
    """
    name: Optional[str] = Field(default=None, description="Category name.")
    count: int = Field(..., description="Count of occurrences.")


class VerificationSummary(BaseModel):
    """
    Representation of a verification status count.
    Always includes all canonical statuses (Verified, Likely, Unverified, Rejected, Duplicate).
    """
    status: str = Field(..., description="Verification status category.")
    count: int = Field(default=0, description="Count of events in this verification status.")


class EventTypeCountItem(BaseModel):
    """
    Count of weather events grouped by event_type.
    """
    event_type: str = Field(..., description="Weather event classification.")
    count: int = Field(..., description="Count of events.")


class SourceCountItem(BaseModel):
    """
    Count of weather events grouped by origin data source.
    """
    source: str = Field(..., description="Data source origin.")
    count: int = Field(..., description="Count of events.")


class StateCountItem(BaseModel):
    """
    Count of weather events grouped by state.
    """
    state: str = Field(..., description="State name or 'Unknown'.")
    count: int = Field(..., description="Count of events.")


class DateCountItem(BaseModel):
    """
    Count of weather events grouped by calendar date.
    """
    date: str = Field(..., description="Calendar date in YYYY-MM-DD format.")
    count: int = Field(..., description="Count of events on this date.")


class AnalyticsSummaryResponse(BaseModel):
    """
    Comprehensive analytics summary payload for frontend dashboard widgets and charts.
    """
    total_events: int = Field(..., description="Total count of events matching filter criteria.")
    verified_events: int = Field(default=0, description="Count of Verified events.")
    likely_events: int = Field(default=0, description="Count of Likely events.")
    unverified_events: int = Field(default=0, description="Count of Unverified events.")
    rejected_events: int = Field(default=0, description="Count of Rejected events.")
    duplicate_events: int = Field(default=0, description="Count of Duplicate events.")
    verification_breakdown: List[VerificationSummary] = Field(
        default_factory=list,
        description="Array of all 5 canonical verification categories with counts."
    )
    events_by_verification: List[VerificationSummary] = Field(
        default_factory=list,
        description="Alias array for verification breakdown."
    )
    events_by_type: List[EventTypeCountItem] = Field(
        default_factory=list,
        description="Event breakdown by event_type ordered by count DESC."
    )
    events_by_source: List[SourceCountItem] = Field(
        default_factory=list,
        description="Event breakdown by source ordered by count DESC."
    )
    events_by_state: List[StateCountItem] = Field(
        default_factory=list,
        description="Event breakdown by state ordered by count DESC."
    )
    events_over_time: List[DateCountItem] = Field(
        default_factory=list,
        description="Daily time series ordered chronologically ASC."
    )
