"""
Service module for interacting with the Open-Meteo Forecast API.
Fetches real-time weather observations for given geographic coordinates.
"""

from typing import Any, Dict
import httpx

# Open-Meteo Forecast API Base URL
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Request timeout in seconds
REQUEST_TIMEOUT_SECONDS = 10.0


class OpenMeteoError(Exception):
    """Base exception for Open-Meteo service errors."""
    pass


class OpenMeteoTimeoutError(OpenMeteoError):
    """Raised when the Open-Meteo API request times out."""
    pass


class OpenMeteoRequestError(OpenMeteoError):
    """Raised when there is a network or connection failure."""
    pass


class OpenMeteoAPIError(OpenMeteoError):
    """Raised when the Open-Meteo API returns an HTTP error status."""
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenMeteoResponseError(OpenMeteoError):
    """Raised when the Open-Meteo API response is invalid or missing required data."""
    pass


async def fetch_open_meteo_weather(
    latitude: float,
    longitude: float,
) -> Dict[str, Any]:
    """
    Fetch current weather data from Open-Meteo for the given latitude and longitude.

    Parameters:
        latitude (float): Latitude coordinate (-90.0 to 90.0)
        longitude (float): Longitude coordinate (-180.0 to 180.0)

    Returns:
        Dict[str, Any]: Parsed response dictionary containing weather variables.

    Raises:
        ValueError: If coordinates are out of valid geographic range.
        OpenMeteoTimeoutError: If the external API request times out.
        OpenMeteoRequestError: If network connection to Open-Meteo fails.
        OpenMeteoAPIError: If Open-Meteo returns a non-200 HTTP response.
        OpenMeteoResponseError: If response body cannot be parsed or lacks expected data.
    """
    # 1. Validate latitude and longitude range
    if not (-90.0 <= latitude <= 90.0):
        raise ValueError(
            f"Invalid latitude: {latitude}. Latitude must be between -90.0 and 90.0 degrees."
        )

    if not (-180.0 <= longitude <= 180.0):
        raise ValueError(
            f"Invalid longitude: {longitude}. Longitude must be between -180.0 and 180.0 degrees."
        )

    # 2. Configure query parameters with requested weather variables and metric units
    current_variables = [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "wind_speed_10m",
        "wind_direction_10m",
        "pressure_msl",
        "weather_code",
    ]

    params: Dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(current_variables),
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "wind_speed_unit": "kmh",
    }

    # 3. Perform asynchronous HTTP request to Open-Meteo
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(OPEN_METEO_FORECAST_URL, params=params)
    except httpx.TimeoutException as exc:
        raise OpenMeteoTimeoutError("The request to Open-Meteo timed out.") from exc
    except httpx.RequestError as exc:
        raise OpenMeteoRequestError(f"Network error while reaching Open-Meteo: {exc}") from exc

    # 4. Check HTTP status code
    if response.status_code != 200:
        error_detail = response.text
        try:
            error_json = response.json()
            if "reason" in error_json:
                error_detail = error_json["reason"]
        except Exception:
            pass
        raise OpenMeteoAPIError(
            status_code=response.status_code,
            message=f"Open-Meteo returned status {response.status_code}: {error_detail}",
        )

    # 5. Parse and validate JSON response structure
    try:
        data = response.json()
    except Exception as exc:
        raise OpenMeteoResponseError("Failed to parse JSON response from Open-Meteo.") from exc

    if not isinstance(data, dict):
        raise OpenMeteoResponseError("Unexpected response format from Open-Meteo (expected JSON object).")

    if "current" not in data:
        raise OpenMeteoResponseError("Response from Open-Meteo did not contain 'current' weather data.")

    return data
