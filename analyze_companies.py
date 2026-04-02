#!/usr/bin/env python3
"""
analyze_companies.py — Đọc file companies markdown và phân tích với DeepSeek.

Usage:
    python analyze_companies.py companies_ho_chi_minh_ecommerce_20260401_111846.md
    python analyze_companies.py companies_ho_chi_minh_ecommerce_20260401_111846.md --output results.json
"""
import argparse
import json
import os
import re
import sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_ANALYSIS_SYSTEM = (
    "You are a business analyst. Given crawled website content of a company, "
    "extract structured information and return ONLY valid JSON."
)

_ANALYSIS_TEMPLATE = """\
Analyze this company's website content and extract:
1. Leadership personnel (CEO, CTO, Founder, Director, etc.)
2. Main services/products (max 5)
3. One-sentence company summary in Vietnamese

Return ONLY a JSON object like:
{{
  "leaders": [{{"name": "...", "title": "..."}}],
  "services": ["...", "..."],
  "summary": "..."
}}
If a field has no data, use empty list [] or empty string "".

Website content:
{content}"""


def parse_companies_markdown(filepath: str) -> list[dict]:
    """Parse a companies markdown file into list of company dicts."""
    with open(filepath, encoding="utf-8") as f:
        text = f.read()

    sections = re.split(r"\n(?=## )", text)
    companies = []

    for section in sections:
        lines = section.strip().splitlines()
        if not lines or not lines[0].startswith("## "):
            continue

        name = lines[0][3:].strip()
        company = {
            "name": name,
            "website": "",
            "address": "",
            "phone": "",
            "rating": "",
            "description": "",
            "content": "",
        }

        for line in lines[1:]:
            if line.startswith("**Website:**"):
                m = re.search(r"\((.+?)\)", line)
                company["website"] = m.group(1) if m else ""
            elif line.startswith("**Address:**"):
                company["address"] = line.replace("**Address:**", "").strip()
            elif line.startswith("**Phone:**"):
                company["phone"] = line.replace("**Phone:**", "").strip()
            elif line.startswith("**Rating:**"):
                company["rating"] = line.replace("**Rating:**", "").strip()
            elif line.startswith("**Description:**"):
                company["description"] = line.replace("**Description:**", "").strip().strip('"')

        content_match = re.search(r"### Website Content\n(.*)", section, re.DOTALL)
        if content_match:
            company["content"] = content_match.group(1).strip()[:6000]

        companies.append(company)

    return companies


def analyze_company(client: OpenAI, company: dict) -> dict:
    """Run DeepSeek analysis on a company's content."""
    content = company.get("content", "")
    if not content:
        return {"leaders": [], "services": [], "summary": "Không có nội dung website."}

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _ANALYSIS_SYSTEM},
                {"role": "user", "content": _ANALYSIS_TEMPLATE.format(content=content[:5000])},
            ],
            temperature=0,
            max_tokens=1024,
        )
        generated = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", generated, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "leaders": data.get("leaders", []),
                "services": data.get("services", []),
                "summary": data.get("summary", ""),
            }
    except Exception as e:
        print(f"    [ERROR] DeepSeek call failed: {e}")
    return {"leaders": [], "services": [], "summary": ""}


def main():
    parser = argparse.ArgumentParser(description="Analyze companies markdown with DeepSeek")
    parser.add_argument("file", help="Path to companies markdown file")
    parser.add_argument("--output", help="Save results to JSON file (optional)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: File not found: {args.file}")
        sys.exit(1)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    print(f"Parsing {args.file}...")
    companies = parse_companies_markdown(args.file)
    print(f"Found {len(companies)} companies. Analyzing with DeepSeek...\n")

    results = []
    for i, company in enumerate(companies, 1):
        print(f"[{i}/{len(companies)}] Analyzing: {company['name']}...")
        analysis = analyze_company(client, company)
        result = {
            "name": company["name"],
            "website": company["website"],
            "address": company["address"],
            "phone": company["phone"],
            "rating": company["rating"],
            "description": company["description"],
            "deepseek_analysis": analysis,
        }
        results.append(result)

        summary = analysis.get("summary", "")
        leaders = analysis.get("leaders", [])
        services = analysis.get("services", [])
        print(f"  Summary  : {summary}")
        if leaders:
            print(f"  Leaders  : {[l['name'] + ' (' + l['title'] + ')' for l in leaders]}")
        if services:
            print(f"  Services : {services}")
        print()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Results saved to: {args.output}")
    else:
        print("\n=== FULL RESULTS ===")
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
