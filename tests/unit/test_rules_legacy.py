"""Unit tests for the deterministic rule engine and decision matrices."""

import pytest

from app.rules import (
    AQI_MASK_THRESHOLD,
    AQI_MEDICAL_ALERT_THRESHOLD,
    aqi_band,
    build_plan,
)
from app.schemas import (
    BudgetTier,
    CommuteMode,
    CookingFuel,
    HealthFactor,
    HouseholdType,
    PlanRequest,
)

pytestmark = pytest.mark.unit
HEDGE_WORDS = ["roughly", "about", "avoids", "estimated", "typically", "zero direct"]


@pytest.mark.parametrize(
    ("lower_aqi", "lower_band", "upper_aqi", "upper_band"),
    [
        (50, "Good", 51, "Satisfactory"),
        (100, "Satisfactory", 101, "Moderate"),
        (200, "Moderate", 201, "Poor"),
        (300, "Poor", 301, "Very Poor"),
        (400, "Very Poor", 401, "Severe"),
    ],
)
def test_every_aqi_band_boundary(lower_aqi, lower_band, upper_aqi, upper_band):
    """Verify Indian CPCB AQI classifications at every precise boundary pair."""
    assert aqi_band(lower_aqi) == lower_band
    assert aqi_band(upper_aqi) == upper_band


def test_aqi_band_min_and_max():
    """Verify minimum (0) and maximum (500) valid AQI bands."""
    assert aqi_band(0) == "Good"
    assert aqi_band(500) == "Severe"


def test_aqi_band_out_of_range():
    """Verify out-of-range AQI values raise ValueError."""
    with pytest.raises(ValueError, match="out of valid range"):
        aqi_band(-1)
    with pytest.raises(ValueError, match="out of valid range"):
        aqi_band(501)


def test_n95_advice_appears_only_above_threshold():
    """Verify N95 / FFP2 respirator advice appears strictly when AQI > 200."""
    base_kwargs = {
        "location": "Delhi",
        "household": HouseholdType.ADULTS,
        "commute": CommuteMode.CAR,
        "cooking_fuel": CookingFuel.LPG,
        "budget": BudgetTier.MODERATE,
    }

    # At or below threshold: AQI = 200 -> No N95 respirator advice
    req_at_threshold = PlanRequest(aqi=AQI_MASK_THRESHOLD, **base_kwargs)
    plan_at_threshold = build_plan(req_at_threshold)
    routine_actions_at = [item.action.lower() for item in plan_at_threshold.routine]
    assert not any("n95" in a or "ffp2" in a for a in routine_actions_at)

    # Strictly above threshold: AQI = 201 -> N95 respirator advice required
    req_above_threshold = PlanRequest(aqi=AQI_MASK_THRESHOLD + 1, **base_kwargs)
    plan_above_threshold = build_plan(req_above_threshold)
    routine_actions_above = [item.action.lower() for item in plan_above_threshold.routine]
    assert any("n95" in a or "ffp2" in a for a in routine_actions_above)


def test_medical_help_note_appears_for_aqi_above_300():
    """Verify medical preparation note appears when AQI > 300 without health factors."""
    base_kwargs = {
        "location": "Kanpur",
        "household": HouseholdType.ADULTS,
        "health_factors": [],
        "commute": CommuteMode.CAR,
        "cooking_fuel": CookingFuel.LPG,
        "budget": BudgetTier.MODERATE,
    }

    # At threshold: AQI = 300 -> No medical note if no health factors
    req_300 = PlanRequest(aqi=AQI_MEDICAL_ALERT_THRESHOLD, **base_kwargs)
    plan_300 = build_plan(req_300)
    routine_300 = [item.action.lower() for item in plan_300.routine]
    assert not any("medical kit" in a or "inhaler" in a or "action plan" in a for a in routine_300)

    # Above threshold: AQI = 301 -> Medical preparation note must appear
    req_301 = PlanRequest(aqi=AQI_MEDICAL_ALERT_THRESHOLD + 1, **base_kwargs)
    plan_301 = build_plan(req_301)
    routine_301 = [item.action.lower() for item in plan_301.routine]
    assert any("medical kit" in a or "inhaler" in a or "action plan" in a for a in routine_301)


@pytest.mark.parametrize("factor", list(HealthFactor))
def test_medical_help_note_appears_for_each_health_factor(factor):
    """Verify medical preparation note appears for each health factor even at low AQI."""
    req = PlanRequest(
        location="Bengaluru",
        aqi=80,  # Satisfactory AQI (< 300)
        household=HouseholdType.ADULTS,
        health_factors=[factor],
        commute=CommuteMode.CAR,
        cooking_fuel=CookingFuel.LPG,
        budget=BudgetTier.MODERATE,
    )
    plan = build_plan(req)
    routine_actions = [item.action.lower() for item in plan.routine]
    assert any("medical kit" in a or "inhaler" in a or "action plan" in a for a in routine_actions), (
        f"Medical preparation action missing for health factor {factor}"
    )


def test_biomass_fuel_triggers_switching_advice():
    """Verify biomass fuel triggers clean-fuel switching recommendations."""
    # Test for very_low budget
    req_bio_low = PlanRequest(
        location="Varanasi",
        aqi=180,
        household=HouseholdType.ADULTS,
        commute=CommuteMode.WALK_CYCLE,
        cooking_fuel=CookingFuel.BIOMASS,
        budget=BudgetTier.VERY_LOW,
    )
    plan_low = build_plan(req_bio_low)
    swaps_low = [item.action.lower() for item in plan_low.swaps]
    assert any("outdoor" in a or "chimney" in a or "cleaner fuel" in a for a in swaps_low)

    # Test for moderate budget
    req_bio_mod = PlanRequest(
        location="Patna",
        aqi=240,
        household=HouseholdType.ADULTS,
        commute=CommuteMode.TWO_WHEELER,
        cooking_fuel=CookingFuel.BIOMASS,
        budget=BudgetTier.MODERATE,
    )
    plan_mod = build_plan(req_bio_mod)
    swaps_mod = [item.action.lower() for item in plan_mod.swaps]
    assert any("induction" in a or "lpg" in a for a in swaps_mod)


def test_very_low_budget_never_recommends_purifier_purchase():
    """Verify very_low budget never advises purchasing a commercial purifier or HEPA appliance."""
    for aqi_val in [120, 250, 450]:
        req = PlanRequest(
            location="Lucknow",
            aqi=aqi_val,
            household=HouseholdType.CHILDREN_AND_ELDERLY,
            health_factors=[HealthFactor.ASTHMA],
            commute=CommuteMode.PUBLIC_TRANSPORT,
            cooking_fuel=CookingFuel.BIOMASS,
            budget=BudgetTier.VERY_LOW,
        )
        plan = build_plan(req)
        indoor_actions = [item.action.lower() for item in plan.indoor]

        # Must not recommend purchasing a commercial purifier or HEPA machine
        assert not any("purchase a true hepa" in a for a in indoor_actions)
        assert not any("commercial air purifier" in a for a in indoor_actions)
        assert not any("buy" in a and "purifier" in a for a in indoor_actions)

        # Must suggest low-cost DIY filtration or wet cleaning instead
        assert any("diy" in a or "box fan" in a or "wet-mop" in a for a in indoor_actions)


def test_every_section_has_at_least_three_items():
    """Verify routine, indoor, and swaps sections always contain >= 3 items."""
    test_scenarios = [
        # Mild AQI, adult, car, flexible budget
        PlanRequest(
            location="Shimla",
            aqi=35,
            household=HouseholdType.ADULTS,
            commute=CommuteMode.CAR,
            cooking_fuel=CookingFuel.INDUCTION,
            budget=BudgetTier.FLEXIBLE,
        ),
        # Severe AQI, vulnerable family, very low budget, biomass
        PlanRequest(
            location="Delhi",
            aqi=460,
            household=HouseholdType.CHILDREN_AND_ELDERLY,
            health_factors=[HealthFactor.ASTHMA, HealthFactor.HEART],
            commute=CommuteMode.TWO_WHEELER,
            cooking_fuel=CookingFuel.BIOMASS,
            budget=BudgetTier.VERY_LOW,
        ),
        # Moderate AQI, work from home, piped gas
        PlanRequest(
            location="Pune",
            aqi=140,
            household=HouseholdType.YOUNG_CHILDREN,
            commute=CommuteMode.WORK_FROM_HOME,
            cooking_fuel=CookingFuel.PIPED_GAS,
            budget=BudgetTier.MODERATE,
        ),
        # Very Poor AQI, elderly, walk/cycle, outdoor work
        PlanRequest(
            location="Kolkata",
            aqi=320,
            household=HouseholdType.ELDERLY,
            health_factors=[HealthFactor.OUTDOOR_WORK],
            commute=CommuteMode.WALK_CYCLE,
            cooking_fuel=CookingFuel.LPG,
            budget=BudgetTier.VERY_LOW,
        ),
    ]

    for req in test_scenarios:
        plan = build_plan(req)
        assert len(plan.routine) >= 3, f"Routine section has {len(plan.routine)} items for aqi={req.aqi}"
        assert len(plan.indoor) >= 3, f"Indoor section has {len(plan.indoor)} items for aqi={req.aqi}"
        assert len(plan.swaps) >= 3, f"Swaps section has {len(plan.swaps)} items for aqi={req.aqi}"


def test_every_impact_contains_hedged_word_and_basis():
    """Verify that every single action item contains an honest, hedged estimate with basis."""
    for household in HouseholdType:
        for budget in BudgetTier:
            req = PlanRequest(
                location="Delhi",
                aqi=350,
                household=household,
                health_factors=[HealthFactor.ASTHMA],
                commute=CommuteMode.TWO_WHEELER,
                cooking_fuel=CookingFuel.BIOMASS,
                budget=budget,
            )
            plan = build_plan(req)
            all_items = plan.routine + plan.indoor + plan.swaps
            for item in all_items:
                impact_text = item.impact.lower()
                has_hedge = any(word in impact_text for word in HEDGE_WORDS)
                assert has_hedge, (
                    f"Item action '{item.action}' impact '{item.impact}' lacks expected hedge words ({HEDGE_WORDS})"
                )
                assert "basis" in impact_text, (
                    f"Item action '{item.action}' impact '{item.impact}' lacks explicit scientific basis"
                )
