"""
enrich_linkedin.py — Enrich leaders in existing response_deepseek/*.json files
with personal LinkedIn URLs via SerpAPI Google search.

Usage:
  python enrich_linkedin.py                         # process all files
  python enrich_linkedin.py --file <path>           # single file
  python enrich_linkedin.py --dry-run               # preview without API calls
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv
from src.linkedin_enricher import LinkedInEnricher

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

RESPONSE_DIR = "response_deepseek"


def is_junk_leader(leader: dict) -> bool:
    """Filter out noise entries extracted from reviews/FAQ text."""
    name = leader.get("name", "").strip()
    if len(name) > 60:
        return True
    if len(name) > 5 and name == name.lower():
        return True
    junk_keywords = ["frequently asked", "question", "commitment"]
    return any(k in name.lower() for k in junk_keywords)


def enrich_file(filepath: str, enricher: LinkedInEnricher) -> int:
    """Enrich all leaders in a single JSON file. Returns count of leaders with LinkedIn found."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    for company in data.get("companies", []):
        company_name = company.get("name", "")
        valid_leaders = [
            l for l in company.get("leaders", [])
            if not is_junk_leader(l)
        ]
        # Set empty linkedin on junk leaders so they have the field
        for l in company.get("leaders", []):
            if is_junk_leader(l):
                l.setdefault("linkedin", "")

        if valid_leaders:
            enricher.enrich(valid_leaders, company_name)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return sum(
        1 for c in data.get("companies", [])
        for l in c.get("leaders", [])
        if l.get("linkedin")
    )


def main():
    parser = argparse.ArgumentParser(
        description="Enrich leader LinkedIn URLs in response_deepseek/*.json files"
    )
    parser.add_argument("--file", help="Process a single JSON file instead of all files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview leaders that would be searched — no API calls")
    args = parser.parse_args()

    key = os.getenv("SERPAPI_KEY")
    if not key and not args.dry_run:
        sys.exit("ERROR: SERPAPI_KEY not set in .env")

    if args.file:
        files = [args.file]
    else:
        if not os.path.isdir(RESPONSE_DIR):
            sys.exit(f"ERROR: Directory '{RESPONSE_DIR}' not found")
        files = sorted(
            os.path.join(RESPONSE_DIR, fn)
            for fn in os.listdir(RESPONSE_DIR)
            if fn.startswith("companies_") and fn.endswith(".json")
        )

    if not files:
        print("No files found.")
        return

    print(f"Files to process: {len(files)}\n")

    if args.dry_run:
        total = 0
        for fp in files:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            print(f"=== {os.path.basename(fp)} ===")
            for c in data.get("companies", []):
                for l in c.get("leaders", []):
                    if not l.get("linkedin") and not is_junk_leader(l):
                        print(f"  [{c.get('name', '?')}] {l.get('name')} | {l.get('title')}")
                        total += 1
        print(f"\nTotal leaders to search: {total}")
        return

    enricher = LinkedInEnricher(key)
    total_found = 0
    for fp in files:
        print(f"\n=== {os.path.basename(fp)} ===")
        n = enrich_file(fp, enricher)
        print(f"  => {n} leader(s) now have LinkedIn")
        total_found += n

    print(f"\nDone. Total leaders with LinkedIn across all files: {total_found}")


if __name__ == "__main__":
    main()
