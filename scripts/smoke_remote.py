#!/usr/bin/env python3
"""Smoke test script for remote and local ClearAir Home deployments.

Uses only the Python standard library (no third-party dependencies).

Checks:
1. GET /healthz returns HTTP 200 and {"status": "ok"}.
2. GET / returns HTML dashboard.
3. POST /api/plan with a sample payload returns a valid plan structure.
4. Mandatory security headers are present.

Usage:
    python scripts/smoke_remote.py <base_url>
    e.g. python scripts/smoke_remote.py http://localhost:10000
         python scripts/smoke_remote.py https://clearair-home.onrender.com
"""

import json
import sys
import urllib.error
import urllib.request


def log(msg: str) -> None:
    print(f"[SMOKE] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def check_security_headers(headers: dict[str, str], context: str) -> None:
    expected_headers = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "geolocation=(self)",
    }

    # Case-insensitive headers dictionary
    norm_headers = {k.lower(): v for k, v in headers.items()}

    # Check CSP presence
    if "content-security-policy" not in norm_headers:
        fail(f"{context}: Missing Content-Security-Policy header")
    csp = norm_headers["content-security-policy"]
    if "default-src 'self'" not in csp:
        fail(f"{context}: Content-Security-Policy missing default-src 'self': {csp}")

    for header_name, expected_val in expected_headers.items():
        if header_name not in norm_headers:
            fail(f"{context}: Missing required security header '{header_name}'")
        actual_val = norm_headers[header_name]
        if expected_val.lower() not in actual_val.lower():
            fail(f"{context}: Header '{header_name}' value '{actual_val}' does not match expected '{expected_val}'")

    log(f"Verified security headers on {context}")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <base_url>", file=sys.stderr)
        print("Example: python scripts/smoke_remote.py http://localhost:10000", file=sys.stderr)
        sys.exit(2)

    base_url = sys.argv[1].rstrip("/")
    log(f"Starting smoke tests against target: {base_url}")

    # 1. Test GET /healthz
    health_url = f"{base_url}/healthz"
    log(f"Checking GET {health_url}...")
    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "ClearAirSmoke/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            headers = dict(resp.headers)

            if status != 200:
                fail(f"GET /healthz returned status {status}, expected 200")

            data = json.loads(body)
            if data.get("status") != "ok":
                fail(f"GET /healthz body unexpected: {body}")

            check_security_headers(headers, "GET /healthz")
            log("GET /healthz PASSED (HTTP 200 OK)")
    except urllib.error.URLError as e:
        fail(f"Connection failed for GET /healthz: {e}")

    # 2. Test GET / (HTML Dashboard)
    root_url = f"{base_url}/"
    log(f"Checking GET {root_url}...")
    try:
        req = urllib.request.Request(root_url, headers={"User-Agent": "ClearAirSmoke/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            content_type = resp.headers.get("Content-Type", "")

            if status != 200:
                fail(f"GET / returned status {status}, expected 200")

            if "text/html" not in content_type:
                fail(f"GET / Content-Type '{content_type}' does not contain text/html")

            if "ClearAir Home" not in body:
                fail("GET / response body missing expected title 'ClearAir Home'")

            log("GET / PASSED (HTTP 200 HTML dashboard)")
    except urllib.error.URLError as e:
        fail(f"Connection failed for GET /: {e}")

    # 3. Test POST /api/plan
    plan_url = f"{base_url}/api/plan"
    log(f"Checking POST {plan_url}...")
    sample_payload = {
        "location": "Kolkata",
        "aqi": 380,
        "household": "young_children",
        "health_factors": ["asthma"],
        "commute": "public_transport",
        "cooking_fuel": "biomass",
        "budget": "very_low",
    }
    payload_bytes = json.dumps(sample_payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            plan_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ClearAirSmoke/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            headers = dict(resp.headers)

            if status != 200:
                fail(f"POST /api/plan returned status {status}, expected 200")

            plan = json.loads(body)
            # Validate required fields
            for section in ("routine", "indoor", "swaps"):
                items = plan.get(section)
                if not isinstance(items, list) or len(items) < 3:
                    fail(f"POST /api/plan section '{section}' does not contain at least 3 items: {items}")

            if "aqi_band" not in plan:
                fail("POST /api/plan response missing 'aqi_band'")

            if "used_ai" not in plan:
                fail("POST /api/plan response missing 'used_ai'")

            check_security_headers(headers, "POST /api/plan")
            log(f"POST /api/plan PASSED (band={plan['aqi_band']}, used_ai={plan['used_ai']})")
    except urllib.error.URLError as e:
        fail(f"Connection failed for POST /api/plan: {e}")

    log("=" * 60)
    log("ALL SMOKE TESTS PASSED SUCCESSFULLY! Target deployment is healthy.")
    log("=" * 60)


if __name__ == "__main__":
    main()
