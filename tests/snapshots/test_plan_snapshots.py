import json
from pathlib import Path

import pytest

from app.rules import build_plan
from app.schemas import PlanRequest

pytestmark = pytest.mark.unit
PERSONAS = {
    "kolkata_children_biomass_380": dict(
        location="Kolkata",
        aqi=380,
        household="young_children",
        health_factors=[],
        commute="public_transport",
        cooking_fuel="biomass",
        budget="very_low",
    ),
    "adult_wfh_120": dict(
        location="Pune",
        aqi=120,
        household="adults",
        health_factors=[],
        commute="work_from_home",
        cooking_fuel="induction",
        budget="moderate",
    ),
    "elderly_heart_301": dict(
        location="Delhi",
        aqi=301,
        household="elderly",
        health_factors=["heart"],
        commute="car",
        cooking_fuel="lpg",
        budget="moderate",
    ),
    "two_wheeler_adult_250": dict(
        location="Jaipur",
        aqi=250,
        household="adults",
        health_factors=[],
        commute="two_wheeler",
        cooking_fuel="piped_gas",
        budget="flexible",
    ),
    "family_severe_low_budget": dict(
        location="Kanpur",
        aqi=500,
        household="children_and_elderly",
        health_factors=["asthma"],
        commute="walk_cycle",
        cooking_fuel="biomass",
        budget="very_low",
    ),
}
SNAPSHOT_DIR = Path(__file__).parent / "personas"


@pytest.mark.parametrize("name,payload", PERSONAS.items())
def test_plan_matches_persona_snapshot(name, payload):
    actual = build_plan(PlanRequest(**payload)).model_dump(mode="json")
    expected = json.loads((SNAPSHOT_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert actual == expected
