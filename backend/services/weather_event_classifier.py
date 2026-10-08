"""
Deterministic weather event classification service for Open-Meteo observations.
Maps meteorological measurements and WMO weather codes into standard event types:
- Rainfall
- Heavy Rain
- Thunderstorm
- Flooding
- Heatwave
- Fog
- Dust Storm
- Strong Wind
- Cyclone
- Other

All rules are deterministic, conservative, and adhere to official WMO 4677 code standards.
"""

from typing import Any, Dict, Optional, Set

# --- Classification Thresholds & Reference Constants ---

# Rainfall thresholds
HEAVY_RAIN_MM_THRESHOLD: float = 15.0  # mm/hr: Intense/violent precipitation rate
RAINFALL_MIN_MM_THRESHOLD: float = 0.1  # mm: Trace measurable precipitation

# Wind speed thresholds (km/h)
STRONG_WIND_KMH_THRESHOLD: float = 45.0  # km/h: Beaufort 6+ (Strong breeze to near-gale)
CYCLONE_MIN_WIND_KMH: float = 62.0  # km/h: IMD Cyclonic storm minimum sustained speed
CYCLONE_MAX_PRESSURE_HPA: float = 985.0  # hPa: Deep cyclonic depression requirement

# Temperature thresholds (°C)
HEATWAVE_MIN_TEMP_CELSIUS: float = 45.0  # °C: Severe absolute heatwave threshold for plains

# Official WMO 4677 Weather Code Sets (as supported by Open-Meteo)
THUNDERSTORM_WMO_CODES: Set[int] = {
    95,  # Thunderstorm: Slight or moderate
    96,  # Thunderstorm with slight hail
    99,  # Thunderstorm with heavy hail
}

HEAVY_RAIN_WMO_CODES: Set[int] = {
    65,  # Rain: Heavy intensity
    82,  # Rain showers: Violent
}

RAINFALL_WMO_CODES: Set[int] = {
    51,  # Drizzle: Light
    53,  # Drizzle: Moderate
    55,  # Drizzle: Dense intensity
    56,  # Freezing Drizzle: Light
    57,  # Freezing Drizzle: Dense intensity
    61,  # Rain: Slight
    63,  # Rain: Moderate
    66,  # Freezing Rain: Light
    67,  # Freezing Rain: Heavy
    80,  # Rain showers: Slight
    81,  # Rain showers: Moderate
}

FOG_WMO_CODES: Set[int] = {
    45,  # Fog
    48,  # Depositing rime fog
}

DUST_STORM_WMO_CODES: Set[int] = {
    30,  # Slight or moderate duststorm/sandstorm
    31,  # Duststorm/sandstorm no change
    32,  # Duststorm/sandstorm increasing
    33,  # Severe duststorm/sandstorm
    34,  # Severe duststorm/sandstorm no change
    35,  # Severe duststorm/sandstorm increasing
}

# Complete list of allowable event types
ALLOWED_EVENT_TYPES: Set[str] = {
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


def classify_weather_event(
    weather_code: Optional[int] = None,
    rainfall: Optional[float] = None,
    wind_speed: Optional[float] = None,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    pressure: Optional[float] = None,
) -> str:
    """
    Classify observed meteorological parameters into a standard event_type.

    Evaluation Priority:
    1. Cyclone: Requires both cyclonic wind (>= 62 km/h) AND extreme pressure depression (<= 985 hPa).
    2. Thunderstorm: WMO codes 95, 96, 99.
    3. Heavy Rain: WMO codes 65, 82 OR precipitation >= 15 mm.
    4. Rainfall: WMO rain/drizzle codes OR precipitation > 0.1 mm.
    5. Fog: WMO codes 45, 48.
    6. Dust Storm: WMO codes 30-35.
    7. Strong Wind: Wind speed >= 45 km/h.
    8. Heatwave: Temperature >= 45.0 °C.
    9. Other: Default for normal/clear conditions or when data is insufficient.

    Note on Flooding:
    Open-Meteo provides atmospheric conditions rather than ground hydrological or
    water-level observations. Flooding is never inferred merely from atmospheric rainfall.

    Returns:
        str: One of the allowed event_type values.
    """
    # 1. Cyclone (Strict: requires severe gale/cyclonic wind AND extreme low pressure)
    if (
        wind_speed is not None
        and wind_speed >= CYCLONE_MIN_WIND_KMH
        and pressure is not None
        and pressure <= CYCLONE_MAX_PRESSURE_HPA
    ):
        return "Cyclone"

    # 2. Thunderstorm (Direct WMO thunderstorm codes)
    if weather_code in THUNDERSTORM_WMO_CODES:
        return "Thunderstorm"

    # 3. Heavy Rain (Direct heavy rain code or high precipitation rate)
    if weather_code in HEAVY_RAIN_WMO_CODES or (
        rainfall is not None and rainfall >= HEAVY_RAIN_MM_THRESHOLD
    ):
        return "Heavy Rain"

    # 4. Rainfall (Standard rain/drizzle codes or measurable precipitation)
    if weather_code in RAINFALL_WMO_CODES or (
        rainfall is not None and rainfall > RAINFALL_MIN_MM_THRESHOLD
    ):
        return "Rainfall"

    # 5. Fog
    if weather_code in FOG_WMO_CODES:
        return "Fog"

    # 6. Dust Storm
    if weather_code in DUST_STORM_WMO_CODES:
        return "Dust Storm"

    # 7. Strong Wind (High wind speed without thunderstorm/cyclone)
    if wind_speed is not None and wind_speed >= STRONG_WIND_KMH_THRESHOLD:
        return "Strong Wind"

    # 8. Heatwave (Severe absolute temperature threshold)
    if temperature is not None and temperature >= HEATWAVE_MIN_TEMP_CELSIUS:
        return "Heatwave"

    # 9. Default: Other (Clear, partly cloudy, overcast, or non-hazardous conditions)
    return "Other"


def classify_open_meteo_observation(current: Dict[str, Any]) -> str:
    """
    Extract observation variables from Open-Meteo 'current' payload
    and return the classified event_type.
    """
    return classify_weather_event(
        weather_code=current.get("weather_code"),
        rainfall=current.get("precipitation"),
        wind_speed=current.get("wind_speed_10m"),
        temperature=current.get("temperature_2m"),
        humidity=current.get("relative_humidity_2m"),
        pressure=current.get("pressure_msl"),
    )


def normalize_event_type(raw_event_type: str) -> str:
    """
    Normalize event type against ALLOWED_EVENT_TYPES.
    Matches case-insensitively and maps to the official canonical title.
    If no standard match is found, preserves the stripped event type.
    """
    trimmed = raw_event_type.strip()
    for allowed in ALLOWED_EVENT_TYPES:
        if trimmed.lower() == allowed.lower():
            return allowed
    return trimmed

