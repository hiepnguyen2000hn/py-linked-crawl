# main.py
import argparse
import os
import sys
import time
from dotenv import load_dotenv
from src.places_client import PlacesClient
from src.website_crawler import WebsiteCrawler
from src.output_writer import save_results

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crawl company info by location and industry using Google Places API"
    )
    parser.add_argument("--location", required=True, help='e.g. "Ho Chi Minh" or "Vietnam"')
    parser.add_argument("--industry", required=True, help='e.g. "ecommerce" or "mining"')
    parser.add_argument("--output-dir", default=".", help="Directory to save JSON output")
    parser.add_argument("--no-crawl", action="store_true", help="Skip website crawling, only fetch Places data")
    return parser.parse_args()


def main():
    args = parse_args()

    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_PLACES_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    print(f"Searching for '{args.industry}' companies in '{args.location}'...")
    client = PlacesClient(api_key=api_key)
    companies = client.search(location=args.location, industry=args.industry)
    print(f"Found {len(companies)} companies.")

    if not args.no_crawl:
        crawler = WebsiteCrawler()
        for i, company in enumerate(companies, 1):
            website = company.get("website")
            print(f"[{i}/{len(companies)}] Crawling {company['name']} ({website or 'no website'})...")
            company["leaders"] = crawler.crawl(website)
            time.sleep(0.5)  # polite delay
    else:
        for company in companies:
            company["leaders"] = []

    output_path = save_results(
        companies=companies,
        location=args.location,
        industry=args.industry,
        output_dir=args.output_dir
    )
    print(f"\nDone! Results saved to: {output_path}")


if __name__ == "__main__":
    main()
