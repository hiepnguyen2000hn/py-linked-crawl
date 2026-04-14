# src/serp_client.py
from serpapi import GoogleSearch


class SerpClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, location: str, industry: str, pages: int = 1, start_page: int = 1) -> list[dict]:
        """Search companies. Each page returns up to 20 results (google_local limit).
        Uses start=0,20,40,... for pagination. Stops early if no more results.
        start_page: which page to begin from (1-indexed). e.g. start_page=2 skips first 20 results."""
        all_results = []
        start = (start_page - 1) * 20
        for page in range(pages):
            params = {
                "engine": "google_local",
                "q": f"{industry} companies",
                "location": location,
                "hl": "en",
                "start": start,
                "api_key": self.api_key,
            }
            result = GoogleSearch(params)
            data = result.get_dict()
            local_results = data.get("local_results", [])
            if not local_results:
                break
            all_results.extend([self._normalize(r) for r in local_results])
            print(f"  [SerpAPI] Page {page + 1}: {len(local_results)} results (start={start})")
            if not data.get("serpapi_pagination", {}).get("next"):
                break
            start += 20
        return all_results

    def _normalize(self, raw: dict) -> dict:
        links = raw.get("links") or {}
        return {
            "name": raw.get("title"),
            "address": raw.get("address"),
            "phone": raw.get("phone"),
            "website": links.get("website") or raw.get("website"),
            "rating": raw.get("rating"),
            "reviews": raw.get("reviews"),
            "description": raw.get("description"),
            "place_id": raw.get("place_id", ""),
            "thumbnail": raw.get("thumbnail"),
        }
