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


def save_markdown_report(
    companies: list[dict],
    location: str,
    industry: str,
    output_dir: str = "."
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_location = location.replace(" ", "_").lower()
    safe_industry = industry.replace(" ", "_").lower()
    filename = f"companies_{safe_location}_{safe_industry}_{timestamp}.md"
    filepath = os.path.join(output_dir, filename)

    lines = [
        f"# {industry.title()} Companies in {location}",
        f"",
        f"_Crawled at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — Total: {len(companies)}_",
        f"",
        "---",
        "",
    ]

    for company in companies:
        name = company.get("name") or "Unknown"
        url = company.get("website") or ""
        thumbnail = company.get("thumbnail") or ""
        address = company.get("address") or ""
        phone = company.get("phone") or ""
        description = company.get("description") or ""
        rating = company.get("rating")
        reviews = company.get("reviews")
        markdown_content = company.get("markdown_content") or ""

        lines.append(f"## {name}")
        lines.append("")
        if thumbnail:
            lines.append(f"![{name} logo]({thumbnail})")
            lines.append("")
        if url:
            lines.append(f"**Website:** [{url}]({url})  ")
        if address:
            lines.append(f"**Address:** {address}  ")
        if phone:
            lines.append(f"**Phone:** {phone}  ")
        if rating is not None:
            rating_str = f"**Rating:** {rating}"
            if reviews:
                rating_str += f" ({reviews} reviews)"
            lines.append(rating_str + "  ")
        if description:
            lines.append(f"**Description:** {description}  ")
        lines.append("")

        if markdown_content:
            lines.append("### Website Content")
            lines.append("")
            lines.append(markdown_content.strip())
            lines.append("")

        lines.append("---")
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
