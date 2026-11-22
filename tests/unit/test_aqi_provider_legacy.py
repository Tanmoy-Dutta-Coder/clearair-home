"""Unit tests for the AQI provider, CPCB breakpoint formulas, and caching."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.aqi_provider import (
    _CACHE,
    AqiUnavailable,
    detect_aqi,
    detect_aqi_by_coords,
    fetch_pm,
    geocode,
    pm_to_indian_aqi,
)

pytestmark = pytest.mark.unit


def setup_function():
    """Clear in-memory cache before every test."""
    _CACHE.clear()


def test_pm_to_indian_aqi_pm25_breakpoints():
    """Test CPCB PM2.5 breakpoints across all Indian AQI categories."""
    assert pm_to_indian_aqi(0.0, 0.0) == 0
    assert pm_to_indian_aqi(15.0, 0.0) == 25
    assert pm_to_indian_aqi(30.0, 0.0) == 50

    assert 51 <= pm_to_indian_aqi(31.0, 0.0) <= 60
    assert pm_to_indian_aqi(60.0, 0.0) == 100

    assert 101 <= pm_to_indian_aqi(61.0, 0.0) <= 110
    assert pm_to_indian_aqi(90.0, 0.0) == 200

    assert 201 <= pm_to_indian_aqi(91.0, 0.0) <= 210
    assert pm_to_indian_aqi(120.0, 0.0) == 300

    assert 301 <= pm_to_indian_aqi(121.0, 0.0) <= 310
    assert pm_to_indian_aqi(250.0, 0.0) == 400

    assert 401 <= pm_to_indian_aqi(251.0, 0.0) <= 410
    assert pm_to_indian_aqi(500.0, 0.0) == 500

    assert pm_to_indian_aqi(800.0, 0.0) == 500


def test_pm_to_indian_aqi_pm10_breakpoints():
    """Test CPCB PM10 breakpoints across all Indian AQI categories."""
    assert pm_to_indian_aqi(0.0, 25.0) == 25
    assert pm_to_indian_aqi(0.0, 50.0) == 50

    assert 51 <= pm_to_indian_aqi(0.0, 51.0) <= 60
    assert pm_to_indian_aqi(0.0, 100.0) == 100

    assert 101 <= pm_to_indian_aqi(0.0, 101.0) <= 110
    assert pm_to_indian_aqi(0.0, 250.0) == 200

    assert 201 <= pm_to_indian_aqi(0.0, 251.0) <= 210
    assert pm_to_indian_aqi(0.0, 350.0) == 300

    assert 301 <= pm_to_indian_aqi(0.0, 351.0) <= 310
    assert pm_to_indian_aqi(0.0, 430.0) == 400

    assert 401 <= pm_to_indian_aqi(0.0, 431.0) <= 410
    assert pm_to_indian_aqi(0.0, 500.0) == 500

    assert pm_to_indian_aqi(0.0, 950.0) == 500


def test_pm_to_indian_aqi_max_of_sub_indices():
    """Verify that overall AQI is the maximum of PM2.5 and PM10 sub-indices."""
    assert pm_to_indian_aqi(90.0, 50.0) == 200
    assert pm_to_indian_aqi(30.0, 350.0) == 300


@patch("httpx.Client")
def test_geocode_success(mock_client_class):
    """Test successful geocoding parse."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": [{"latitude": 28.6139, "longitude": 77.2090, "name": "New Delhi"}]}
    mock_client.get.return_value = mock_resp
    mock_client_class.return_value.__enter__.return_value = mock_client

    lat, lon, display = geocode("New Delhi")
    assert lat == 28.6139
    assert lon == 77.2090
    assert display == "New Delhi"


@patch("httpx.Client")
def test_geocode_not_found(mock_client_class):
    """Test geocoding error when location is missing in response."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}
    mock_client.get.return_value = mock_resp
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(AqiUnavailable):
        geocode("NonExistentCityXYZ")


@patch("httpx.Client")
def test_fetch_pm_success(mock_client_class):
    """Test successful air quality metrics fetch."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"current": {"pm2_5": 115.4, "pm10": 210.2, "time": "2026-11-23T00:00"}}
    mock_client.get.return_value = mock_resp
    mock_client_class.return_value.__enter__.return_value = mock_client

    pm2_5, pm10, observed_at = fetch_pm(28.61, 77.20)
    assert pm2_5 == 115.4
    assert pm10 == 210.2
    assert observed_at == "2026-11-23T00:00"


@patch("httpx.Client")
def test_detect_aqi_timeout_fallback(mock_client_class):
    """Verify that network timeout raises AqiUnavailable."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(AqiUnavailable):
        detect_aqi("Delhi")


@patch("app.aqi_provider.fetch_pm")
@patch("app.aqi_provider.geocode")
def test_detect_aqi_caching_hit_and_miss(mock_geocode, mock_fetch):
    """Verify that consecutive requests for same place hit TTL cache without network I/O."""
    mock_geocode.return_value = (28.61, 77.20, "Delhi")
    mock_fetch.return_value = (115.0, 210.0, "2026-11-23T00:00")

    # 1. Cache Miss (first call)
    res1 = detect_aqi("Delhi")
    assert res1["source"] == "Open-Meteo"
    assert res1["band"] in ("Poor", "Very Poor")
    assert mock_geocode.call_count == 1
    assert mock_fetch.call_count == 1

    # 2. Cache Hit (second call for same place with whitespace/case variation)
    res2 = detect_aqi("  delhi  ")
    assert res2 == res1
    assert mock_geocode.call_count == 1
    assert mock_fetch.call_count == 1


@patch("app.aqi_provider.fetch_pm")
def test_detect_aqi_by_coords_rounding_and_cache(mock_fetch):
    """Verify that coords are rounded to 2 decimals before cache lookup and fetching."""
    mock_fetch.return_value = (115.0, 210.0, "2026-11-23T00:00")

    # Call with high-precision lat/lon
    res1 = detect_aqi_by_coords(28.613891, 77.209012)
    assert res1["source"] == "Open-Meteo"
    assert res1["approximate_location"] is True
    assert res1["area"] == "Your current location (approx.)"
    assert mock_fetch.call_count == 1
    # Verify fetch_pm received rounded coordinates
    mock_fetch.assert_called_with(28.61, 77.21)

    # Second call with slightly different precision that rounds to same 2 decimals
    res2 = detect_aqi_by_coords(28.61011, 77.21499)
    assert res2 == res1
    # Call count should not have increased (cache hit)
    assert mock_fetch.call_count == 1


@patch("httpx.Client")
def test_detect_aqi_by_coords_timeout_and_error(mock_client_class):
    """Verify coords detection raises AqiUnavailable without coordinates in exception."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(AqiUnavailable) as exc_info:
        detect_aqi_by_coords(28.61, 77.21)

    # Coordinate values must not appear in exception string
    err_str = str(exc_info.value)
    assert "28.61" not in err_str
    assert "77.21" not in err_str
