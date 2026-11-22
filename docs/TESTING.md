# ClearAir Home — Testing Guide & Manual Test Matrix

This document outlines the testing strategy, automated test suites, and manual verification procedures for device-specific capabilities such as HTML5 Geolocation.

---

## 1. Automated Test Suites

All automated tests use `pytest` and `pytest-asyncio`. External HTTP dependencies (`httpx`) and the Gemini GenAI SDK are **100% mocked**, guaranteeing fast, offline, and reliable test runs.

Run the full test suite:
```bash
pytest -v
```

### Test Coverage Summary:
- **`tests/test_schemas.py`**:
  - `PlanRequest` input validation, whitespace stripping, length constraints, boundary AQI values (0, 500, negative, >500), and unknown field rejection (`extra="forbid"`).
  - `PlanResponse` structural invariant enforcement (minimum 3 items per section).
  - `CoordsQuery` validation: -90..90 latitude, -180..180 longitude, rejection of `NaN`, `inf`, `-inf`, and extra parameters.
- **`tests/test_rules.py`**:
  - Indian CPCB AQI band classification across all 6 tiers.
  - Contextual decision matrices: N95/FFP2 masking when AQI > 200, indoor exercise restrictions for vulnerable groups, medical checklists when AQI > 300 or health conditions present, biomass clean fuel transitions, and budget-sensitive filtration (DIY Corsi-Rosenthal vs True HEPA).
  - Verification that 100% of generated items include honest, hedged impact statements with an explicit basis.
- **`tests/test_aqi_provider.py`**:
  - Exact CPCB breakpoint calculations for PM2.5 and PM10.
  - Sub-index maximization.
  - Geocoding and air quality JSON parsing.
  - 15-minute TTL cache hit and miss verification.
  - Coordinate rounding to 2 decimals (~1 km grid) prior to cache lookup.
  - Non-disclosure of user coordinates in exception messages and logs.
  - Timeout recovery raising `AqiUnavailable`.
- **`tests/test_api.py`**:
  - `GET /healthz` probe and security headers (`Permissions-Policy: geolocation=(self)`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`).
  - `GET /` and static asset delivery (`styles.css`, `app.js`).
  - `POST /api/plan` plan generation.
  - `GET /api/aqi?place=...` success, 503 fallback, and 422 input validation.
  - `GET /api/aqi/coords?lat=..&lon=..` success, 503 fallback (with no coordinates in response), and 422 input validation.
  - Sliding-window rate limiter enforcement returning HTTP 429.

---

## 2. Manual Geolocation Test Matrix (Device & Browser Verification)

Because browser geolocation (`navigator.geolocation.getCurrentPosition`) requires interactive user permission prompts and device sensor access, verify these scenarios on a desktop or mobile browser over **HTTPS** (or `http://localhost`):

| Test Case | Scenario / Preconditions | User Action | Expected Behavior |
| :--- | :--- | :--- | :--- |
| **M-1: Feature Detection** | Open in an insecure context (e.g. non-localhost HTTP) or on a browser with geolocation disabled. | Load `http://<ip>:8000`. | The "Use my current location" button is automatically hidden. Form remains 100% usable via manual entry. |
| **M-2: User Consent Granted** | Modern browser on HTTPS or `http://localhost:8000`. | Click "Use my current location" and choose **Allow** when prompted. | 1. Button changes to disabled with "Detecting your location...".<br>2. Coordinates are rounded to 2 decimals and sent to `/api/aqi/coords`.<br>3. AQI input pre-fills with estimated AQI.<br>4. Live region announces: *"Auto-detected near your current location from Open-Meteo (modelled estimate), <time>. You can edit this."*<br>5. Focus moves back to the AQI field.<br>6. Button is re-enabled. |
| **M-3: User Permission Denied** | Modern browser on HTTPS or `http://localhost:8000`. | Click "Use my current location" and choose **Block** / **Don't Allow**. | 1. Live region announces: *"Location access was declined. Please enter your AQI manually."*<br>2. Button is re-enabled.<br>3. Form inputs remain editable and unblocked. |
| **M-4: Device Position Unavailable** | Device in Airplane mode or location hardware disabled at OS level. | Click "Use my current location". | 1. Live region announces: *"Your device could not determine your location. Please enter your AQI manually."*<br>2. Button is re-enabled. |
| **M-5: Geolocation Timeout** | Emulate delayed position (e.g. Chrome DevTools Sensors: delay > 8 seconds). | Click "Use my current location". | 1. Browser 8-second timeout triggers.<br>2. Live region announces: *"Finding your location took too long. Please enter your AQI manually."*<br>3. Button is re-enabled. |
| **M-6: Upstream Network Failure** | Open-Meteo offline or network disconnected after coordinates obtained. | Click "Use my current location". | 1. Backend returns HTTP 503.<br>2. Live region announces: *"Couldn't fetch air quality for your area. Please enter your AQI manually."*<br>3. Coordinates are never leaked in UI or server logs. |
