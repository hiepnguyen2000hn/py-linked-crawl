# src/browser_fetcher.py
import requests

_CF_MARKER = "Just a moment..."


def fetch_html(url: str, timeout: int = 10) -> str:
    """Fetch HTML from url. Falls back to Playwright if blocked by Cloudflare."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    })
    try:
        r = session.get(url, timeout=timeout)
        if r.status_code != 403 and _CF_MARKER not in r.text:
            return r.text
    except Exception:
        pass

    return _fetch_with_playwright(url, timeout=timeout)


def _fetch_with_playwright(url: str, timeout: int = 10) -> str:
    from playwright.sync_api import sync_playwright
    pw_timeout = max(timeout * 1000, 30_000)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = ctx.new_page()
        # Hide webdriver flag
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.goto(url, timeout=pw_timeout, wait_until="domcontentloaded")
        # Wait for CF challenge to pass
        try:
            page.wait_for_function(
                "() => document.title !== 'Just a moment...'",
                timeout=pw_timeout,
            )
        except Exception:
            pass
        html = page.content()
        browser.close()
        return html