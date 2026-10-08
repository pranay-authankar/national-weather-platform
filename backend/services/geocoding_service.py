"""
Service module for reverse geocoding geographic coordinates to administrative divisions.
Determines city, district, and state from latitude and longitude.

Designed modularly with an abstract provider interface (BaseGeocodingProvider)
to enable plugging in alternative geocoding providers in the future.
Default implementation uses the OpenStreetMap Nominatim reverse geocoding API.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, Optional, TypedDict
import httpx

logger = logging.getLogger(__name__)


class GeocodedLocation(TypedDict):
    """
    Structured dictionary containing resolved administrative location fields.
    """
    city: Optional[str]
    district: Optional[str]
    state: Optional[str]


def _clean_str(value: Any) -> Optional[str]:
    """
    Trim whitespace and convert empty strings or None to None.
    """
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned if cleaned else None


class BaseGeocodingProvider(ABC):
    """
    Abstract base class for reverse-geocoding service providers.
    Enables modularity and provider replacement (e.g., Nominatim, BigDataCloud, Google Maps, Mapbox).
    """

    @abstractmethod
    async def reverse_geocode(self, latitude: float, longitude: float) -> GeocodedLocation:
        """
        Reverse-geocode coordinates to city, district, and state.

        Args:
            latitude: Latitude coordinate (-90.0 to 90.0).
            longitude: Longitude coordinate (-180.0 to 180.0).

        Returns:
            GeocodedLocation dictionary with city, district, and state (or None if unresolved).
        """
        pass


class NominatimGeocodingProvider(BaseGeocodingProvider):
    """
    Reverse-geocoding provider using the OpenStreetMap Nominatim REST API.
    A free, real-world geocoding service with global and India administrative boundary support.
    """

    NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
    DEFAULT_TIMEOUT_SECONDS = 5.0
    DEFAULT_USER_AGENT = "NationalWeatherPlatform/1.0 (contact: geocoding@nationalweather.gov.in)"

    def __init__(
        self,
        base_url: str = NOMINATIM_REVERSE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    async def reverse_geocode(self, latitude: float, longitude: float) -> GeocodedLocation:
        """
        Query OpenStreetMap Nominatim to reverse-geocode coordinates.
        Safely extracts city, district, and state.
        Never raises exceptions; returns all None on failure.
        """
        # Validate coordinates range
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            logger.warning(
                "Invalid coordinates passed to Nominatim geocoding: lat=%s, lon=%s",
                latitude,
                longitude,
            )
            return {"city": None, "district": None, "state": None}

        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
        }
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.base_url, params=params, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    "Nominatim reverse geocode returned HTTP %s for (%s, %s): %s",
                    response.status_code,
                    latitude,
                    longitude,
                    response.text[:200],
                )
                return {"city": None, "district": None, "state": None}

            data = response.json()
            if not isinstance(data, dict):
                logger.warning(
                    "Unexpected response structure from Nominatim for (%s, %s)",
                    latitude,
                    longitude,
                )
                return {"city": None, "district": None, "state": None}

            # Nominatim returns {"error": "..."} when coordinates cannot be geocoded (e.g. open waters)
            if "error" in data:
                logger.info(
                    "Nominatim could not geocode (%s, %s): %s",
                    latitude,
                    longitude,
                    data.get("error"),
                )
                return {"city": None, "district": None, "state": None}

            address = data.get("address", {})
            return self._extract_administrative_divisions(address)

        except httpx.TimeoutException:
            logger.warning(
                "Nominatim reverse geocode timed out after %s seconds for (%s, %s)",
                self.timeout_seconds,
                latitude,
                longitude,
            )
            return {"city": None, "district": None, "state": None}
        except httpx.RequestError as exc:
            logger.warning(
                "Network error connecting to Nominatim for (%s, %s): %s",
                latitude,
                longitude,
                exc,
            )
            return {"city": None, "district": None, "state": None}
        except Exception as exc:
            logger.warning(
                "Unexpected error in Nominatim reverse geocode for (%s, %s): %s",
                latitude,
                longitude,
                exc,
            )
            return {"city": None, "district": None, "state": None}

    def _extract_administrative_divisions(self, address: Dict[str, Any]) -> GeocodedLocation:
        """
        Extract city, district, and state from an OSM address dictionary.

        Extraction rules:
        - city: Priority from city -> town -> municipality -> village -> suburb -> hamlet -> city_district.
        - district: Priority from state_district -> district -> county.
        - state: Priority from state -> province -> state_code.
        """
        city = (
            _clean_str(address.get("city"))
            or _clean_str(address.get("town"))
            or _clean_str(address.get("municipality"))
            or _clean_str(address.get("village"))
            or _clean_str(address.get("suburb"))
            or _clean_str(address.get("hamlet"))
            or _clean_str(address.get("city_district"))
        )

        district = (
            _clean_str(address.get("state_district"))
            or _clean_str(address.get("district"))
            or _clean_str(address.get("county"))
        )

        state = (
            _clean_str(address.get("state"))
            or _clean_str(address.get("province"))
            or _clean_str(address.get("state_code"))
        )

        return {
            "city": city,
            "district": district,
            "state": state,
        }


# Modular provider instance registry
_active_provider: BaseGeocodingProvider = NominatimGeocodingProvider()


def get_geocoding_provider() -> BaseGeocodingProvider:
    """
    Get the currently active geocoding provider.
    """
    return _active_provider


def set_geocoding_provider(provider: BaseGeocodingProvider) -> None:
    """
    Configure a custom geocoding provider (e.g. for testing or switching vendors).
    """
    global _active_provider
    _active_provider = provider


async def reverse_geocode(
    latitude: float,
    longitude: float,
    provider: Optional[BaseGeocodingProvider] = None,
) -> GeocodedLocation:
    """
    Public interface for reverse-geocoding coordinates to city, district, and state.

    Guarantees:
    - Automatically handles timeouts and network exceptions safely.
    - If geocoding fails or is unavailable, returns city=None, district=None, state=None.
    - Never invents, guesses, or fabricates locations.
    - Does not raise exceptions to the caller.
    """
    try:
        current_provider = provider or get_geocoding_provider()
        return await current_provider.reverse_geocode(latitude=latitude, longitude=longitude)
    except Exception as exc:
        logger.warning(
            "Safely handled top-level exception in reverse_geocode (%s, %s): %s",
            latitude,
            longitude,
            exc,
        )
        return {"city": None, "district": None, "state": None}
