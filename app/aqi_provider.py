"""AQI auto-detection provider using Open-Meteo and Indian CPCB breakpoints.

Fetches modelled PM2.5 and PM10 for a geographic location or approximate coordinates,
converts concentrations to the Indian National Air Quality Index (NAQI) scale, and
maintains an in-memory TTL cache. Purely optional; manual user input remains the primary fallback.
"""

import logging
import math
import re
import threading
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

import httpx

from app.rules import aqi_band

logger = logging.getLogger(__name__)

# Network & Host Whitelist Constraints
ALLOWED_HOSTS = {
    "geocoding-api.open-meteo.com",
    "air-quality-api.open-meteo.com",
}
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
REQUEST_TIMEOUT_SECONDS = 3.0

# In-Memory TTL Cache Configuration
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes
CACHE_MAX_ENTRIES = 256
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.RLock()

# Indian CPCB Breakpoint Tables (Concentration Low, High, Index Low, High)
# PM2.5 (24-hour average µg/m³) -> Sub-Index
PM25_BREAKPOINTS = [
    (0.0, 30.0, 0, 50),
    (30.1, 60.0, 51, 100),
    (60.1, 90.0, 101, 200),
    (90.1, 120.0, 201, 300),
    (120.1, 250.0, 301, 400),
    (250.1, 500.0, 401, 500),
]

# PM10 (24-hour average µg/m³) -> Sub-Index
PM10_BREAKPOINTS = [
    (0.0, 50.0, 0, 50),
    (50.1, 100.0, 51, 100),
    (100.1, 250.0, 101, 200),
    (250.1, 350.0, 201, 300),
    (350.1, 430.0, 301, 400),
    (430.1, 500.0, 401, 500),
]


class AqiUnavailable(Exception):
    """Raised when AQI cannot be fetched, geocoded, or calculated."""


def _calculate_sub_index(conc: float, breakpoints: Sequence[tuple[float, float, int, int]]) -> float:
    """Linearly interpolate sub-index for a pollutant concentration."""
    if not math.isfinite(conc) or conc < 0:
        raise ValueError("Pollutant concentration must be a finite non-negative number")
    if conc <= 0:
        return 0.0

    for c_low, c_high, i_low, i_high in breakpoints:
        if conc <= c_high:
            return float(i_low + ((i_high - i_low) / (c_high - c_low)) * (conc - c_low))

    # Above highest tier
    last_c_low, last_c_high, last_i_low, last_i_high = breakpoints[-1]
    extrapolated = last_i_low + ((last_i_high - last_i_low) / (last_c_high - last_c_low)) * (conc - last_c_low)
    return min(500.0, max(0.0, extrapolated))


def pm_to_indian_aqi(pm2_5: float, pm10: float) -> int:
    """Calculate Indian AQI from PM2.5 and PM10 concentrations using CPCB breakpoints.

    Args:
        pm2_5: Particulate matter 2.5 concentration in µg/m³.
        pm10: Particulate matter 10 concentration in µg/m³.

    Returns:
        Integer AQI value bounded between 0 and 500.
    """
    sub_pm25 = _calculate_sub_index(pm2_5, PM25_BREAKPOINTS)
    sub_pm10 = _calculate_sub_index(pm10, PM10_BREAKPOINTS)
    aqi_float = max(sub_pm25, sub_pm10)
    return round(min(500.0, max(0.0, aqi_float)))


def _check_allowed_url(url: str) -> None:
    """Verify that target URL belongs strictly to allowed Open-Meteo domains."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.port not in (None, 443):
        raise AqiUnavailable(f"Restricted domain rejected: {parsed.hostname}")


def geocode(place: str) -> tuple[float, float, str]:
    """Geocode a place name into latitude, longitude, and display name.

    Never logs the place name for user privacy.
    """
    _check_allowed_url(GEOCODING_URL)
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False) as client:
            resp = client.get(
                GEOCODING_URL,
                params={"name": place, "count": 1, "language": "en", "format": "json"},
            )
            if resp.status_code != 200:
                raise AqiUnavailable(f"Geocoding returned HTTP {resp.status_code}")

            data = resp.json()
            results = data.get("results")
            if not results:
                raise AqiUnavailable("Place location not found")

            first = results[0]
            lat = float(first["latitude"])
            lon = float(first["longitude"])
            display_name = first.get("name", "Unknown Area")
            if not math.isfinite(lat) or not -90 <= lat <= 90 or not math.isfinite(lon) or not -180 <= lon <= 180:
                raise ValueError("Geocoder returned invalid coordinates")
            if not isinstance(display_name, str) or not display_name.strip():
                raise ValueError("Geocoder returned an invalid place name")
            return lat, lon, display_name

    except (httpx.RequestError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning("Geocoding service unavailable (%s)", type(e).__name__)
        raise AqiUnavailable("Geocoding failed") from e


def fetch_pm(lat: float, lon: float) -> tuple[float, float, str]:
    """Fetch current PM2.5 and PM10 levels from Open-Meteo air quality API.

    Coordinates are not logged to protect user privacy.
    """
    _check_allowed_url(AIR_QUALITY_URL)
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False) as client:
            resp = client.get(
                AIR_QUALITY_URL,
                params={"latitude": lat, "longitude": lon, "current": "pm10,pm2_5"},
            )
            if resp.status_code != 200:
                raise AqiUnavailable(f"Air quality API returned HTTP {resp.status_code}")

            data = resp.json()
            current = data.get("current")
            if not current or "pm2_5" not in current or "pm10" not in current:
                raise AqiUnavailable("Current PM metrics unavailable")

            pm2_5 = float(current["pm2_5"])
            pm10 = float(current["pm10"])
            if not math.isfinite(pm2_5) or pm2_5 < 0 or not math.isfinite(pm10) or pm10 < 0:
                raise ValueError("Air quality API returned invalid particulate levels")
            observed_at = str(current.get("time", "Current"))
            return pm2_5, pm10, observed_at

    except (httpx.RequestError, ValueError, KeyError, TypeError, AttributeError) as e:
        logger.warning("Air quality metrics unavailable (%s)", type(e).__name__)
        raise AqiUnavailable("Air quality metric lookup failed") from e


def _get_from_cache(cache_key: str) -> dict[str, Any] | None:
    """Retrieve entry from in-memory TTL cache if not expired."""
    with _CACHE_LOCK:
        now = time.time()
        if cache_key in _CACHE:
            timestamp, data = _CACHE[cache_key]
            if now - timestamp < CACHE_TTL_SECONDS:
                return data.copy()
            del _CACHE[cache_key]
        return None


def _set_in_cache(cache_key: str, data: dict[str, Any]) -> None:
    """Store entry in in-memory TTL cache with eviction."""
    if CACHE_MAX_ENTRIES < 1:
        return
    with _CACHE_LOCK:
        now = time.time()
        if cache_key not in _CACHE and len(_CACHE) >= CACHE_MAX_ENTRIES:
            # Evict the least recently stored entry.
            oldest_key = min(_CACHE.keys(), key=lambda k: _CACHE[k][0])
            del _CACHE[oldest_key]
        _CACHE[cache_key] = (now, data.copy())


def detect_aqi(place: str) -> dict[str, Any]:
    """Detect current Indian AQI for a given place name with TTL caching.

    Args:
        place: Cleaned string place/city name.

    Returns:
        Dict containing aqi, band, source, observed_at, and area.

    Raises:
        AqiUnavailable: If geocoding or air quality data is unreachable.
    """
    clean_key = re.sub(r"\s+", " ", place.strip().lower())
    cached = _get_from_cache(clean_key)
    if cached is not None:
        return cached

    lat, lon, display_name = geocode(place)
    pm2_5, pm10, observed_at = fetch_pm(lat, lon)
    calculated_aqi = pm_to_indian_aqi(pm2_5, pm10)
    calculated_band = aqi_band(calculated_aqi)

    result = {
        "aqi": calculated_aqi,
        "band": calculated_band,
        "source": "Open-Meteo",
        "observed_at": observed_at,
        "area": display_name,
    }

    _set_in_cache(clean_key, result)
    return result


def detect_aqi_by_coords(lat: float, lon: float) -> dict[str, Any]:
    """Detect current Indian AQI for approximate coordinates with TTL caching.

    Coordinates are rounded to 2 decimal places (~1 km grid) before lookup and caching.
    Never logs raw coordinates.

    Args:
        lat: Latitude between -90 and 90.
        lon: Longitude between -180 and 180.

    Returns:
        Dict matching the AQI response shape with approximate_location=True.

    Raises:
        AqiUnavailable: If air quality data cannot be fetched.
    """
    if not math.isfinite(lat) or not -90 <= lat <= 90 or not math.isfinite(lon) or not -180 <= lon <= 180:
        raise AqiUnavailable("Coordinates must be finite values within latitude and longitude bounds")
    lat_r = round(lat, 2)
    lon_r = round(lon, 2)
    cache_key = f"coords:{lat_r:.2f}:{lon_r:.2f}"

    cached = _get_from_cache(cache_key)
    if cached is not None:
        return cached

    pm2_5, pm10, observed_at = fetch_pm(lat_r, lon_r)
    calculated_aqi = pm_to_indian_aqi(pm2_5, pm10)
    calculated_band = aqi_band(calculated_aqi)

    result = {
        "aqi": calculated_aqi,
        "band": calculated_band,
        "source": "Open-Meteo",
        "observed_at": observed_at,
        "area": "Your current location (approx.)",
        "approximate_location": True,
    }

    _set_in_cache(cache_key, result)
    return result
