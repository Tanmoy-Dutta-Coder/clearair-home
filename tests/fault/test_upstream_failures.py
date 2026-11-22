import json
from unittest.mock import MagicMock

import httpx
import pytest

from app import aqi_provider, llm
from app.rules import build_plan

pytestmark = pytest.mark.fault


@pytest.fixture
def mock_http_client(monkeypatch):
    def install(response=None, exception=None):
        response_context = MagicMock()
        response_context.__enter__.return_value = response_context
        if exception is not None:
            response_context.get.side_effect = exception
        else:
            response_context.get.return_value = response
        monkeypatch.setattr(httpx, "Client", lambda **_kwargs: response_context)
        return response_context

    return install


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("timeout"),
        RuntimeError("429 rate limited"),
        RuntimeError("500 upstream"),
    ],
)
def test_gemini_failures_fall_back_to_baseline(monkeypatch, valid_request, error):
    baseline = build_plan(valid_request)
    client = MagicMock()
    client.models.generate_content.side_effect = error
    monkeypatch.setattr(llm, "_get_genai_client", lambda: client)
    result = llm.personalise_plan(valid_request, baseline)
    assert result.used_ai is False
    assert result.model_dump(exclude={"used_ai"}) == baseline.model_dump(exclude={"used_ai"})


@pytest.mark.parametrize(
    "body",
    ["not json", {"current": {"pm2_5": 1}}, {"current": {"pm2_5": {}, "pm10": 2}}, []],
)
def test_aqi_malformed_or_wrong_type_response_is_normalized(mock_http_client, body):
    response = MagicMock(status_code=200)
    if body == "not json":
        response.json.side_effect = json.JSONDecodeError("invalid", "not json", 0)
    else:
        response.json.return_value = body
    mock_http_client(response=response)
    with pytest.raises(aqi_provider.AqiUnavailable):
        aqi_provider.fetch_pm(28.6, 77.2)


@pytest.mark.parametrize(
    "current",
    [
        {"pm2_5": float("nan"), "pm10": 2},
        {"pm2_5": float("inf"), "pm10": 2},
        {"pm2_5": -1, "pm10": 2},
    ],
)
def test_aqi_non_finite_or_negative_upstream_values_are_normalized(mock_http_client, current):
    response = MagicMock(status_code=200)
    response.json.return_value = {"current": current}
    mock_http_client(response=response)

    with pytest.raises(aqi_provider.AqiUnavailable):
        aqi_provider.fetch_pm(28.6, 77.2)


@pytest.mark.parametrize(
    "result",
    [
        {"latitude": float("nan"), "longitude": 77.2, "name": "Delhi"},
        {"latitude": 91, "longitude": 77.2, "name": "Delhi"},
        {"latitude": 28.6, "longitude": 181, "name": "Delhi"},
        {"latitude": 28.6, "longitude": 77.2, "name": []},
    ],
)
def test_invalid_geocoder_result_is_normalized(mock_http_client, result):
    response = MagicMock(status_code=200)
    response.json.return_value = {"results": [result]}
    mock_http_client(response=response)

    with pytest.raises(aqi_provider.AqiUnavailable):
        aqi_provider.geocode("Delhi")


@pytest.mark.parametrize("error", [httpx.TimeoutException("timeout"), httpx.ConnectError("DNS failure")])
def test_aqi_network_failures_are_normalized(mock_http_client, error):
    mock_http_client(exception=error)
    with pytest.raises(aqi_provider.AqiUnavailable):
        aqi_provider.fetch_pm(28.6, 77.2)


def test_gemini_empty_and_oversized_malformed_output_fall_back(monkeypatch, valid_request):
    baseline = build_plan(valid_request)
    for output in ("", "x" * 100_000):
        client = MagicMock()
        client.models.generate_content.return_value.text = output
        monkeypatch.setattr(llm, "_get_genai_client", lambda client=client: client)
        result = llm.personalise_plan(valid_request, baseline)
        assert result.used_ai is False
        assert result.model_dump(exclude={"used_ai"}) == baseline.model_dump(exclude={"used_ai"})
