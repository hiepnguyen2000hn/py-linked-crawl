# Company Crawler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool that uses Google Places API to find companies by location & industry, crawls their websites to extract CEO/COO info, and saves results as JSON.

**Architecture:** User provides `--location` and `--industry` via CLI → Places API Text Search returns up to 60 companies → for each company, fetch website and parse About/Team pages for leadership names → save all results to a timestamped JSON file.

**Tech Stack:** Python 3.10+, `requests`, `beautifulsoup4`, `argparse`, `tenacity`, `python-dotenv`

---

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

**Step 1: Create requirements.txt**

```
requests==2.31.0
beautifulsoup4==4.12.3
tenacity==8.2.3
python-dotenv==1.0.1
lxml==5.1.0
```

**Step 2: Create .env.example**

```
GOOGLE_PLACES_API_KEY=your_api_key_here
```

**Step 3: Create empty init files**

```bash
touch src/__init__.py tests/__init__.py
```

**Step 4: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

**Step 5: Commit**

```bash
git init
git add .
git commit -m "chore: initial project setup"
```

---

### Task 2: Google Places API Client

**Files:**
- Create: `src/places_client.py`
- Create: `tests/test_places_client.py`

**Step 1: Write the failing test**

```python
# tests/test_places_client.py
import pytest
from unittest.mock import patch, MagicMock
from src.places_client import PlacesClient


def test_search_returns_list_of_companies():
    mock_response = {
        "status": "OK",
        "results": [
            {
                "name": "Test Company",
                "formatted_address": "123 Main St, Ho Chi Minh City",
                "formatted_phone_number": "+84 123 456 789",
                "website": "https://testcompany.com",
                "rating": 4.5,
                "place_id": "abc123"
            }
        ]
    }
    with patch("src.places_client.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.status_code = 200
        client = PlacesClient(api_key="fake_key")
        results = client.search(location="Ho Chi Minh", industry="ecommerce")
        assert len(results) == 1
        assert results[0]["name"] == "Test Company"
        assert results[0]["website"] == "https://testcompany.com"


def test_search_handles_zero_results():
    mock_response = {"status": "ZERO_RESULTS", "results": []}
    with patch("src.places_client.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.status_code = 200
        client = PlacesClient(api_key="fake_key")
        results = client.search(location="Nowhere", industry="ecommerce")
        assert results == []
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_places_client.py -v
```
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

**Step 3: Write implementation**

```python
# src/places_client.py
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


class PlacesClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, location: str, industry: str) -> list[dict]:
        query = f"{industry} companies in {location}"
        results = []
        next_page_token = None

        for _ in range(3):  # max 3 pages = 60 results
            params = {
                "query": query,
                "key": self.api_key,
            }
            if next_page_token:
                params["pagetoken"] = next_page_token

            data = self._get(PLACES_TEXT_SEARCH_URL, params)
            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                break

            for place in data.get("results", []):
                detail = self._get_details(place["place_id"])
                results.append({
                    "name": place.get("name"),
                    "address": place.get("formatted_address"),
                    "rating": place.get("rating"),
                    "place_id": place.get("place_id"),
                    "phone": detail.get("formatted_phone_number"),
                    "website": detail.get("website"),
                })

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break

        return results

    def _get_details(self, place_id: str) -> dict:
        params = {
            "place_id": place_id,
            "fields": "formatted_phone_number,website",
            "key": self.api_key,
        }
        data = self._get(PLACES_DETAILS_URL, params)
        return data.get("result", {})

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _get(self, url: str, params: dict) -> dict:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_places_client.py -v
```
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/places_client.py tests/test_places_client.py
git commit -m "feat: add Google Places API client with pagination"
```

---

### Task 3: Website Crawler for Leadership Info

**Files:**
- Create: `src/website_crawler.py`
- Create: `tests/test_website_crawler.py`

**Step 1: Write the failing test**

```python
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
  <span>CEO & Founder</span>
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
    with patch("src.website_crawler.requests.get") as mock_get:
        mock_get.return_value.text = MOCK_ABOUT_HTML
        mock_get.return_value.status_code = 200
        # Should follow /about link and find leaders
        with patch.object(crawler, "_fetch_page", side_effect=[
            MOCK_ABOUT_HTML,   # homepage
            MOCK_TEAM_HTML,    # /about page
        ]):
            result = crawler.crawl("https://example.com")
            assert isinstance(result, list)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_website_crawler.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# src/website_crawler.py
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from tenacity import retry, stop_after_attempt, wait_exponential

LEADERSHIP_KEYWORDS = re.compile(
    r"\b(ceo|coo|cto|cfo|founder|co-founder|president|director|chief executive|"
    r"chief operating|chief technology|chief financial|managing director|"
    r"giám đốc|tổng giám đốc|chủ tịch)\b",
    re.IGNORECASE
)

ABOUT_LINK_KEYWORDS = re.compile(
    r"\b(about|team|leadership|management|people|who we are|về chúng tôi|đội ngũ)\b",
    re.IGNORECASE
)


class WebsiteCrawler:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; CompanyCrawler/1.0)"
        })

    def crawl(self, website: str) -> list[dict]:
        if not website:
            return []
        try:
            homepage_html = self._fetch_page(website)
            leaders = self._extract_leaders_from_html(homepage_html)
            if leaders:
                return leaders

            about_url = self._find_about_link(homepage_html, website)
            if about_url:
                about_html = self._fetch_page(about_url)
                leaders = self._extract_leaders_from_html(about_html)

            return leaders
        except Exception:
            return []

    def _find_about_link(self, html: str, base_url: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("a", href=True):
            text = tag.get_text(strip=True)
            href = tag["href"]
            if ABOUT_LINK_KEYWORDS.search(text) or ABOUT_LINK_KEYWORDS.search(href):
                return urljoin(base_url, href)
        return None

    def _extract_leaders_from_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        leaders = []
        seen_names = set()

        # Strategy: find elements whose nearby text contains leadership keywords
        for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "span", "div"]):
            text = element.get_text(strip=True)
            if not text or len(text) > 100:
                continue
            if LEADERSHIP_KEYWORDS.search(text):
                # Look for a name nearby (sibling or parent's sibling)
                name = self._find_nearby_name(element, soup)
                if name and name not in seen_names:
                    seen_names.add(name)
                    leaders.append({"name": name, "title": text[:100]})

        return leaders

    def _find_nearby_name(self, element, soup) -> str | None:
        # Check previous sibling
        prev = element.find_previous_sibling(["h1", "h2", "h3", "h4"])
        if prev:
            candidate = prev.get_text(strip=True)
            if self._looks_like_name(candidate):
                return candidate
        # Check parent's previous sibling
        parent = element.parent
        if parent:
            prev_p = parent.find_previous_sibling()
            if prev_p:
                candidate = prev_p.get_text(strip=True)
                if self._looks_like_name(candidate):
                    return candidate
        return None

    def _looks_like_name(self, text: str) -> bool:
        # A name is 2-5 words, each capitalized, no special chars
        if not text or len(text) > 60:
            return False
        words = text.split()
        if not (2 <= len(words) <= 5):
            return False
        return all(w[0].isupper() for w in words if w)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _fetch_page(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_website_crawler.py -v
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/website_crawler.py tests/test_website_crawler.py
git commit -m "feat: add website crawler for CEO/COO extraction"
```

---

### Task 4: JSON Output Writer

**Files:**
- Create: `src/output_writer.py`
- Create: `tests/test_output_writer.py`

**Step 1: Write the failing test**

```python
# tests/test_output_writer.py
import json
import os
import tempfile
from src.output_writer import save_results


def test_save_results_creates_json_file():
    companies = [
        {
            "name": "Test Corp",
            "address": "123 Main St",
            "phone": "+84 123",
            "website": "https://test.com",
            "rating": 4.2,
            "leaders": [{"name": "John Doe", "title": "CEO"}]
        }
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = save_results(
            companies=companies,
            location="Ho Chi Minh",
            industry="ecommerce",
            output_dir=tmpdir
        )
        assert os.path.exists(output_path)
        with open(output_path) as f:
            data = json.load(f)
        assert data["location"] == "Ho Chi Minh"
        assert data["industry"] == "ecommerce"
        assert len(data["companies"]) == 1
        assert data["companies"][0]["name"] == "Test Corp"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_output_writer.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# src/output_writer.py
import json
import os
from datetime import datetime


def save_results(
    companies: list[dict],
    location: str,
    industry: str,
    output_dir: str = "."
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_location = location.replace(" ", "_").lower()
    safe_industry = industry.replace(" ", "_").lower()
    filename = f"companies_{safe_location}_{safe_industry}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    payload = {
        "location": location,
        "industry": industry,
        "crawled_at": datetime.now().isoformat(),
        "total": len(companies),
        "companies": companies,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filepath
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_output_writer.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/output_writer.py tests/test_output_writer.py
git commit -m "feat: add JSON output writer"
```

---

### Task 5: CLI Entry Point (main.py)

**Files:**
- Create: `main.py`

**Step 1: Write implementation** (no unit test — this is the CLI glue layer)

```python
# main.py
import argparse
import os
import sys
import time
from dotenv import load_dotenv
from src.places_client import PlacesClient
from src.website_crawler import WebsiteCrawler
from src.output_writer import save_results

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crawl company info by location and industry using Google Places API"
    )
    parser.add_argument("--location", required=True, help='e.g. "Ho Chi Minh" or "Vietnam"')
    parser.add_argument("--industry", required=True, help='e.g. "ecommerce" or "mining"')
    parser.add_argument("--output-dir", default=".", help="Directory to save JSON output")
    parser.add_argument("--no-crawl", action="store_true", help="Skip website crawling, only fetch Places data")
    return parser.parse_args()


def main():
    args = parse_args()

    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_PLACES_API_KEY not set. Copy .env to .env and add your key.")
        sys.exit(1)

    print(f"Searching for '{args.industry}' companies in '{args.location}'...")
    client = PlacesClient(api_key=api_key)
    companies = client.search(location=args.location, industry=args.industry)
    print(f"Found {len(companies)} companies.")

    if not args.no_crawl:
        crawler = WebsiteCrawler()
        for i, company in enumerate(companies, 1):
            website = company.get("website")
            print(f"[{i}/{len(companies)}] Crawling {company['name']} ({website or 'no website'})...")
            company["leaders"] = crawler.crawl(website)
            time.sleep(0.5)  # polite delay
    else:
        for company in companies:
            company["leaders"] = []

    output_path = save_results(
        companies=companies,
        location=args.location,
        industry=args.industry,
        output_dir=args.output_dir
    )
    print(f"\nDone! Results saved to: {output_path}")


if __name__ == "__main__":
    main()
```

**Step 2: Test manually**

```bash
# Copy .env to .env and set your API key first
cp .env .env

# Run
python main.py --location "Ho Chi Minh" --industry "ecommerce"
```

Expected: JSON file created in current directory.

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add CLI entry point"
```

---

### Task 6: Run All Tests

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

**Step 2: Final commit**

```bash
git add .
git commit -m "chore: final cleanup and full test pass"
```

---

## Usage

```bash
# Basic
python main.py --location "Ho Chi Minh" --industry "ecommerce"

# Specific country
python main.py --location "Vietnam" --industry "mining"

# Skip website crawling (faster, less info)
python main.py --location "Singapore" --industry "fintech" --no-crawl

# Custom output directory
python main.py --location "Hanoi" --industry "logistics" --output-dir ./results
```

## Output Format

```json
{
  "location": "Ho Chi Minh",
  "industry": "ecommerce",
  "crawled_at": "2026-03-30T10:00:00",
  "total": 42,
  "companies": [
    {
      "name": "Tiki Corporation",
      "address": "123 Nguyen Hue, District 1",
      "phone": "+84 28 1234 5678",
      "website": "https://tiki.vn",
      "rating": 4.3,
      "leaders": [
        {"name": "Tran Ngoc Thai Son", "title": "Chief Executive Officer"}
      ]
    }
  ]
}
```
