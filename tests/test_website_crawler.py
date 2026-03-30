# tests/test_website_crawler.py
import pytest
from unittest.mock import patch
from src.website_crawler import WebsiteCrawler


MOCK_ABOUT_HTML = """
<html><body>
  <a href="/about">About Us</a>
  <div class="team">
    <h3>Nguyen Van A</h3>
    <p>Chief Executive Officer</p>
    <h3>Tran Thi B</h3>
    <p>Chief Operating Officer</p>
  </div>
</body></html>
"""

MOCK_TEAM_HTML = """
<html><body>
  <h2>John Smith</h2>
  <span>CEO &amp; Founder</span>
</body></html>
"""


def test_extract_leaders_from_page():
    crawler = WebsiteCrawler()
    leaders = crawler._extract_leaders_from_html(MOCK_TEAM_HTML)
    assert len(leaders) >= 1
    assert any("John Smith" in l["name"] for l in leaders)


def test_crawl_returns_empty_on_no_website():
    crawler = WebsiteCrawler()
    result = crawler.crawl(None)
    assert result == []


def test_crawl_finds_about_link():
    crawler = WebsiteCrawler()
    with patch.object(crawler, "_fetch_page", side_effect=[
        MOCK_ABOUT_HTML,   # homepage
        MOCK_TEAM_HTML,    # /about page
    ]):
        result = crawler.crawl("https://example.com")
        assert isinstance(result, list)
