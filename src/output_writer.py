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
