"""
Service module for interacting with the Open Government Data (OGD) Platform India (data.gov.in).
Fetches, validates, normalizes, and persists daily district-wise rainfall data while ensuring
credential security, duplicate prevention, and zero data fabrication.
"""

from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from dotenv import load_dotenv
import httpx
import psycopg

from database import get_db_connection, sanitize_error_message
from services.weather_event_service import weather_event_exists

logger = logging.getLogger(__name__)

# Load backend/.env if available
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=False)

# Data.gov.in API Defaults
DEFAULT_DATA_GOV_BASE_URL: str = "https://api.data.gov.in/resource"
DEFAULT_DATA_GOV_RESOURCE_ID: str = "8018e697-393d-4c6e-8a24-91ee0f2a996b"
DATASET_ATTRIBUTION: str = (
    "India Meteorological Department (IMD) / Ministry of Earth Sciences via Data.gov.in "
    "(Open Government Data Platform)"
)
DEFAULT_TIMEOUT_SECONDS: float = 15.0


# ---------------------------------------------------------------------------
# Exceptions Hierarchy
# ---------------------------------------------------------------------------

class DataGovError(Exception):
    """Base exception for all Data.gov.in service operations."""
    pass


class DataGovConfigError(DataGovError):
    """Raised when required configuration (e.g. DATA_GOV_API_KEY) is missing."""
    pass


class DataGovTimeoutError(DataGovError):
    """Raised when an HTTP request to Data.gov.in times out."""
    pass


class DataGovNetworkError(DataGovError):
    """Raised when connection to Data.gov.in fails or is actively refused."""
    pass


class DataGovAPIError(DataGovError):
    """Raised when Data.gov.in returns an HTTP error code (401, 403, 404, 500, etc.)."""
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class DataGovResponseError(DataGovError):
    """Raised when response body cannot be parsed or lacks required structure."""
    pass


class DataGovValidationError(DataGovError):
    """Raised when a record contains malformed or unparseable fields."""
    pass


# ---------------------------------------------------------------------------
# Configuration Helpers
# ---------------------------------------------------------------------------

def get_data_gov_config() -> Dict[str, Any]:
    """
    Read Data.gov.in parameters securely from environment variables.
    """
    load_dotenv(dotenv_path=env_path, override=False)
    api_key = os.getenv("DATA_GOV_API_KEY", "").strip()
    resource_id = os.getenv("DATA_GOV_RESOURCE_ID", "").strip() or DEFAULT_DATA_GOV_RESOURCE_ID
    base_url = os.getenv("DATA_GOV_API_BASE_URL", DEFAULT_DATA_GOV_BASE_URL).strip().rstrip("/")
    timeout = float(os.getenv("DATA_GOV_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    return {
        "api_key": api_key,
        "resource_id": resource_id,
        "base_url": base_url,
        "timeout_seconds": timeout,
    }


def mask_credential(credential: Optional[str]) -> Optional[str]:
    """
    Return a masked representation of an API credential for safe display.
    Example: '579b...489c' or '***' if too short.
    """
    if not credential:
        return None
    cred_len = len(credential)
    if cred_len <= 8:
        return "********"
    return f"{credential[:4]}...{credential[-4:]}"


def sanitize_data_gov_message(message: str) -> str:
    """
    Ensure the Data.gov.in API key is scrubbed from any error or logging message.
    """
    if not message:
        return ""
    sanitized = sanitize_error_message(message)
    api_key = os.getenv("DATA_GOV_API_KEY", "").strip()
    if api_key and api_key in sanitized:
        sanitized = sanitized.replace(api_key, "******")
    return sanitized


def get_data_gov_status() -> Dict[str, Any]:
    """
    Inspect whether the connector is fully configured without leaking secrets.
    """
    config = get_data_gov_config()
    has_key = bool(config["api_key"])
    has_res = bool(config["resource_id"])

    if not has_key:
        msg = (
            "DATA_GOV_API_KEY is not configured in backend/.env. "
            "To enable live Data.gov.in ingestion, register at https://data.gov.in "
            "and add your personal API key as DATA_GOV_API_KEY=<your_api_key>."
        )
    else:
        msg = "Data.gov.in connector is configured with API key and resource ID."

    return {
        "configured": has_key and has_res,
        "has_api_key": has_key,
        "has_resource_id": has_res,
        "resource_id": config["resource_id"],
        "api_key_masked": mask_credential(config["api_key"]),
        "base_url": config["base_url"],
        "timeout_seconds": config["timeout_seconds"],
        "message": msg,
    }


# ---------------------------------------------------------------------------
# HTTP Data Fetching
# ---------------------------------------------------------------------------

async def fetch_data_gov_records(
    resource_id: Optional[str] = None,
    api_key: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    filters: Optional[Dict[str, str]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Fetch records from the official Data.gov.in API endpoint over HTTPS.
    
    Parameters:
        resource_id: Resource ID / UUID of the dataset. Falls back to env.
        api_key: API Key for authentication. Falls back to env.
        limit: Number of records to request.
        offset: Record pagination offset.
        filters: Optional dictionary of field=value filters.
        client: Optional injected httpx.AsyncClient (for testing).

    Returns:
        Dict[str, Any]: Parsed JSON response containing metadata and records list.

    Raises:
        DataGovConfigError: When credentials or resource ID are missing.
        DataGovTimeoutError: When request times out.
        DataGovNetworkError: On connection refused or network failure.
        DataGovAPIError: On non-200 HTTP responses.
        DataGovResponseError: On invalid JSON or malformed structure.
    """
    config = get_data_gov_config()
    target_resource_id = (resource_id or config["resource_id"]).strip()
    target_api_key = (api_key or config["api_key"]).strip()

    if not target_api_key:
        raise DataGovConfigError(
            "DATA_GOV_API_KEY is missing. Please set DATA_GOV_API_KEY in backend/.env "
            "with a valid key generated from your data.gov.in account."
        )

    if not target_resource_id:
        raise DataGovConfigError(
            "DATA_GOV_RESOURCE_ID is missing. Please specify a valid dataset resource ID."
        )

    url = f"{config['base_url']}/{target_resource_id}"

    params: Dict[str, Any] = {
        "api-key": target_api_key,
        "format": "json",
        "limit": limit,
        "offset": offset,
    }

    if filters:
        for k, v in filters.items():
            params[f"filters[{k}]"] = str(v)

    timeout = config["timeout_seconds"]

    async def _do_request(c: httpx.AsyncClient) -> httpx.Response:
        return await c.get(url, params=params)

    try:
        if client is not None:
            response = await _do_request(client)
        else:
            async with httpx.AsyncClient(timeout=timeout) as c:
                response = await _do_request(c)
    except httpx.TimeoutException as exc:
        raise DataGovTimeoutError(
            f"Request to Data.gov.in timed out after {timeout} seconds."
        ) from exc
    except httpx.RequestError as exc:
        sanitized_exc = sanitize_data_gov_message(str(exc))
        raise DataGovNetworkError(
            f"Failed to connect to Data.gov.in: {sanitized_exc}"
        ) from exc

    # Handle non-200 HTTP status
    if response.status_code != 200:
        raw_detail = sanitize_data_gov_message(response.text)
        try:
            err_json = response.json()
            if "message" in err_json:
                raw_detail = err_json["message"]
            elif "error" in err_json:
                raw_detail = str(err_json["error"])
        except Exception:
            pass
        sanitized_detail = sanitize_data_gov_message(str(raw_detail)[:300])
        raise DataGovAPIError(
            status_code=response.status_code,
            message=f"Data.gov.in returned HTTP {response.status_code}: {sanitized_detail}",
        )

    # Parse JSON
    try:
        data = response.json()
    except Exception as exc:
        raise DataGovResponseError("Failed to parse JSON response from Data.gov.in.") from exc

    if not isinstance(data, dict):
        raise DataGovResponseError("Data.gov.in response must be a JSON object.")

    # Check for API error status embedded in JSON
    if data.get("status") == "error":
        err_msg = sanitize_data_gov_message(data.get("message", "Unknown API error"))
        raise DataGovAPIError(status_code=400, message=f"Data.gov.in API error: {err_msg}")

    if "records" not in data or not isinstance(data["records"], list):
        raise DataGovResponseError("Data.gov.in response does not contain a valid 'records' list.")

    return data


def parse_data_gov_response(raw_data: Dict[str, Any], resource_id: str) -> Dict[str, Any]:
    """
    Parse top-level metadata and validate the records list from raw Data.gov.in JSON.
    """
    if not isinstance(raw_data, dict):
        raise DataGovResponseError("Data.gov.in response must be a JSON object.")

    if raw_data.get("status") == "error":
        err_msg = sanitize_data_gov_message(raw_data.get("message", "Unknown API error"))
        raise DataGovAPIError(status_code=400, message=f"Data.gov.in API error: {err_msg}")

    records = raw_data.get("records")
    if records is None or not isinstance(records, list):
        raise DataGovResponseError("Data.gov.in response does not contain a valid 'records' list.")

    return {
        "index_name": raw_data.get("index_name", resource_id),
        "title": raw_data.get("title") or "Daily District-wise Rainfall Data",
        "desc": raw_data.get("desc"),
        "org_type": raw_data.get("org_type"),
        "org": raw_data.get("org", []),
        "sector": raw_data.get("sector", []),
        "total": int(raw_data.get("total", len(records))),
        "count": int(raw_data.get("count", len(records))),
        "limit": int(raw_data.get("limit", len(records))),
        "offset": int(raw_data.get("offset", 0)),
        "fields": raw_data.get("field", []),
        "records": records,
    }


# ---------------------------------------------------------------------------
# Normalization & Schema Validation
# ---------------------------------------------------------------------------

def _clean_slug(val: str) -> str:
    """Convert text to safe lowercase identifier string."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", val.strip().lower())
    return cleaned.strip("_")


def _find_field_value(record: Dict[str, Any], candidates: List[str]) -> Optional[Any]:
    """Find first matching field name in record ignoring case and formatting."""
    record_lower = {k.strip().lower(): v for k, v in record.items()}
    for candidate in candidates:
        cand_lower = candidate.strip().lower()
        if cand_lower in record_lower and record_lower[cand_lower] is not None:
            return record_lower[cand_lower]
    return None


def _parse_date_string(date_val: Any) -> date:
    """
    Parse date from various standard formats found across Indian government datasets:
    YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, YYYY/MM/DD, DD-Mon-YYYY.
    """
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()

    if not isinstance(date_val, str) or not date_val.strip():
        raise DataGovValidationError("Date field is missing or empty.")

    clean_str = date_val.strip().split("T")[0].split(" ")[0]

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%Y%m%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt).date()
        except ValueError:
            continue

    raise DataGovValidationError(
        f"Unrecognized date format: '{date_val}'. Expected YYYY-MM-DD or DD-MM-YYYY."
    )


def _parse_rainfall_value(val: Any) -> Optional[float]:
    """
    Parse rainfall number in millimeters.
    Safely handles NA / NR / hyphen values without inventing numbers.
    """
    if val is None:
        return None

    if isinstance(val, (int, float)):
        float_val = float(val)
        if float_val < 0:
            raise DataGovValidationError(f"Rainfall cannot be negative: {float_val}")
        return float_val

    if isinstance(val, str):
        cleaned = val.strip().upper()
        if cleaned in ("", "-", "NA", "N.A.", "NR", "N.R.", "NIL", "NULL", "NONE"):
            return None
        # Remove trailing units if present (e.g. "12.5 mm" -> "12.5")
        cleaned = re.sub(r"[^\d\.]", "", cleaned)
        if not cleaned:
            return None
        try:
            parsed = float(cleaned)
            if parsed < 0:
                raise DataGovValidationError(f"Rainfall cannot be negative: {parsed}")
            return parsed
        except ValueError:
            raise DataGovValidationError(f"Invalid non-numeric rainfall value: '{val}'")

    raise DataGovValidationError(f"Unsupported rainfall data type: {type(val)}")


def normalize_rainfall_record(
    raw_record: Dict[str, Any],
    resource_id: str,
    dataset_title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Normalize a raw Data.gov.in rainfall record into our structured schema.
    
    Preserves:
    - Original observation date
    - State and district
    - Rainfall units ('mm')
    - Source URL and attribution
    - Deterministic stable source_record_id
    
    Rules:
    - Never invents GPS coordinates (latitude, longitude remain None)
    - Never invents weather measurements (temperature, humidity, wind remain None)
    - Rejects malformed records missing critical fields (state, district, date)
    """
    if not isinstance(raw_record, dict):
        raise DataGovValidationError("Record must be a JSON dictionary.")

    # 1. State
    state_val = _find_field_value(
        raw_record, ["state", "state_name", "state_ut", "statename", "state_or_ut"]
    )
    if not state_val or not str(state_val).strip():
        raise DataGovValidationError("Record is missing required 'state' field.")
    state = str(state_val).strip().title()

    # 2. District
    district_val = _find_field_value(
        raw_record, ["district", "district_name", "districtname"]
    )
    if not district_val or not str(district_val).strip():
        raise DataGovValidationError("Record is missing required 'district' field.")
    district = str(district_val).strip().title()

    # 3. Observation Date
    date_val = _find_field_value(
        raw_record, ["date", "observation_date", "record_date", "rainfall_date", "rainfall_recorded_date"]
    )
    if not date_val:
        raise DataGovValidationError("Record is missing required 'date' field.")
    obs_date = _parse_date_string(date_val)

    # 4. Rainfall (mm)
    rainfall_val = _find_field_value(
        raw_record, ["rainfall", "rainfall_mm", "actual_rainfall", "actual", "daily_rainfall", "precipitation"]
    )
    rainfall_mm = _parse_rainfall_value(rainfall_val)

    # 5. Normal and departure (if present)
    normal_val = _find_field_value(raw_record, ["normal_rainfall", "normal", "normal_rainfall_mm"])
    normal_rainfall_mm = _parse_rainfall_value(normal_val) if normal_val is not None else None

    departure_val = _find_field_value(raw_record, ["departure", "departure_percentage", "dep_percentage"])
    departure_pct = None
    if departure_val is not None:
        try:
            clean_dep = str(departure_val).replace("%", "").strip()
            if clean_dep not in ("", "-", "NA", "N.A."):
                departure_pct = float(clean_dep)
        except ValueError:
            pass

    # 6. Generate Deterministic Stable Record Identifier
    date_str = obs_date.strftime("%Y%m%d")
    slug_res = _clean_slug(resource_id)
    slug_state = _clean_slug(state)
    slug_district = _clean_slug(district)
    source_record_id = f"data_gov_{slug_res}_{slug_state}_{slug_district}_{date_str}"

    source_url = f"https://data.gov.in/resource/{resource_id}"

    return {
        "source": "Data_Gov",
        "source_record_id": source_record_id,
        "resource_id": resource_id,
        "dataset_title": dataset_title or "Daily District-wise Rainfall Data",
        "state": state,
        "district": district,
        "observation_date": obs_date,
        "rainfall_mm": rainfall_mm,
        "rainfall_unit": "mm",
        "normal_rainfall_mm": normal_rainfall_mm,
        "departure_percentage": departure_pct,
        "raw_data": raw_record,
        "source_url": source_url,
    }


def normalize_data_gov_to_weather_event(normalized_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map a validated Data.gov.in rainfall record to the standard weather_events schema.
    
    Guarantees:
    - Never classifies historical aggregates as current live weather.
    - Preserves historical observation timestamp (at 08:30 IST / 03:00 UTC, the IMD standard daily rainfall time).
    - Coordinates are strictly None (no fabricated GPS).
    - Unmeasured variables (temperature, humidity, pressure, wind) are strictly None.
    - Verified status with high source trust for official government records.
    """
    obs_date: date = normalized_record["observation_date"]
    rainfall: Optional[float] = normalized_record["rainfall_mm"]
    district = normalized_record["district"]
    state = normalized_record["state"]

    # Observation timestamp in UTC preserving original observation date
    # Standard IMD daily rainfall observation is taken at 08:30 IST (03:00 UTC)
    event_timestamp = datetime(
        obs_date.year, obs_date.month, obs_date.day, 3, 0, 0, tzinfo=timezone.utc
    )

    # Classify event type based on genuine precipitation amount
    if rainfall is not None and rainfall >= 64.5:
        event_type = "Heavy Rain"  # IMD standard definition of heavy rain >= 64.5mm
    else:
        event_type = "Rainfall"

    rf_display = f"{rainfall:.1f} mm" if rainfall is not None else "unrecorded"
    desc = (
        f"Historical daily observed rainfall ({rf_display}) for {district}, {state} "
        f"on {obs_date.isoformat()} published by {DATASET_ATTRIBUTION}."
    )

    return {
        "source": "Data_Gov",
        "source_record_id": normalized_record["source_record_id"],
        "event_type": event_type,
        "description": desc,
        "event_timestamp": event_timestamp,
        "latitude": None,
        "longitude": None,
        "location": None,
        "city": None,
        "district": district,
        "state": state,
        "temperature": None,
        "rainfall": rainfall,
        "humidity": None,
        "wind_speed": None,
        "wind_direction": None,
        "pressure": None,
        "image_url": None,
        "video_url": None,
        "source_url": normalized_record["source_url"],
        "verification_status": "Verified",
        "confidence_score": 95.0,
        "duplicate_of": None,
        "credibility_score": 95.0,
        "credibility_status": "Verified",
        "credibility_reasons": ["OFFICIAL_GOVERNMENT_DATA", "DATA_GOV_IN"],
        "source_trust_score": 95.0,
    }


# ---------------------------------------------------------------------------
# Database Utilities & Duplicate Prevention
# ---------------------------------------------------------------------------

def data_gov_rainfall_record_exists(source_record_id: str) -> bool:
    """
    Check if a rainfall record from Data.gov.in already exists in data_gov_rainfall_records.
    """
    sql = """
        SELECT 1
        FROM public.data_gov_rainfall_records
        WHERE source_record_id = %(source_record_id)s
        LIMIT 1;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"source_record_id": source_record_id})
                return cur.fetchone() is not None
    except Exception as exc:
        sanitized = sanitize_data_gov_message(str(exc))
        logger.warning("Error checking existing data_gov record %s: %s", source_record_id, sanitized)
        return False


def insert_data_gov_rainfall_record(record_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert a validated Data.gov.in rainfall record into the dedicated data_gov_rainfall_records table.
    """
    insert_sql = """
        INSERT INTO public.data_gov_rainfall_records (
            source,
            source_record_id,
            resource_id,
            dataset_title,
            state,
            district,
            observation_date,
            rainfall_mm,
            rainfall_unit,
            normal_rainfall_mm,
            departure_percentage,
            raw_data,
            source_url
        ) VALUES (
            %(source)s,
            %(source_record_id)s,
            %(resource_id)s,
            %(dataset_title)s,
            %(state)s,
            %(district)s,
            %(observation_date)s,
            %(rainfall_mm)s,
            %(rainfall_unit)s,
            %(normal_rainfall_mm)s,
            %(departure_percentage)s,
            %(raw_data)s,
            %(source_url)s
        )
        RETURNING record_id, created_at;
    """
    payload = {
        **record_data,
        "raw_data": json.dumps(record_data.get("raw_data", {})),
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(insert_sql, payload)
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("Failed to retrieve record_id from inserted record.")
                record_id = str(row[0])
                created_at = row[1]
            conn.commit()

        result = {**record_data}
        result["record_id"] = record_id
        result["created_at"] = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        result["observation_date"] = record_data["observation_date"].isoformat()
        return result

    except psycopg.Error as exc:
        sanitized = sanitize_data_gov_message(str(exc))
        raise RuntimeError(f"Database insertion error: {sanitized}") from None


def get_data_gov_rainfall_records(
    state: Optional[str] = None,
    district: Optional[str] = None,
    start_date: Optional[Union[date, str]] = None,
    end_date: Optional[Union[date, str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Query records stored in the dedicated data_gov_rainfall_records table.
    """
    conditions: List[str] = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if state:
        conditions.append("LOWER(state) = LOWER(%(state)s)")
        params["state"] = state.strip()

    if district:
        conditions.append("LOWER(district) = LOWER(%(district)s)")
        params["district"] = district.strip()

    if start_date:
        conditions.append("observation_date >= %(start_date)s")
        params["start_date"] = str(start_date)

    if end_date:
        conditions.append("observation_date <= %(end_date)s")
        params["end_date"] = str(end_date)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    select_sql = f"""
        SELECT
            record_id,
            source,
            source_record_id,
            resource_id,
            dataset_title,
            state,
            district,
            observation_date,
            rainfall_mm,
            rainfall_unit,
            normal_rainfall_mm,
            departure_percentage,
            source_url,
            created_at
        FROM public.data_gov_rainfall_records
        {where_clause}
        ORDER BY observation_date DESC, state ASC, district ASC
        LIMIT %(limit)s OFFSET %(offset)s;
    """

    count_sql = f"""
        SELECT COUNT(*)
        FROM public.data_gov_rainfall_records
        {where_clause};
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                total = cur.fetchone()[0]

                cur.execute(select_sql, params)
                rows = cur.fetchall()

        records: List[Dict[str, Any]] = []
        for r in rows:
            records.append({
                "record_id": str(r[0]),
                "source": r[1],
                "source_record_id": r[2],
                "resource_id": r[3],
                "dataset_title": r[4],
                "state": r[5],
                "district": r[6],
                "observation_date": r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7]),
                "rainfall_mm": r[8],
                "rainfall_unit": r[9] or "mm",
                "normal_rainfall_mm": r[10],
                "departure_percentage": r[11],
                "source_url": r[12],
                "created_at": r[13].isoformat() if hasattr(r[13], "isoformat") else str(r[13]),
            })

        return {
            "data": records,
            "count": len(records),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except psycopg.Error as exc:
        sanitized = sanitize_data_gov_message(str(exc))
        raise RuntimeError(f"Database query error: {sanitized}") from None


# ---------------------------------------------------------------------------
# High-Level Ingestion Orchestrator
# ---------------------------------------------------------------------------

async def ingest_data_gov_rainfall(
    resource_id: Optional[str] = None,
    api_key: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    filters: Optional[Dict[str, str]] = None,
    target_table: str = "data_gov_rainfall_records",
    skip_if_exists: bool = True,
    dry_run: bool = False,
    mock_payload: Optional[Dict[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """
    Orchestrate fetching, parsing, normalizing, and inserting Data.gov.in rainfall data.
    
    Parameters:
        resource_id: Dataset resource identifier.
        api_key: User API key.
        limit: Number of records to process.
        offset: Record pagination offset.
        filters: Optional field filters.
        target_table: 'data_gov_rainfall_records' (default dataset table) or 'weather_events'.
        skip_if_exists: Skip duplicate records based on deterministic source_record_id.
        dry_run: Validate without inserting into database.
        mock_payload: Optional pre-parsed API response dictionary for testing without external network.
        client: Optional httpx.AsyncClient.
    """
    config = get_data_gov_config()
    target_res = (resource_id or config["resource_id"]).strip()

    # 1. Fetch raw data (or use mock payload if supplied)
    if mock_payload is not None:
        raw_data = mock_payload
    else:
        raw_data = await fetch_data_gov_records(
            resource_id=target_res,
            api_key=api_key,
            limit=limit,
            offset=offset,
            filters=filters,
            client=client,
        )

    dataset_title = raw_data.get("title") or "Daily District-wise Rainfall Data"
    records_list = raw_data.get("records", [])

    successful = 0
    skipped_duplicates = 0
    failed = 0
    details: List[Dict[str, Any]] = []

    for raw_rec in records_list:
        try:
            # 2. Normalize and validate fields
            normalized = normalize_rainfall_record(
                raw_record=raw_rec,
                resource_id=target_res,
                dataset_title=dataset_title,
            )

            rec_id = normalized["source_record_id"]

            # 3. Duplicate check
            is_dup = False
            if skip_if_exists:
                if target_table == "weather_events":
                    is_dup = weather_event_exists("Data_Gov", rec_id)
                else:
                    is_dup = data_gov_rainfall_record_exists(rec_id)

            if is_dup:
                skipped_duplicates += 1
                details.append({
                    "source_record_id": rec_id,
                    "state": normalized["state"],
                    "district": normalized["district"],
                    "date": normalized["observation_date"].isoformat(),
                    "status": "skipped",
                    "reason": "duplicate_record",
                })
                continue

            # 4. Dry-run mode
            if dry_run:
                successful += 1
                details.append({
                    "source_record_id": rec_id,
                    "state": normalized["state"],
                    "district": normalized["district"],
                    "date": normalized["observation_date"].isoformat(),
                    "rainfall_mm": normalized["rainfall_mm"],
                    "status": "dry_run",
                })
                continue

            # 5. Persist to chosen target table
            if target_table == "weather_events":
                weather_dict = normalize_data_gov_to_weather_event(normalized)
                from services.weather_event_service import insert_weather_event
                inserted = insert_weather_event(weather_dict)
                successful += 1
                details.append({
                    "event_id": inserted.get("event_id"),
                    "source_record_id": rec_id,
                    "status": "inserted",
                    "target_table": "weather_events",
                })
            else:
                inserted = insert_data_gov_rainfall_record(normalized)
                successful += 1
                details.append({
                    "record_id": inserted.get("record_id"),
                    "source_record_id": rec_id,
                    "status": "inserted",
                    "target_table": "data_gov_rainfall_records",
                })

        except Exception as exc:
            failed += 1
            sanitized_err = sanitize_data_gov_message(str(exc))
            details.append({
                "status": "failed",
                "error": sanitized_err,
                "raw_record": raw_rec,
            })

    if failed == 0:
        status_label = "dry_run" if dry_run else "success"
    elif successful > 0 or skipped_duplicates > 0:
        status_label = "partial"
    else:
        status_label = "failed"

    return {
        "status": status_label,
        "message": (
            f"Processed {len(records_list)} record(s): {successful} inserted/validated, "
            f"{skipped_duplicates} duplicate(s) skipped, {failed} failed."
        ),
        "resource_id": target_res,
        "target_table": target_table,
        "total_fetched": len(records_list),
        "successful_ingested": successful,
        "skipped_duplicates": skipped_duplicates,
        "failed_records": failed,
        "dry_run": dry_run,
        "details": details,
    }
