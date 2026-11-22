"""Behavioural tests for the deterministic AQI plan rules."""

import pytest

from app.rules import aqi_band, build_plan
from app.schemas import BudgetTier, CookingFuel, HealthFactor

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("aqi", "expected_band"),
    [
        (0, "Good"),
        (50, "Good"),
        (51, "Satisfactory"),
        (100, "Satisfactory"),
        (101, "Moderate"),
        (200, "Moderate"),
        (201, "Poor"),
        (300, "Poor"),
        (301, "Very Poor"),
        (400, "Very Poor"),
        (401, "Severe"),
        (500, "Severe"),
    ],
)
def test_aqi_band_uses_expected_category_at_every_boundary(aqi, expected_band):
    assert aqi_band(aqi) == expected_band


def test_n95_advice_appears_only_above_threshold(valid_request):
    at_threshold = build_plan(valid_request.model_copy(update={"aqi": 200}))
    above_threshold = build_plan(valid_request.model_copy(update={"aqi": 201}))

    assert not any("N95" in item.action or "FFP2" in item.action for item in at_threshold.routine)
    assert any("N95" in item.action or "FFP2" in item.action for item in above_threshold.routine)


@pytest.mark.parametrize("health_factor", list(HealthFactor))
def test_medical_help_note_appears_for_each_health_factor(valid_request, health_factor):
    plan = build_plan(valid_request.model_copy(update={"aqi": 100, "health_factors": [health_factor]}))

    assert any("medical kit" in item.action.lower() for item in plan.routine)


def test_medical_help_note_appears_above_aqi_300(valid_request):
    plan = build_plan(valid_request.model_copy(update={"aqi": 301, "health_factors": []}))

    assert any("medical kit" in item.action.lower() for item in plan.routine)


def test_biomass_fuel_triggers_clean_cooking_switch_advice(valid_request):
    plan = build_plan(
        valid_request.model_copy(update={"cooking_fuel": CookingFuel.BIOMASS, "budget": BudgetTier.MODERATE})
    )

    assert any("transition from biomass" in item.action.lower() for item in plan.swaps)


def test_very_low_budget_never_recommends_purifier_purchase(valid_request):
    plan = build_plan(valid_request.model_copy(update={"budget": BudgetTier.VERY_LOW}))

    assert not any("purchase" in item.action.lower() or "buy" in item.action.lower() for item in plan.indoor)
    assert any("diy box fan filter" in item.action.lower() for item in plan.indoor)


def test_each_plan_section_has_three_items_and_hedged_impacts(valid_request):
    plan = build_plan(valid_request)
    hedge_words = ("roughly", "about", "approximately", "may", "might", "can", "could", "zero direct")

    for section in (plan.routine, plan.indoor, plan.swaps):
        assert len(section) >= 3
        assert all(any(word in item.impact.lower() for word in hedge_words) for item in section)
