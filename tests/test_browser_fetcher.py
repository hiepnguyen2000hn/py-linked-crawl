# tests/test_browser_fetcher.py
import pytest
from unittest.mock import patch, MagicMock
from src.browser_fetcher import fetch_html


def test_uses_requests_when_response_is_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><body>hello</body></html>"

    with patch("src.browser_fetcher.requests.Session") as MockSession:
        MockSession.return_value.get.return_value = mock_resp
        html = fetch_html("https://example.com")

    assert "hello" in html


def test_falls_back_to_playwright_on_403():
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "forbidden"

    with patch("src.browser_fetcher.requests.Session") as MockSession, \
         patch("src.browser_fetcher._fetch_with_playwright") as mock_pw:
        MockSession.return_value.get.return_value = mock_resp
        mock_pw.return_value = "<html><body>playwright content</body></html>"
        html = fetch_html("https://protected.com")

    mock_pw.assert_called_once_with("https://protected.com", timeout=10)
    assert "playwright content" in html


def test_falls_back_to_playwright_on_cloudflare_challenge():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html><head><title>Just a moment...</title></head></html>"

    with patch("src.browser_fetcher.requests.Session") as MockSession, \
         patch("src.browser_fetcher._fetch_with_playwright") as mock_pw:
        MockSession.return_value.get.return_value = mock_resp
        mock_pw.return_value = "<html><body>real content</body></html>"
        html = fetch_html("https://cloudflare-site.com")

    mock_pw.assert_called_once()
    assert "real content" in html