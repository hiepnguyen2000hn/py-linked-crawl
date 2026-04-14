# SerpAPI Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SerpAPI as an alternative data source alongside Google Places API, selectable via `--source serpapi` or `--source google` CLI flag.

**Architecture:** Create `src/serp_client.py` with the same `search(location, industry) -> list[dict]` interface as `PlacesClient` using SerpAPI's `google_local` engine. Update `main.py` to accept `--source` flag and instantiate the correct client. Both clients return identical dict shape so the rest of the pipeline (crawler, output writer) is unchanged.

**Tech Stack:** `google-search-results` (SerpAPI Python SDK), existing `requests`, `tenacity`

---

### Task 1: Add SerpAPI dependency

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

**Step 1: Add dependency to requirements.txt**

Append this line to `C:/code/crawl/requirements.txt`:
```
google-search-results==2.4.2
```

Final file:
```
requests==2.31.0
beautifulsoup4==4.12.3
tenacity==8.2.3
python-dotenv==1.0.1
lxml==5.1.0
google-search-results==2.4.2
```

**Step 2: Add SERPAPI_KEY to .env.example**

Final file:
```
GOOGLE_PLACES_API_KEY=your_google_api_key_here
SERPAPI_KEY=your_serpapi_key_here
```

**Step 3: Install new dependency**

```bash
cd C:/code/crawl && pip install google-search-results==2.4.2
```

Expected: installs without error.

**Step 4: Commit**

```bash
cd C:/code/crawl && git add requirements.txt .env && git commit -m "chore: add serpapi dependency"
```

---

### Task 2: SerpAPI Client

**Files:**
- Create: `src/serp_client.py`
- Create: `tests/test_serp_client.py`

**Step 1: Write the failing test**

```python
# tests/test_serp_client.py
import pytest
from unittest.mock import patch, MagicMock
from src.serp_client import SerpClient


MOCK_LOCAL_RESULTS = [
    {
        "title": "Tiki Corp",
        "address": "52 Ut Tich, Ward 4, Tan Binh",
        "phone": "+84 28 1234 5678",
        "website": "https://tiki.vn",
        "rating": 4.2,
        "type": "E-commerce company",
    },
    {
        "title": "Sendo",
        "address": "20 Truong Son, Tan Binh",
        "phone": None,
        "website": None,
        "rating": 3.8,
        "type": "Online marketplace",
    },
]


def test_search_returns_normalized_companies():
    mock_result = MagicMock()
    mock_result.as_dict.return_value = {"local_results": MOCK_LOCAL_RESULTS}

    with patch("src.serp_client.GoogleSearch") as MockGoogleSearch:
        MockGoogleSearch.return_value = mock_result
        client = SerpClient(api_key="fake_key")
        results = client.search(location="Ho Chi Minh", industry="ecommerce")

    assert len(results) == 2
    assert results[0]["name"] == "Tiki Corp"
    assert results[0]["website"] == "https://tiki.vn"
    assert results[0]["phone"] == "+84 28 1234 5678"
    assert results[0]["address"] == "52 Ut Tich, Ward 4, Tan Binh"
    assert results[0]["rating"] == 4.2
    assert "place_id" in results[0]
    assert "leaders" not in results[0]


def test_search_handles_no_local_results():
    mock_result = MagicMock()
    mock_result.as_dict.return_value = {}

    with patch("src.serp_client.GoogleSearch") as MockGoogleSearch:
        MockGoogleSearch.return_value = mock_result
        client = SerpClient(api_key="fake_key")
        results = client.search(location="Nowhere", industry="xyz")

    assert results == []


def test_search_handles_none_fields():
    mock_result = MagicMock()
    mock_result.as_dict.return_value = {
        "local_results": [
            {"title": "Company X"}  # minimal — no phone/website/rating
        ]
    }

    with patch("src.serp_client.GoogleSearch") as MockGoogleSearch:
        MockGoogleSearch.return_value = mock_result
        client = SerpClient(api_key="fake_key")
        results = client.search(location="Hanoi", industry="fintech")

    assert len(results) == 1
    assert results[0]["name"] == "Company X"
    assert results[0]["phone"] is None
    assert results[0]["website"] is None
    assert results[0]["rating"] is None
```

**Step 2: Run test to verify it FAILS**

```bash
cd C:/code/crawl && python -m pytest tests/test_serp_client.py -v
```
Expected: ImportError — `src.serp_client` does not exist yet.

**Step 3: Write implementation**

```python
# src/serp_client.py
from serpapi import GoogleSearch


class SerpClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, location: str, industry: str) -> list[dict]:
        params = {
            "engine": "google_local",
            "q": f"{industry} companies",
            "location": location,
            "hl": "en",
            "api_key": self.api_key,
        }
        result = GoogleSearch(params)
        data = result.as_dict()
        local_results = data.get("local_results", [])
        return [self._normalize(r) for r in local_results]

    def _normalize(self, raw: dict) -> dict:
        return {
            "name": raw.get("title"),
            "address": raw.get("address"),
            "phone": raw.get("phone"),
            "website": raw.get("website"),
            "rating": raw.get("rating"),
            "place_id": raw.get("place_id", ""),
        }
```

**Step 4: Run tests to verify they PASS**

```bash
cd C:/code/crawl && python -m pytest tests/test_serp_client.py -v
```
Expected: 3 tests PASS.

**Step 5: Commit**

```bash
cd C:/code/crawl && git add src/serp_client.py tests/test_serp_client.py && git commit -m "feat: add SerpAPI client"
```

---

### Task 3: Update main.py with --source flag

**Files:**
- Modify: `main.py`

**Step 1: Read current main.py** to understand what needs changing.

Current `main.py` hardcodes `PlacesClient`. We need to:
1. Add `--source` argument (choices: `google`, `serpapi`, default: `google`)
2. Conditionally instantiate `PlacesClient` or `SerpClient`
3. Validate the correct API key based on chosen source
4. Update description string

**Step 2: Write the new main.py**

```python
# main.py
import argparse
import os
import sys
import time
from dotenv import load_dotenv
from src.places_client import PlacesClient
from src.serp_client import SerpClient
from src.website_crawler import WebsiteCrawler
from src.output_writer import save_results

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crawl company info by location and industry"
    )
    parser.add_argument("--location", required=True, help='e.g. "Ho Chi Minh" or "Vietnam"')
    parser.add_argument("--industry", required=True, help='e.g. "ecommerce" or "mining"')
    parser.add_argument("--source", choices=["google", "serpapi"], default="google",
                        help="Data source: google (Places API) or serpapi (default: google)")
    parser.add_argument("--output-dir", default=".", help="Directory to save JSON output")
    parser.add_argument("--no-crawl", action="store_true",
                        help="Skip website crawling, only fetch company list")
    return parser.parse_args()


def build_client(source: str):
    if source == "serpapi":
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            print("ERROR: SERPAPI_KEY not set. Add it to your .env file.")
            sys.exit(1)
        return SerpClient(api_key=api_key)

    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_PLACES_API_KEY not set. Add it to your .env file.")
        sys.exit(1)
    return PlacesClient(api_key=api_key)


def main():
    args = parse_args()

    client = build_client(args.source)

    print(f"[{args.source}] Searching for '{args.industry}' companies in '{args.location}'...")
    companies = client.search(location=args.location, industry=args.industry)
    print(f"Found {len(companies)} companies.")

    if not args.no_crawl:
        crawler = WebsiteCrawler()
        for i, company in enumerate(companies, 1):
            website = company.get("website")
            print(f"[{i}/{len(companies)}] Crawling {company['name']} ({website or 'no website'})...")
            company["leaders"] = crawler.crawl(website)
            time.sleep(0.5)
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

**Step 3: Verify --help still works**

```bash
cd C:/code/crawl && python main.py --help
```

Expected output includes `--source {google,serpapi}`.

**Step 4: Commit**

```bash
cd C:/code/crawl && git add main.py && git commit -m "feat: add --source flag to select google or serpapi"
```

---

### Task 4: Run All Tests

**Step 1: Run full test suite**

```bash
cd C:/code/crawl && python -m pytest tests/ -v
```

Expected: All 11 tests PASS (8 existing + 3 new serp_client tests).

**Step 2: Final commit if any stray files**

```bash
cd C:/code/crawl && git status
```

If clean, no commit needed.

---

## Usage after integration

```bash
# Google Places API (default)
python main.py --location "Ho Chi Minh" --industry "ecommerce"

# SerpAPI
python main.py --location "Ho Chi Minh" --industry "ecommerce" --source serpapi

# SerpAPI, skip website crawl
python main.py --location "Vietnam" --industry "mining" --source serpapi --no-crawl
```
