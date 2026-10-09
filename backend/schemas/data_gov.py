"""
Pydantic schemas for Data.gov.in (OGD India) integration.
Defines request and response structures for configuration status, manual ingestion,
and dataset records.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DataGovConfigStatusResponse(BaseModel):
    """
    Configuration and operational health status for Data.gov.in integration.
    Never exposes raw API keys.
    """
    configured: bool = Field(..., description="True if both DATA_GOV_API_KEY and DATA_GOV_RESOURCE_ID are provided.")
    has_api_key: bool = Field(..., description="True if DATA_GOV_API_KEY is present.")
    has_resource_id: bool = Field(..., description="True if DATA_GOV_RESOURCE_ID is present.")
    resource_id: Optional[str] = Field(default=None, description="Configured resource ID / UUID.")
    api_key_masked: Optional[str] = Field(default=None, description="Masked API key for identification without leaking secrets.")
    base_url: str = Field(..., description="Base API endpoint URL for Data.gov.in.")
    api_reachable: Optional[bool] = Field(default=None, description="Live reachability status of the API endpoint.")
    message: str = Field(..., description="Operational status or instructions on what variables need to be supplied.")


class DataGovIngestRequest(BaseModel):
    """
    Request payload for manual Data.gov.in ingestion.
    """
    resource_id: Optional[str] = Field(default=None, description="Override resource ID. Defaults to env DATA_GOV_RESOURCE_ID.")
    limit: int = Field(default=10, ge=1, le=1000, description="Number of records to fetch and process.")
    offset: int = Field(default=0, ge=0, description="Offset for pagination.")
    filters: Optional[Dict[str, str]] = Field(default=None, description="Optional field-value filters (e.g. {'state': 'Maharashtra'}).")
    target_table: str = Field(
        default="data_gov_rainfall_records",
        description="Target database destination: 'data_gov_rainfall_records' (default dataset table) or 'weather_events'.",
    )
    skip_if_exists: bool = Field(default=True, description="Skip duplicate records based on source_record_id.")
    dry_run: bool = Field(default=False, description="Fetch and normalize without inserting into database.")


class DataGovIngestResponse(BaseModel):
    """
    Summary response for Data.gov.in ingestion run.
    """
    status: str = Field(..., description="Execution status: 'success', 'skipped', 'dry_run', or 'partial'.")
    message: str = Field(..., description="Human-readable outcome description.")
    resource_id: str = Field(..., description="Target dataset resource ID.")
    target_table: str = Field(..., description="Database table where records were directed.")
    total_fetched: int = Field(..., description="Total records returned by API.")
    successful_ingested: int = Field(..., description="Number of new records successfully inserted.")
    skipped_duplicates: int = Field(..., description="Number of duplicate records skipped.")
    failed_records: int = Field(..., description="Number of records that failed schema validation or insertion.")
    dry_run: bool = Field(..., description="Whether this was a dry run.")
    details: List[Dict[str, Any]] = Field(default=[], description="List of per-record ingestion results.")


class DataGovRainfallRecordResponse(BaseModel):
    """
    Representation of a stored Data.gov.in rainfall observation record.
    """
    record_id: str = Field(..., description="Unique UUID identifier for this record.")
    source: str = Field(..., description="Data source identifier ('Data_Gov').")
    source_record_id: str = Field(..., description="Deterministic stable source record ID.")
    resource_id: str = Field(..., description="Dataset resource ID / UUID.")
    dataset_title: Optional[str] = Field(default=None, description="Title of the source dataset.")
    state: str = Field(..., description="Administrative State name.")
    district: str = Field(..., description="Administrative District name.")
    observation_date: str = Field(..., description="Original observation date in YYYY-MM-DD format.")
    rainfall_mm: Optional[float] = Field(default=None, description="Rainfall amount in millimeters.")
    rainfall_unit: str = Field(default="mm", description="Precipitation unit.")
    normal_rainfall_mm: Optional[float] = Field(default=None, description="Normal rainfall baseline in mm if available.")
    departure_percentage: Optional[float] = Field(default=None, description="Departure percentage from normal if available.")
    source_url: Optional[str] = Field(default=None, description="Link to source dataset page.")
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")


class DataGovRainfallListResponse(BaseModel):
    """
    Paginated list of records from data_gov_rainfall_records table.
    """
    data: List[DataGovRainfallRecordResponse] = Field(..., description="List of rainfall records.")
    count: int = Field(..., description="Number of returned records.")
    total: int = Field(..., description="Total matching records in dataset table.")
    limit: int = Field(..., description="Requested limit.")
    offset: int = Field(..., description="Requested offset.")
