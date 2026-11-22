from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import aqi_provider, llm
from app.main import app
from app.rules import build_plan
from app.schemas import (
    BudgetTier,
    CommuteMode,
    CookingFuel,
    HouseholdType,
    PlanRequest,
    PlanResponse,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clear_provider_cache():
    aqi_provider._CACHE.clear()
    yield
    aqi_provider._CACHE.clear()


def test_rules_llm_and_schema_form_one_validated_plan(monkeypatch):
    request = PlanRequest(
        location="Delhi",
        aqi=320,
        household="adults",
        commute="car",
        cooking_fuel="lpg",
        budget="moderate",
    )
    baseline = build_plan(request)
    personalized = baseline.model_copy(update={"summary": "Personalized explanation for Delhi."})
    response = MagicMock(text=personalized.model_dump_json())
    client = MagicMock()
    client.models.generate_content.return_value = response
    monkeypatch.setattr(llm, "_get_genai_client", lambda: client)

    result = llm.personalise_plan(request, baseline)
    validated = PlanResponse.model_validate(result.model_dump())

    assert validated.used_ai is True
    assert validated.summary == "Personalized explanation for Delhi."
    for section in ("routine", "indoor", "swaps"):
        assert [item.action for item in getattr(validated, section)] == [
            item.action for item in getattr(baseline, section)
        ]


def test_mocked_aqi_result_can_drive_a_deterministic_plan(monkeypatch):
    monkeypatch.setattr(aqi_provider, "geocode", lambda place: (28.61, 77.21, "Delhi"))
    monkeypatch.setattr(aqi_provider, "fetch_pm", lambda lat, lon: (115.0, 210.0, "2026-11-23T00:00"))
    estimate = aqi_provider.detect_aqi("Delhi")
    request = PlanRequest(
        location=estimate["area"],
        aqi=estimate["aqi"],
        household=HouseholdType.YOUNG_CHILDREN,
        commute=CommuteMode.WORK_FROM_HOME,
        cooking_fuel=CookingFuel.BIOMASS,
        budget=BudgetTier.VERY_LOW,
    )
    plan = build_plan(request)

    assert estimate["source"] == "Open-Meteo"
    assert plan.aqi_band == estimate["band"]
    assert len(plan.routine) >= 3
    assert len(plan.indoor) >= 3
    assert len(plan.swaps) >= 3


def test_app_startup_and_plan_endpoint_work_without_gemini(monkeypatch):
    monkeypatch.setattr(llm.settings, "gemini_api_key", None)
    with TestClient(app) as client:
        health = client.get("/healthz")
        response = client.post(
            "/api/plan",
            json={
                "location": "Pune",
                "aqi": 120,
                "household": "adults",
                "commute": "work_from_home",
                "cooking_fuel": "induction",
                "budget": "moderate",
            },
        )

    assert health.status_code == 200
    assert response.status_code == 200
    assert response.json()["used_ai"] is False
    PlanResponse.model_validate(response.json())
