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
    "You are a business intelligence analyst. Extract structured data from company website content. "
    "Return ONLY valid JSON, no explanation, no markdown code blocks."
)

_ANALYSIS_TEMPLATE = """\
Extract ALL of the following from the company website content below.

Return ONLY a JSON object with these exact keys:
{{
  "leadership": [
    {{
      "name": "full name",
      "title": "job title (CEO/CTO/CFO/COO/Founder/Director/BOD member/etc.)",
      "linkedin": "linkedin profile URL or empty string",
      "email": "personal email or empty string",
      "note": "any extra info (years experience, background) or empty string"
    }}
  ],
  "contact": {{
    "emails": ["list of company emails found"],
    "phones": ["list of phone numbers found"],
    "linkedin_company": "company LinkedIn page URL or empty string",
    "facebook": "Facebook page URL or empty string",
    "twitter": "Twitter/X URL or empty string",
    "youtube": "YouTube URL or empty string",
    "other_socials": ["any other social/contact URLs"]
  }},
  "services": ["main service or product 1", "..."],
  "summary": "one sentence describing the company in Vietnamese"
}}

Rules:
- Include ALL people with executive/leadership titles: CEO, CTO, CFO, COO, CPO, CMO, Founder, Co-founder, Director, Managing Director, President, Vice President, Head of, BOD member, Chairman, Giám đốc, Phó giám đốc, Tổng giám đốc, Chủ tịch, Thành viên HĐQT
- Extract emails like name@company.com or contact@company.com
- Extract all social media URLs (linkedin.com, facebook.com, twitter.com, x.com, youtube.com, instagram.com, etc.)
- If a field has no data use empty string "" or empty list []
- Do NOT invent data — only extract what is explicitly present in the text

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


_EMPTY_RESULT = {
    "leadership": [],
    "contact": {"emails": [], "phones": [], "linkedin_company": "", "facebook": "",
                "twitter": "", "youtube": "", "other_socials": []},
    "services": [],
    "summary": "",
}


def analyze_company(client: OpenAI, company: dict) -> dict:
    """Run DeepSeek analysis on a company's content."""
    content = company.get("content", "")
    if not content:
        return {**_EMPTY_RESULT, "summary": "Không có nội dung website."}

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _ANALYSIS_SYSTEM},
                {"role": "user", "content": _ANALYSIS_TEMPLATE.format(content=content[:6000])},
            ],
            temperature=0,
            max_tokens=2048,
        )
        generated = response.choices[0].message.content or ""
        match = re.search(r"\{.*\}", generated, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "leadership": data.get("leadership", []),
                "contact": data.get("contact", _EMPTY_RESULT["contact"]),
                "services": data.get("services", []),
                "summary": data.get("summary", ""),
            }
    except Exception as e:
        print(f"    [ERROR] DeepSeek call failed: {e}")
    return _EMPTY_RESULT


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
        leadership = analysis.get("leadership", [])
        contact = analysis.get("contact", {})
        services = analysis.get("services", [])
        print(f"  Summary   : {summary}")
        if leadership:
            for p in leadership:
                li = f" | {p['linkedin']}" if p.get("linkedin") else ""
                print(f"  Leader    : {p['name']} — {p['title']}{li}")
        if contact.get("emails"):
            print(f"  Emails    : {contact['emails']}")
        if contact.get("phones"):
            print(f"  Phones    : {contact['phones']}")
        socials = [v for k, v in contact.items()
                   if k not in ("emails", "phones", "other_socials") and v]
        if socials:
            print(f"  Socials   : {socials}")
        if services:
            print(f"  Services  : {services[:3]}")
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
