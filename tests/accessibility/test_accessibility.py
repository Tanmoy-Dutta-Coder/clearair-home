from pathlib import Path

import pytest
from html5lib import parse

pytestmark = pytest.mark.accessibility
ROOT = Path(__file__).parents[2]


def test_every_form_input_has_an_associated_label_and_headings_are_structured():
    tree = parse(
        (ROOT / "static" / "index.html").read_text(encoding="utf-8"),
        namespaceHTMLElements=False,
    )
    ids = {node.attrib["id"] for node in tree.iter() if node.tag == "input" and "id" in node.attrib}
    labels = {node.attrib.get("for") for node in tree.iter() if node.tag == "label"}
    assert ids <= labels
    assert sum(node.tag == "h1" for node in tree.iter()) == 1
    levels = [int(node.tag[1]) for node in tree.iter() if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}]
    assert all(current <= previous + 1 for previous, current in zip(levels, levels[1:], strict=False))


def test_live_regions_skip_link_and_reduced_motion_rule_exist():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    assert 'href="#main-content"' in html
    assert 'aria-live="polite"' in html
    assert "prefers-reduced-motion: reduce" in css


def relative_luminance(hex_color):
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground, background):
    high, low = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize(
    "foreground,background",
    [
        ("#FFFFFF", "#5B6E28"),
        ("#141C0C", "#F3F6F4"),
        ("#141C0C", "#FFFFFF"),
        ("#4E5F2D", "#F3F6F4"),
        ("#141C0C", "#7E8E36"),
        ("#141C0C", "#FF5A1C"),
        ("#FFFFFF", "#822416"),
    ],
)
def test_documented_contrast_pairs_meet_wcag_aa(foreground, background):
    assert contrast_ratio(foreground, background) >= 4.5


def test_axe_has_no_critical_or_serious_violations_on_empty_form_and_results(browser_page, local_app_url):
    axe_path = ROOT / "node_modules" / "axe-core" / "axe.min.js"
    assert axe_path.exists(), "Install npm dev dependencies with npm ci to run axe checks"
    page = browser_page
    page.route(
        "**/axe.min.js",
        lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body=axe_path.read_text(encoding="utf-8"),
        ),
    )
    page.goto(local_app_url)
    page.add_script_tag(url=f"{local_app_url}/axe.min.js")

    empty_violations = page.evaluate(
        "async () => (await axe.run()).violations.filter(v => ['critical','serious'].includes(v.impact))"
    )
    assert empty_violations == []

    mock_plan = {
        "aqi_band": "Poor",
        "summary": "Current air quality is poor.",
        "used_ai": False,
        "routine": [
            {
                "action": "Wear a respirator",
                "why": "Reduce exposure.",
                "impact": "Roughly 50% reduction (test basis).",
            }
        ]
        * 3,
        "indoor": [
            {
                "action": "Filter indoor air",
                "why": "Reduce particles.",
                "impact": "About 50% reduction (test basis).",
            }
        ]
        * 3,
        "swaps": [
            {
                "action": "Use transit",
                "why": "Reduce emissions.",
                "impact": "About 20% reduction (test basis).",
            }
        ]
        * 3,
    }
    page.route(
        "**/api/plan",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=__import__("json").dumps(mock_plan),
        ),
    )
    page.locator("#location").fill("Delhi")
    page.locator("#aqi").fill("250")
    page.locator("#plan-form button[type=submit]").click()
    page.locator("#results-section:not(.hidden)").wait_for()
    page.locator("#submit-btn:not([disabled])").wait_for()
    assert page.evaluate("document.activeElement.id") == "results-heading"
    results_violations = page.evaluate(
        "async () => (await axe.run()).violations.filter(v => ['critical','serious'].includes(v.impact))"
    )
    assert results_violations == []

    page.locator("#location").fill("")
    page.locator("#plan-form button[type=submit]").click()
    page.locator("#form-errors:not(.hidden)").wait_for()
    page.locator("#submit-btn:not([disabled])").wait_for()
    page.emulate_media(color_scheme="dark")
    assert page.locator("#submit-btn").evaluate("element => !element.disabled")
    assert page.locator("#submit-btn").evaluate("element => getComputedStyle(element).opacity") == "1"
    error_dark_violations = page.evaluate(
        "async () => (await axe.run()).violations.filter(v => ['critical','serious'].includes(v.impact))"
    )
    assert error_dark_violations == [], "\n".join(
        f"{node['target']}: {node.get('any', [{}])[0].get('data', {})}"
        for violation in error_dark_violations
        for node in violation["nodes"]
    )


def test_keyboard_skip_link_reduced_motion_dark_mode_and_320px(browser_page, local_app_url):
    page = browser_page
    page.set_viewport_size({"width": 320, "height": 800})
    page.emulate_media(color_scheme="dark", reduced_motion="reduce")
    page.goto(local_app_url)
    page.keyboard.press("Tab")
    assert page.locator(":focus").get_attribute("href") == "#main-content"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main-content"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.evaluate(
        "matchMedia('(prefers-color-scheme: dark)').matches && matchMedia('(prefers-reduced-motion: reduce)').matches"
    )
