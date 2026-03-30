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
    },
    {
        "title": "Sendo",
        "address": "20 Truong Son, Tan Binh",
        "phone": None,
        "website": None,
        "rating": 3.8,
    },
]


def test_search_returns_normalized_companies():
    mock_result = MagicMock()
    mock_result.get_dict.return_value = {"local_results": MOCK_LOCAL_RESULTS}

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


def test_search_handles_no_local_results():
    mock_result = MagicMock()
    mock_result.get_dict.return_value = {}

    with patch("src.serp_client.GoogleSearch") as MockGoogleSearch:
        MockGoogleSearch.return_value = mock_result
        client = SerpClient(api_key="fake_key")
        results = client.search(location="Nowhere", industry="xyz")

    assert results == []


def test_search_handles_none_fields():
    mock_result = MagicMock()
    mock_result.get_dict.return_value = {
        "local_results": [
            {"title": "Company X"}
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
