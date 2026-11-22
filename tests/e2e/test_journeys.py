import json

import pytest

pytestmark = pytest.mark.e2e


def sample_plan():
    return {
        "aqi_band": "Very Poor",
        "summary": "Current air quality in Delhi is Very Poor.",
        "used_ai": False,
        "routine": [
            {
                "action": "Wear a well-fitted N95",
                "why": "Reduce particle exposure.",
                "impact": "Roughly 80% reduction (test basis).",
            }
        ]
        * 3,
        "indoor": [
            {
                "action": "Filter indoor air",
                "why": "Reduce particles.",
                "impact": "About 60% reduction (test basis).",
            }
        ]
        * 3,
        "swaps": [
            {
                "action": "Choose cleaner travel",
                "why": "Reduce emissions.",
                "impact": "About 20% reduction (test basis).",
            }
        ]
        * 3,
    }


def mock_api(page, plan=None):
    page.route(
        "**/api/plan",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(plan or sample_plan()),
        ),
    )
    page.route(
        "**/api/aqi?**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "aqi": 385,
                    "band": "Severe",
                    "source": "Open-Meteo",
                    "observed_at": "now",
                    "area": "Delhi",
                }
            ),
        ),
    )
    page.route(
        "**/api/aqi/coords?**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "aqi": 320,
                    "band": "Very Poor",
                    "source": "Open-Meteo",
                    "observed_at": "now",
                    "area": "Your current location (approx.)",
                    "approximate_location": True,
                }
            ),
        ),
    )


def fill_required_form(page):
    page.locator("#location").fill("Delhi")
    page.locator("#aqi").fill("380")


def test_manual_aqi_journey_renders_complete_results(page, app_url):
    mock_api(page)
    page.goto(app_url)
    fill_required_form(page)
    page.locator("#plan-form button[type=submit]").click()
    page.locator("#results-section:not(.hidden)").wait_for()
    assert page.locator("#result-aqi-val").inner_text() == "380"
    assert page.locator("#result-aqi-band").inner_text() == "◆ VERY POOR"
    assert page.locator("#routine-cards article").count() == 3
    assert page.evaluate("document.activeElement.id") == "results-heading"


def test_regional_preset_fills_location_and_aqi(page, app_url):
    page.goto(app_url)
    page.locator('[data-location="Kanpur"]').click()
    assert page.locator("#location").input_value() == "Kanpur"
    assert page.locator("#aqi").input_value() == "320"
    assert "selected" in (page.locator('[data-location="Kanpur"]').get_attribute("class") or "")


def test_place_name_aqi_detection_uses_mocked_backend(page, app_url):
    mock_api(page)
    page.goto(app_url)
    page.locator("#location").fill("Delhi")
    page.locator("#detect-aqi-btn").click()
    assert page.locator("#aqi").input_value() == "385"
    assert "Open-Meteo" in page.locator("#detection-status").inner_text()


def test_geolocation_granted_uses_rounded_location(page, app_url):
    mock_api(page)
    context = page.context
    context.grant_permissions(["geolocation"], origin=app_url)
    context.set_geolocation({"latitude": 28.613891, "longitude": 77.209012})
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(app_url)
    page.locator("#use-location-btn").click()
    assert page.locator("#aqi").input_value() == "320"
    assert any("lat=28.61" in url and "lon=77.21" in url for url in requests)


@pytest.mark.parametrize(
    "code,message",
    [(1, "Location access was declined"), (3, "Finding your location took too long")],
)
def test_geolocation_denial_and_timeout_have_friendly_errors(page, app_url, code, message):
    page.add_init_script(
        f"""Object.defineProperty(navigator, 'geolocation', {{value: {{getCurrentPosition(_success, failure) {{failure({{code: {code}}});}}}}}});"""
    )
    page.goto(app_url)
    page.locator("#use-location-btn").click()
    assert message in page.locator("#detection-status").inner_text()


def test_form_validation_and_print_view(page, app_url):
    page.goto(app_url)
    page.locator("#plan-form button[type=submit]").click()
    assert "Please enter your location" in page.locator("#form-errors").inner_text()
    page.emulate_media(media="print")
    assert page.locator("#print-btn").is_hidden()


def test_keyboard_only_skip_link_and_form_flow(page, app_url):
    mock_api(page)
    page.goto(app_url)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main-content"
    page.locator("#location").focus()
    page.keyboard.type("Delhi")
    page.locator("#aqi").focus()
    page.keyboard.type("300")
    page.locator("#plan-form button[type=submit]").focus()
    page.keyboard.press("Enter")
    page.locator("#results-section:not(.hidden)").wait_for()
    assert page.locator("#results-heading").evaluate("el => document.activeElement === el")
