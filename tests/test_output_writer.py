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


def test_save_results_filename_format():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = save_results(
            companies=[],
            location="Ho Chi Minh",
            industry="ecommerce",
            output_dir=tmpdir
        )
        filename = os.path.basename(output_path)
        assert filename.startswith("companies_ho_chi_minh_ecommerce_")
        assert filename.endswith(".json")


def test_save_results_includes_total():
    companies = [{"name": "A"}, {"name": "B"}]
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = save_results(
            companies=companies,
            location="Hanoi",
            industry="fintech",
            output_dir=tmpdir
        )
        with open(output_path) as f:
            data = json.load(f)
        assert data["total"] == 2
