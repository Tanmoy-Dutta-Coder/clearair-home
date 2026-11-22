import pytest

from app.rules import aqi_band, build_plan
from app.schemas import BudgetTier, CookingFuel, HealthFactor, HouseholdType


@pytest.mark.unit
@pytest.mark.parametrize(
    "aqi,band",
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
def test_aqi_band_returns_expected_band_at_each_boundary(aqi, band):
    assert aqi_band(aqi) == band


@pytest.mark.unit
@pytest.mark.parametrize(
    "household",
    [
        HouseholdType.YOUNG_CHILDREN,
        HouseholdType.ELDERLY,
        HouseholdType.CHILDREN_AND_ELDERLY,
    ],
)
def test_indoor_exercise_advice_for_vulnerable_household(valid_request, household):
    plan = build_plan(valid_request.model_copy(update={"household": household, "aqi": 100}))
    assert any("strictly indoors" in item.action for item in plan.routine)


@pytest.mark.unit
@pytest.mark.parametrize(
    "budget,expected",
    [
        (BudgetTier.VERY_LOW, "DIY box fan"),
        (BudgetTier.MODERATE, "True HEPA"),
        (BudgetTier.FLEXIBLE, "multi-room True HEPA"),
    ],
)
def test_indoor_filtration_recommendation_matches_budget(valid_request, budget, expected):
    plan = build_plan(valid_request.model_copy(update={"budget": budget}))
    assert any(expected.lower() in item.action.lower() for item in plan.indoor)


@pytest.mark.unit
def test_biomass_with_low_budget_gets_immediate_exposure_reduction_advice(
    valid_request,
):
    plan = build_plan(
        valid_request.model_copy(update={"cooking_fuel": CookingFuel.BIOMASS, "budget": BudgetTier.VERY_LOW})
    )
    assert any("outdoors" in item.action.lower() or "chimney" in item.action.lower() for item in plan.swaps)


@pytest.mark.unit
def test_health_factor_gets_medical_preparedness_note(valid_request):
    plan = build_plan(valid_request.model_copy(update={"aqi": 50, "health_factors": [HealthFactor.ASTHMA]}))
    assert any("medical kit" in item.action.lower() for item in plan.routine)


@pytest.mark.unit
def test_every_plan_section_has_at_least_three_items_and_hedged_impacts(valid_request):
    plan = build_plan(valid_request)
    for section in (plan.routine, plan.indoor, plan.swaps):
        assert len(section) >= 3
        for item in section:
            impact = item.impact.lower()
            assert any(word in impact for word in ("roughly", "about", "avoids", "zero direct"))
            assert "basis" in impact
