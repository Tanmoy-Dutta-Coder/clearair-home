import pytest

from app import aqi_provider as provider


@pytest.mark.unit
@pytest.mark.parametrize(
    "concentration,expected",
    [
        (0, 0),
        (30, 50),
        (30.1, 51),
        (60, 100),
        (60.1, 101),
        (90, 200),
        (90.1, 201),
        (120, 300),
        (120.1, 301),
        (250, 400),
        (250.1, 401),
        (500, 500),
        (900, 500),
    ],
)
def test_pm25_breakpoint_boundaries(concentration, expected):
    assert provider.pm_to_indian_aqi(concentration, 0) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "concentration,expected",
    [
        (0, 0),
        (50, 50),
        (50.1, 51),
        (100, 100),
        (100.1, 101),
        (250, 200),
        (250.1, 201),
        (350, 300),
        (350.1, 301),
        (430, 400),
        (430.1, 401),
        (500, 500),
        (900, 500),
    ],
)
def test_pm10_breakpoint_boundaries(concentration, expected):
    assert provider.pm_to_indian_aqi(0, concentration) == expected


@pytest.mark.unit
def test_aqi_uses_maximum_pollutant_subindex():
    assert provider.pm_to_indian_aqi(90, 50) == 200
    assert provider.pm_to_indian_aqi(30, 350) == 300


@pytest.mark.unit
def test_cache_expires_and_evicts_oldest(monkeypatch):
    provider._CACHE.clear()
    now = [100.0]
    monkeypatch.setattr(provider.time, "time", lambda: now[0])
    provider._set_in_cache("old", {"value": 1})
    now[0] += provider.CACHE_TTL_SECONDS
    assert provider._get_from_cache("old") is None
    provider.CACHE_MAX_ENTRIES = 2
    try:
        provider._set_in_cache("a", {})
        now[0] += 1
        provider._set_in_cache("b", {})
        now[0] += 1
        provider._set_in_cache("c", {})
        assert set(provider._CACHE) == {"b", "c"}
    finally:
        provider.CACHE_MAX_ENTRIES = 256
        provider._CACHE.clear()


@pytest.mark.unit
def test_coordinate_lookup_rounds_before_fetch_and_cache(monkeypatch):
    provider._CACHE.clear()
    calls = []
    monkeypatch.setattr(
        provider,
        "fetch_pm",
        lambda lat, lon: (calls.append((lat, lon)) or (30, 50, "now")),
    )
    first = provider.detect_aqi_by_coords(28.613, 77.209)
    second = provider.detect_aqi_by_coords(28.614, 77.211)
    assert calls == [(28.61, 77.21)]
    assert first == second
    provider._CACHE.clear()


@pytest.mark.unit
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -0.1])
def test_non_finite_or_negative_particulate_levels_are_rejected(value):
    with pytest.raises(ValueError, match="finite non-negative"):
        provider.pm_to_indian_aqi(value, 0)


@pytest.mark.unit
def test_refreshing_full_cache_entry_does_not_evict_other_entries(monkeypatch):
    provider._CACHE.clear()
    monkeypatch.setattr(provider, "CACHE_MAX_ENTRIES", 2)
    now = [100.0]
    monkeypatch.setattr(provider.time, "time", lambda: now[0])
    provider._set_in_cache("first", {"value": 1})
    now[0] += 1
    provider._set_in_cache("second", {"value": 2})
    now[0] += 1

    provider._set_in_cache("first", {"value": 3})

    assert set(provider._CACHE) == {"first", "second"}
    assert provider._get_from_cache("first") == {"value": 3}
    provider._CACHE.clear()


@pytest.mark.unit
def test_mutating_cached_result_does_not_corrupt_cache(monkeypatch):
    provider._CACHE.clear()
    provider._set_in_cache("safe", {"aqi": 10})

    result = provider._get_from_cache("safe")
    result["aqi"] = 999

    assert provider._get_from_cache("safe") == {"aqi": 10}
    provider._CACHE.clear()


@pytest.mark.unit
@pytest.mark.parametrize("lat,lon", [(float("nan"), 0), (91, 0), (0, 181)])
def test_coordinate_lookup_rejects_invalid_coordinates(lat, lon):
    with pytest.raises(provider.AqiUnavailable, match="Coordinates must be finite"):
        provider.detect_aqi_by_coords(lat, lon)
