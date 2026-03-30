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
