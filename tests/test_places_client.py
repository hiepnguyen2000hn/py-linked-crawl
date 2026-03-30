# tests/test_places_client.py
import pytest
from unittest.mock import patch, MagicMock
from src.places_client import PlacesClient


def test_search_returns_list_of_companies():
    mock_response_text_search = {
        "status": "OK",
        "results": [
            {
                "name": "Test Company",
                "formatted_address": "123 Main St, Ho Chi Minh City",
                "rating": 4.5,
                "place_id": "abc123"
            }
        ]
    }
    mock_response_details = {
        "status": "OK",
        "result": {
            "formatted_phone_number": "+84 123 456 789",
            "website": "https://testcompany.com"
        }
    }
    with patch("src.places_client.requests.get") as mock_get:
        mock_get.return_value.json.side_effect = [
            mock_response_text_search,
            mock_response_details,
        ]
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
