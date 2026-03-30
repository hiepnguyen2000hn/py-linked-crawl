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
