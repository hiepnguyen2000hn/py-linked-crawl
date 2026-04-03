# src/linkedin_enricher.py
import re
import time
from serpapi import GoogleSearch

LI_PATTERN = re.compile(
    r'https?://(?:www\.)?linkedin\.com/in/[^\s"\'<>\)\]\,]+',
    re.IGNORECASE
)
DELAY = 1.5  # seconds between requests to avoid rate limiting


class LinkedInEnricher:
    """Enrich leader dicts with personal LinkedIn URLs via SerpAPI Google search.

    For each leader with an empty 'linkedin' field, searches Google:
      "name" "title" "company" site:linkedin.com/in/
    and assigns the first linkedin.com/in/ URL found.

    Leaders that already have a linkedin URL are skipped (no API call).
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def enrich(self, leaders: list[dict], company_name: str = "") -> list[dict]:
        """Add 'linkedin' field to leaders missing it. Mutates and returns list."""
        for leader in leaders:
            if leader.get("linkedin", "").strip():
                continue  # already has one — skip, no API call
            name = leader.get("name", "").strip()
            if not name:
                leader["linkedin"] = ""
                continue
            title = leader.get("title", "").strip()
            url = self._search(name, title, company_name)
            leader["linkedin"] = url
            if url:
                print(f"    [LinkedIn] {name} => {url}")
            else:
                print(f"    [LinkedIn] {name} => not found")
            time.sleep(DELAY)
        return leaders

    def _search(self, name: str, title: str, company: str) -> str:
        """Search Google for a person's LinkedIn profile URL.

        Returns first linkedin.com/in/ URL found, or empty string.
        """
        parts = [f'"{name}"']
        if title:
            # Use only first part of title before dash/comma to avoid noise
            clean_title = re.split(r'[–\-,]', title)[0].strip()
            if clean_title:
                parts.append(f'"{clean_title}"')
        if company:
            parts.append(f'"{company}"')
        parts.append("site:linkedin.com/in")
        query = " ".join(parts)

        try:
            params = {
                "engine": "google",
                "q": query,
                "num": 5,
                "api_key": self.api_key,
            }
            data = GoogleSearch(params).get_dict()

            # Check organic results first (most reliable)
            for item in data.get("organic_results", []):
                link = item.get("link", "")
                if "linkedin.com/in/" in link:
                    return link.split("?")[0]  # strip query params

            # Fallback: scan raw response JSON for any linkedin.com/in/ URL
            matches = LI_PATTERN.findall(str(data))
            if matches:
                return matches[0].rstrip(".,;)")

        except Exception as e:
            print(f"    [LinkedInEnricher] search failed for {name!r}: {e}")

        return ""
