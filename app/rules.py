"""Deterministic rule engine for clearair-home.

Evaluates user context (AQI, household vulnerability, health factors,
commute mode, cooking fuel, and budget) to generate structured action plans.
Pure functions only, with zero I/O and zero LLM dependencies.
"""

from app.schemas import (
    ActionItem,
    BudgetTier,
    CommuteMode,
    CookingFuel,
    HouseholdType,
    PlanRequest,
    PlanResponse,
)

# Indian CPCB AQI Category Thresholds (Upper bounds)
AQI_GOOD_MAX = 50
AQI_SATISFACTORY_MAX = 100
AQI_MODERATE_MAX = 200
AQI_POOR_MAX = 300
AQI_VERY_POOR_MAX = 400
AQI_SEVERE_MAX = 500

# Action Decision Thresholds
AQI_MASK_THRESHOLD = 200
AQI_MEDICAL_ALERT_THRESHOLD = 300


def aqi_band(aqi: int) -> str:
    """Return the official Indian CPCB AQI band for a given AQI value.

    Args:
        aqi: Integer AQI value between 0 and 500.

    Returns:
        String category name matching Indian National Air Quality Index standards.

    Raises:
        ValueError: If aqi is outside the 0 to 500 range.
    """
    if not (0 <= aqi <= AQI_SEVERE_MAX):
        raise ValueError(f"AQI {aqi} is out of valid range (0-{AQI_SEVERE_MAX})")

    if aqi <= AQI_GOOD_MAX:
        return "Good"
    if aqi <= AQI_SATISFACTORY_MAX:
        return "Satisfactory"
    if aqi <= AQI_MODERATE_MAX:
        return "Moderate"
    if aqi <= AQI_POOR_MAX:
        return "Poor"
    if aqi <= AQI_VERY_POOR_MAX:
        return "Very Poor"
    return "Severe"


def _is_vulnerable_household(household: HouseholdType) -> bool:
    """Check if the household includes high-risk age demographics."""
    return household in (
        HouseholdType.YOUNG_CHILDREN,
        HouseholdType.ELDERLY,
        HouseholdType.CHILDREN_AND_ELDERLY,
    )


def _has_medical_risk(request: PlanRequest) -> bool:
    """Check if the plan requires an urgent medical safeguard alert."""
    return request.aqi > AQI_MEDICAL_ALERT_THRESHOLD or len(request.health_factors) > 0


def _build_summary(request: PlanRequest, band: str) -> str:
    """Generate a clear contextual summary based on AQI band and vulnerabilities."""
    vulnerabilities = []
    if _is_vulnerable_household(request.household):
        vulnerabilities.append("high-risk age groups (children/elderly)")
    if request.health_factors:
        vulnerabilities.append(f"{len(request.health_factors)} sensitive health condition(s)")

    vuln_desc = f" Household has {', and '.join(vulnerabilities)}." if vulnerabilities else ""
    return (
        f"Current air quality in {request.location} is {band} (AQI {request.aqi})."
        f"{vuln_desc} Prioritize protective indoor safeguards and low-emission choices."
    )


def _build_routine_items(request: PlanRequest) -> list[ActionItem]:
    """Generate daily routine and exposure timing recommendations (at least 3)."""
    items: list[ActionItem] = []

    # 1. Mask guidance based on AQI threshold
    if request.aqi > AQI_MASK_THRESHOLD:
        items.append(
            ActionItem(
                action="Wear a well-fitted N95 or FFP2 respirator outdoors",
                why=f"AQI is {request.aqi} ({aqi_band(request.aqi)}). Standard cloth or surgical masks do not filter fine PM2.5 aerosols.",
                impact="Roughly 95% fine particle filtration efficiency when fitted with a tight perimeter seal (NIOSH/CPCB test basis).",
            )
        )
    else:
        items.append(
            ActionItem(
                action="Keep standard respiratory protection handy for traffic corridors",
                why=f"AQI is {request.aqi} ({aqi_band(request.aqi)}). Local roadway exhaust can still spike particulate exposure during commutes.",
                impact="About 30% to 50% particulate reduction for transient roadside exhaust exposures (occupational safety basis).",
            )
        )

    # 2. Exercise & outdoor activity scheduling based on vulnerability & AQI
    if _is_vulnerable_household(request.household) or request.aqi > AQI_MODERATE_MAX:
        items.append(
            ActionItem(
                action="Shift all aerobic exercise and active play strictly indoors",
                why=(
                    "Deep breathing during outdoor exertion increases particulate deposition in sensitive lungs by 3 to 5 times, "
                    "especially risky for children and seniors."
                ),
                impact="Roughly 60% to 80% reduction in total inhaled aerosol volume compared to exercising outdoors (aerosol medicine study basis).",
            )
        )
    else:
        items.append(
            ActionItem(
                action="Schedule outdoor physical activities between 1:00 PM and 4:00 PM",
                why="Winter temperature inversions trap heavy smog near ground level in early mornings and late evenings; midday sun promotes dispersion.",
                impact="About 25% to 40% lower ambient PM2.5 exposure compared to early morning hours (CPCB diurnal curve basis).",
            )
        )

    # 3. Medical alert / proactive symptom monitoring
    if _has_medical_risk(request):
        conditions = [hf.value for hf in request.health_factors] or ["high AQI threshold"]
        items.append(
            ActionItem(
                action="Prepare emergency medical kit, rescue inhalers, and symptom checklist",
                why=f"Identified elevated risk ({', '.join(conditions)}). Smog triggers rapid bronchial spasms and cardiovascular stress.",
                impact="About 50% reduction in severe asthma attack escalation when rescue medication is initiated at earliest symptom onset (clinical asthma guidelines basis).",
            )
        )
    else:
        items.append(
            ActionItem(
                action="Conduct hydration and saline nasal rinses after outdoor exposure",
                why="Particulates dry out the nasal mucosa and irritate upper respiratory passages during winter smog.",
                impact="Roughly 20% to 30% reduction in mucosal irritation and particulate carriage in upper nasal passages (ENT clinical basis).",
            )
        )

    # 4. Commute travel routine window
    if request.commute != CommuteMode.WORK_FROM_HOME:
        items.append(
            ActionItem(
                action="Adjust commute departure away from peak morning inversion (avoid 7:00 AM - 9:30 AM)",
                why="Surface-level pollutant concentrations peak during morning rush hour combined with cold winter boundary layer compression.",
                impact="About 20% to 35% lower commuter exposure to direct tailpipe carbon monoxide and black carbon (urban transit exposure basis).",
            )
        )
    else:
        items.append(
            ActionItem(
                action="Cluster any outdoor essential errands into a single midday outing",
                why="Working from home minimizes transit exposure; combining errands during peak sunlight hours prevents unnecessary smog exposure.",
                impact="Roughly 40% reduction in daily personal exposure compared to multiple separate trips during peak smog hours (exposure model basis).",
            )
        )

    return items[:4]


def _build_indoor_items(request: PlanRequest) -> list[ActionItem]:
    """Generate indoor air quality and ventilation interventions (at least 3)."""
    items: list[ActionItem] = []

    # 1. Purifier vs Low-cost DIY filtration based strictly on budget
    if request.budget == BudgetTier.VERY_LOW:
        items.append(
            ActionItem(
                action="Build a DIY box fan filter (Corsi-Rosenthal style) using a MERV-13 filter",
                why="Commercial purifiers have high upfront costs, whereas a standard box fan with a securely taped MERV-13 furnace filter cleans air effectively.",
                impact="Roughly 60% to 80% reduction in room PM2.5 levels within 45 minutes of operation (peer-reviewed indoor filtration study basis).",
            )
        )
        items.append(
            ActionItem(
                action="Wet-mop floors daily and wipe flat surfaces with damp microfiber cloths",
                why="Dry sweeping resuspends toxic settled fine dust back into the breathing zone.",
                impact="About 30% to 50% reduction in resuspended indoor particulate concentrations compared to dry broom sweeping (EPA indoor air protocol basis).",
            )
        )
    elif request.budget == BudgetTier.MODERATE:
        items.append(
            ActionItem(
                action="Run a mid-capacity True HEPA air purifier continuously in the primary bedroom",
                why="True HEPA captures sub-micron combustion particles without producing secondary ozone. Sleeping in clean air aids lung recovery.",
                impact="Roughly 75% to 85% reduction in bedroom PM2.5 concentrations in a closed room (standard CADR test basis).",
            )
        )
    else:  # BudgetTier.FLEXIBLE
        items.append(
            ActionItem(
                action="Deploy multi-room True HEPA purifiers with activated carbon filters and seal perimeter gaps",
                why="Activated carbon adsorbs volatile organic compounds (VOCs) and smog odor, while HEPA eliminates particulate matter across the residence.",
                impact="About 85% to 92% reduction in overall indoor PM2.5 and gaseous co-pollutant levels (multi-stage filtration benchmark basis).",
            )
        )

    # 2. Window and ventilation management
    if request.aqi > AQI_MODERATE_MAX:
        items.append(
            ActionItem(
                action="Keep windows and balcony doors sealed; place rolled damp towels along drafty door thresholds",
                why="Hazardous outdoor air rapidly infiltrates homes through window cracks and doorway gaps during stagnant winter inversions.",
                impact="Roughly 40% to 60% reduction in outdoor-to-indoor particulate infiltration rate (building envelope research basis).",
            )
        )
    else:
        items.append(
            ActionItem(
                action="Ventilate briefly for 15-20 minutes only during afternoon hours (1:00 PM - 3:00 PM)",
                why="Allows indoor carbon dioxide flush while avoiding high morning and late evening outdoor smog spikes.",
                impact="About 30% reduction in indoor CO2 buildup without substantial outdoor PM ingress (controlled natural ventilation basis).",
            )
        )

    # 3. Combustion / fragrance avoidance inside home
    items.append(
        ActionItem(
            action="Strictly avoid incense (agarbatti), mosquito coils, and scented candles indoors",
            why="Burning one mosquito coil or incense stick generates fine particulate concentrations equivalent to several tens of cigarettes in an unventilated room.",
            impact="Avoids adding roughly 100 to 250 µg/m³ of internal PM2.5 load into living spaces (combustion emissions study basis).",
        )
    )

    return items[:4]


def _build_swap_items(request: PlanRequest) -> list[ActionItem]:
    """Generate sustainable alternatives for cooking, commuting, and routines (at least 3)."""
    items: list[ActionItem] = []

    # 1. Cooking fuel swaps & kitchen ventilation
    if request.cooking_fuel == CookingFuel.BIOMASS:
        if request.budget == BudgetTier.VERY_LOW:
            items.append(
                ActionItem(
                    action="Cook outdoors or directly beneath an unblocked chimney using dry, seasoned firewood",
                    why="Damp biomass and unvented chulhas produce extreme carbon monoxide and dense black carbon inside enclosed living spaces.",
                    impact="Roughly 50% to 70% decrease in acute kitchen breathing-zone particulate exposure (rural energy study basis).",
                )
            )
        else:
            items.append(
                ActionItem(
                    action="Transition from biomass to a single-burner induction cooktop or clean LPG cylinder",
                    why="Biomass combustion in winter creates concentrated domestic smoke that lingers at floor level where children crawl and play.",
                    impact="Avoids about 80% to 90% of domestic primary PM2.5 emissions during meal preparations (clean cooking transition basis).",
                )
            )
    elif request.cooking_fuel in (CookingFuel.LPG, CookingFuel.PIPED_GAS):
        items.append(
            ActionItem(
                action="Operate kitchen exhaust fan continuously and cook with tight-fitting lids on burners",
                why="Gas combustion releases nitrogen dioxide (NO2) and ultrafine particles that exacerbate bronchial hyper-reactivity.",
                impact="About 35% to 55% reduction in indoor peak NO2 and aerosol peaks during active boiling/frying (kitchen ventilation study basis).",
            )
        )
    else:  # Induction
        items.append(
            ActionItem(
                action="Maintain electric induction cooking and clean cooktop surface regularly",
                why="Induction cooking emits zero in-situ combustion exhaust (no carbon monoxide or nitrogen dioxide emissions).",
                impact="Zero direct combustion byproduct generation inside the residence (appliance emission benchmark basis).",
            )
        )

    # 2. Commute swaps respecting budget
    if request.commute == CommuteMode.CAR:
        if request.budget == BudgetTier.VERY_LOW:
            items.append(
                ActionItem(
                    action="Switch to shared public bus or carpooling for regular work trips",
                    why="Single-occupancy private cars generate significant tailpipe emissions and stall in heavy congestion.",
                    impact="About 1.5 to 2.5 kg CO2 and proportional tailpipe PM avoided per 10 km commute (urban transport average basis).",
                )
            )
        elif request.budget == BudgetTier.MODERATE:
            items.append(
                ActionItem(
                    action="Shift to metro rail transit or set vehicle AC to 100% recirculation mode with a cabin PM2.5 filter",
                    why="Metro transit removes you from surface exhaust corridors; cabin recirculation blocks highway particulate ingress.",
                    impact="Roughly 70% reduction in in-cabin particle exposure and about 2 kg CO2 avoided per transit trip (transportation research basis).",
                )
            )
        else:
            items.append(
                ActionItem(
                    action="Adopt remote work (WFH) on high smog days or organize an EV/carpool commute pool",
                    why="Eliminating private vehicle runs on severe smog days reduces localized peak congestion and road-dust grinding.",
                    impact="About 3 to 5 kg CO2 avoided per avoided round-trip commute (fleet emission model basis).",
                )
            )
    elif request.commute == CommuteMode.TWO_WHEELER:
        items.append(
            ActionItem(
                action="Shift to metro transit or covered bus; if two-wheeler is unavoidable, wear a sealed N95 under full-face helmet",
                why="Two-wheeler riders are directly immersed in the vehicular exhaust plume at tailpipe height without any cabin buffer.",
                impact="Roughly 85% reduction in direct inhaled exhaust particles when combining closed visor and sealed N95 (commuter exposure study basis).",
            )
        )
    elif request.commute == CommuteMode.WALK_CYCLE:
        if request.aqi > AQI_MODERATE_MAX:
            items.append(
                ActionItem(
                    action="Swap walking/cycling along main arterial roads for public transit or detour via residential interior streets",
                    why="Heavy physical exertion next to diesel trucks and buses leads to extreme deep-lung particulate deposition during winter inversions.",
                    impact="About 50% to 65% reduction in commuter black carbon intake during transit (active transport exposure study basis).",
                )
            )
        else:
            items.append(
                ActionItem(
                    action="Choose tree-lined interior residential lanes instead of major highway corridors for active commutes",
                    why="Vegetative roadside buffers and lower vehicle density significantly reduce immediate tailpipe plume exposure.",
                    impact="About 25% to 40% reduction in peak ultra-fine particle exposure (urban canopy study basis).",
                )
            )
    else:  # WORK_FROM_HOME
        items.append(
            ActionItem(
                action="Maintain remote work schedule and replace localized courier deliveries with consolidated neighborhood orders",
                why="Eliminates individual commute emissions while reducing delivery vehicle trips in the community.",
                impact="About 2 to 4 kg CO2 avoided per avoided daily urban trip (urban mobility baseline basis).",
            )
        )

    # 3. Sustainable lifestyle / waste management swap
    items.append(
        ActionItem(
            action="Compost or bag organic garden/kitchen waste; strictly avoid burning dry leaves or trash",
            why="Open biomass burning produces dense polycyclic aromatic hydrocarbons (PAHs) and toxic smoke at ground level during stagnant winter nights.",
            impact="Avoids releasing roughly 15 to 30 grams of pure fine particulate matter per small pile burned (CPCB emission inventory basis).",
        )
    )

    return items[:4]


def build_plan(request: PlanRequest) -> PlanResponse:
    """Build a deterministic, context-aware air quality adaptation plan.

    Pure deterministic decision engine based on user location, AQI,
    household age demographics, health vulnerabilities, commute mode,
    cooking fuel, and budget tier.

    Args:
        request: Validated PlanRequest data model.

    Returns:
        PlanResponse containing CPCB aqi_band, summary, and prioritized
        action items for routine, indoor IAQ, and sustainable swaps.
    """
    band = aqi_band(request.aqi)
    summary = _build_summary(request, band)
    routine = _build_routine_items(request)
    indoor = _build_indoor_items(request)
    swaps = _build_swap_items(request)

    return PlanResponse(
        aqi_band=band,
        summary=summary,
        routine=routine,
        indoor=indoor,
        swaps=swaps,
    )
