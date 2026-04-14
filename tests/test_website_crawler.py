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

MOCK_SOCIAL_HTML = """
<html><body>
  <a href="https://www.facebook.com/companyxyz">Facebook</a>
  <a href="https://instagram.com/companyxyz">Instagram</a>
  <a href="https://linkedin.com/company/companyxyz">LinkedIn</a>
  <a href="https://twitter.com/companyxyz">Twitter</a>
  <a href="mailto:contact@companyxyz.com">Email us</a>
  <a href="https://youtube.com/channel/xyz">YouTube</a>
</body></html>
"""

MOCK_FULL_HTML = """
<html><body>
  <h2>Jane Doe</h2>
  <span>CEO &amp; Founder</span>
  <a href="https://facebook.com/acme">Facebook</a>
  <a href="mailto:hello@acme.com">Contact</a>
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
    assert result == {"leaders": [], "socials": {}}


def test_crawl_finds_about_link():
    crawler = WebsiteCrawler()
    with patch.object(crawler, "_fetch_page", side_effect=[
        MOCK_ABOUT_HTML,   # homepage
        MOCK_TEAM_HTML,    # /about page
    ]):
        result = crawler.crawl("https://example.com")
        assert isinstance(result["leaders"], list)


def test_extract_socials_finds_facebook_and_instagram():
    crawler = WebsiteCrawler()
    socials = crawler._extract_socials_from_html(MOCK_SOCIAL_HTML)
    assert socials.get("facebook") == "https://www.facebook.com/companyxyz"
    assert socials.get("instagram") == "https://instagram.com/companyxyz"


def test_extract_socials_finds_email():
    crawler = WebsiteCrawler()
    socials = crawler._extract_socials_from_html(MOCK_SOCIAL_HTML)
    assert socials.get("email") == "contact@companyxyz.com"


def test_extract_socials_finds_linkedin_twitter_youtube():
    crawler = WebsiteCrawler()
    socials = crawler._extract_socials_from_html(MOCK_SOCIAL_HTML)
    assert "linkedin" in socials
    assert "twitter" in socials
    assert "youtube" in socials


def test_crawl_returns_leaders_and_socials():
    crawler = WebsiteCrawler()
    with patch.object(crawler, "_fetch_page", return_value=MOCK_FULL_HTML):
        result = crawler.crawl("https://example.com")
    assert "leaders" in result
    assert "socials" in result
    assert result["socials"].get("facebook") == "https://facebook.com/acme"
    assert result["socials"].get("email") == "hello@acme.com"
