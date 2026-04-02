#!/usr/bin/env python3
"""
analyze_companies.py — Đọc file companies markdown và phân tích với DeepSeek.

Usage:
    python analyze_companies.py companies_ho_chi_minh_ecommerce_20260401_111846.md
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
OUTPUT_DIR = "response_deepseek"

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

_EMPTY_RESULT = {
    "leadership": [],
    "contact": {
        "emails": [], "phones": [], "linkedin_company": "",
        "facebook": "", "twitter": "", "youtube": "", "other_socials": [],
    },
    "services": [],
    "summary": "",
}

# ─── CSV columns ──────────────────────────────────────────────────────────────
CSV_FIELDNAMES = [
    "company_name", "website", "address", "phone", "rating", "description",
    "person_name", "person_title", "person_linkedin", "person_email", "person_note",
    "company_emails", "company_phones",
    "linkedin_company", "facebook", "twitter", "youtube", "other_socials",
    "services", "summary",
]


def parse_companies_markdown(filepath: str) -> list[dict]:
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
            "name": name, "website": "", "address": "",
            "phone": "", "rating": "", "description": "", "content": "",
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
    content = company.get("content", "")
    if not content:
        return {**_EMPTY_RESULT, "summary": "Không có nội dung website."}

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _ANALYSIS_SYSTEM},
                {"role": "user", "content": _ANALYSIS_TEMPLATE.format(content=content)},
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


def to_csv_rows(company: dict, analysis: dict) -> list[dict]:
    """Flatten one company + analysis into CSV rows (one row per leader, min 1 row)."""
    base = {
        "company_name":    company["name"],
        "website":         company["website"],
        "address":         company["address"],
        "phone":           company["phone"],
        "rating":          company["rating"],
        "description":     company["description"],
        "company_emails":  " | ".join(analysis["contact"].get("emails", [])),
        "company_phones":  " | ".join(analysis["contact"].get("phones", [])),
        "linkedin_company": analysis["contact"].get("linkedin_company", ""),
        "facebook":        analysis["contact"].get("facebook", ""),
        "twitter":         analysis["contact"].get("twitter", ""),
        "youtube":         analysis["contact"].get("youtube", ""),
        "other_socials":   " | ".join(analysis["contact"].get("other_socials", [])),
        "services":        " | ".join(analysis.get("services", [])),
        "summary":         analysis.get("summary", ""),
    }

    leadership = analysis.get("leadership", [])
    if not leadership:
        return [{**base, "person_name": "", "person_title": "",
                 "person_linkedin": "", "person_email": "", "person_note": ""}]

    rows = []
    for person in leadership:
        rows.append({
            **base,
            "person_name":    person.get("name", ""),
            "person_title":   person.get("title", ""),
            "person_linkedin": person.get("linkedin", ""),
            "person_email":   person.get("email", ""),
            "person_note":    person.get("note", ""),
        })
    return rows


def print_company_result(i: int, total: int, company: dict, analysis: dict):
    SEP = "─" * 60
    name = company["name"]
    website = company["website"]
    summary = analysis.get("summary", "")
    leadership = analysis.get("leadership", [])
    contact = analysis.get("contact", {})
    services = analysis.get("services", [])

    print(f"\n{SEP}")
    print(f"  [{i}/{total}]  {name}")
    print(f"  Web     : {website}")
    print(f"  Summary : {summary}")

    if leadership:
        print(f"  {'─'*10} Leadership / BOD {'─'*10}")
        for p in leadership:
            li = f"\n             LinkedIn : {p['linkedin']}" if p.get("linkedin") else ""
            em = f"\n             Email    : {p['email']}" if p.get("email") else ""
            nt = f"\n             Note     : {p['note']}" if p.get("note") else ""
            print(f"  • {p['name']}  |  {p['title']}{li}{em}{nt}")

    if contact.get("emails") or contact.get("phones"):
        print(f"  {'─'*10} Contact {'─'*10}")
        if contact.get("emails"):
            print(f"  Email   : {' | '.join(contact['emails'])}")
        if contact.get("phones"):
            print(f"  Phone   : {' | '.join(contact['phones'])}")

    socials = {k: v for k, v in contact.items()
               if k not in ("emails", "phones", "other_socials") and v}
    if socials or contact.get("other_socials"):
        print(f"  {'─'*10} Social {'─'*10}")
        for k, v in socials.items():
            print(f"  {k:<18}: {v}")
        for url in contact.get("other_socials", []):
            print(f"  other             : {url}")

    if services:
        print(f"  {'─'*10} Services {'─'*10}")
        for s in services:
            print(f"  • {s}")

    print(SEP)


def main():
    parser = argparse.ArgumentParser(description="Analyze companies markdown with DeepSeek")
    parser.add_argument("file", help="Path to companies markdown file")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: File not found: {args.file}")
        sys.exit(1)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path    = os.path.join(OUTPUT_DIR, f"deepseek_{timestamp}.csv")
    result_path = os.path.join(OUTPUT_DIR, f"deepseek_{timestamp}_result.json")

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    print(f"╔{'═'*58}╗")
    print(f"║  Model   : {MODEL:<46}║")
    print(f"║  API     : {BASE_URL:<46}║")
    print(f"║  Input   : {os.path.basename(args.file):<46}║")
    print(f"║  CSV     : {csv_path:<46}║")
    print(f"║  Result  : {result_path:<46}║")
    print(f"╚{'═'*58}╝")

    print(f"\nParsing {args.file}...")
    companies = parse_companies_markdown(args.file)
    print(f"Found {len(companies)} companies. Analyzing with DeepSeek ({MODEL})...\n")

    all_results = []
    all_csv_rows = []

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()

        for i, company in enumerate(companies, 1):
            print(f"[{i}/{len(companies)}] {company['name']}...")
            analysis = analyze_company(client, company)

            result = {
                "company_name": company["name"],
                "website":      company["website"],
                "address":      company["address"],
                "phone":        company["phone"],
                "rating":       company["rating"],
                "description":  company["description"],
                "analysis":     analysis,
            }
            all_results.append(result)

            rows = to_csv_rows(company, analysis)
            for row in rows:
                writer.writerow(row)
            all_csv_rows.extend(rows)

            print_company_result(i, len(companies), company, analysis)

    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n{'═'*60}")
    print(f"  Done! {len(companies)} companies analyzed.")
    print(f"  Model   : {MODEL}")
    print(f"  CSV     : {csv_path}  ({len(all_csv_rows)} rows)")
    print(f"  Result  : {result_path}")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
