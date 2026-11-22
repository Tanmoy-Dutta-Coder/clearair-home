import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.rules import build_plan
from app.schemas import PlanRequest


PERSONAS = {
    "kolkata_children_biomass_380": dict(location="Kolkata", aqi=380, household="young_children", health_factors=[], commute="public_transport", cooking_fuel="biomass", budget="very_low"),
    "adult_wfh_120": dict(location="Pune", aqi=120, household="adults", health_factors=[], commute="work_from_home", cooking_fuel="induction", budget="moderate"),
    "elderly_heart_301": dict(location="Delhi", aqi=301, household="elderly", health_factors=["heart"], commute="car", cooking_fuel="lpg", budget="moderate"),
    "two_wheeler_adult_250": dict(location="Jaipur", aqi=250, household="adults", health_factors=[], commute="two_wheeler", cooking_fuel="piped_gas", budget="flexible"),
    "family_severe_low_budget": dict(location="Kanpur", aqi=500, household="children_and_elderly", health_factors=["asthma"], commute="walk_cycle", cooking_fuel="biomass", budget="very_low"),
}

destination = Path(__file__).parents[1] / "tests" / "snapshots" / "personas"
destination.mkdir(parents=True, exist_ok=True)
for name, payload in PERSONAS.items():
    plan = build_plan(PlanRequest(**payload))
    (destination / f"{name}.json").write_text(json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
