import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import PlanResponse

pytestmark = [pytest.mark.smoke, pytest.mark.api]


def test_health_dashboard_and_plan_smoke_under_ten_seconds(monkeypatch):
    payload = {
        "location": "Delhi",
        "aqi": 320,
        "household": "adults",
        "commute": "car",
        "cooking_fuel": "lpg",
        "budget": "moderate",
    }
    monkeypatch.setattr("app.main.personalise_plan", lambda request, baseline: baseline)
    started = time.perf_counter()
    with TestClient(app) as client:
        health = client.get("/healthz")
        home = client.get("/")
        plan = client.post("/api/plan", json=payload)
    elapsed = time.perf_counter() - started
    assert health.status_code == 200
    assert home.status_code == 200 and "ClearAir Home" in home.text
    assert plan.status_code == 200
    PlanResponse.model_validate(plan.json())
    assert plan.json()["aqi_band"] == "Very Poor"
    assert elapsed < 10
