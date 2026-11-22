import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def local_app_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    import httpx

    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{url}/healthz", timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        pytest.fail("Local test server did not start")
    yield url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"Playwright Chromium is not installed: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        yield page
        browser.close()
