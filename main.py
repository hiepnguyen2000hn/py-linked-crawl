# main.py
import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
import time
from urllib.parse import urlparse
from dotenv import load_dotenv
from src.places_client import PlacesClient
from src.serp_client import SerpClient
from src.website_crawler import WebsiteCrawler
from src.crawl4ai_crawler import Crawl4AICrawler
from src.output_writer import save_results, save_markdown_report
from src.ie_extractor import IEExtractor
from src.deepseek_extractor import DeepSeekExtractor
from src.linkedin_enricher import LinkedInEnricher

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crawl company info by location and industry"
    )
    parser.add_argument("--url", help="Crawl a single URL directly to markdown (skips SerpAPI)")
    parser.add_argument("--location", help='e.g. "Ho Chi Minh" or "Vietnam"')
    parser.add_argument("--industry", help='e.g. "ecommerce" or "mining"')
    parser.add_argument("--source", choices=["google", "serpapi"], default="google",
                        help="Data source: google (Places API) or serpapi (default: google)")
    parser.add_argument("--format", choices=["json", "markdown"], default="json",
                        help="Output format: json (default) or markdown (uses crawl4ai)")
    parser.add_argument("--output-dir", default=".", help="Directory to save output")
    parser.add_argument("--no-crawl", action="store_true",
                        help="Skip website crawling, only fetch company list")
    parser.add_argument("--pages", type=int, default=1,
                        help="Number of SerpAPI pages to fetch (~20 results each, default: 1)")
    parser.add_argument("--start-page", type=int, default=1,
                        help="Which page to start from, 1-indexed (default: 1). e.g. --start-page 2 fetches results 21-40")
    parser.add_argument("--extract", action="store_true",
                        help="Use IE model to extract leaders; only keep pages with results")
    parser.add_argument("--extractor", choices=["qwen", "deepseek"], default="qwen",
                        help="IE extractor to use with --extract: qwen (local) or deepseek (API, requires DEEPSEEK_API_KEY)")
    parser.add_argument(
        "--enrich-linkedin",
        action="store_true",
        help="After extraction, search Google (SerpAPI) for personal LinkedIn URLs of leaders missing them",
    )
    parser.add_argument("--sheets", action="store_true",
                        help="Save results to Google Sheets after crawling")
    parser.add_argument("--sheet-name", default="Sheet1",
                        help="Tab name in Google Sheet (default: Sheet1)")
    args = parser.parse_args()
    if not args.url and (not args.location or not args.industry):
        parser.error("--location and --industry are required unless --url is specified")
    return args


def build_client(source: str):
    if source == "serpapi":
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            print("ERROR: SERPAPI_KEY not set. Add it to your .env file.")
            sys.exit(1)
        return SerpClient(api_key=api_key)

    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_PLACES_API_KEY not set. Add it to your .env file.")
        sys.exit(1)
    return PlacesClient(api_key=api_key)


def build_extractor(args):
    """Build extractor based on --extractor flag. Returns None if --extract not set."""
    if not args.extract:
        return None
    if args.extractor == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("ERROR: DEEPSEEK_API_KEY not set. Add it to your .env file.")
            sys.exit(1)
        return DeepSeekExtractor(api_key=api_key)
    return IEExtractor()


def build_enricher(args) -> "LinkedInEnricher | None":
    """Build LinkedIn enricher if --enrich-linkedin flag is set."""
    if not getattr(args, "enrich_linkedin", False):
        return None
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        print("ERROR: SERPAPI_KEY not set. Add it to your .env file.")
        sys.exit(1)
    return LinkedInEnricher(api_key=api_key)


def run_json_mode(companies: list[dict], args, enricher=None):
    """Original flow: crawl leaders & socials, save as JSON."""
    if not args.no_crawl:
        crawler = WebsiteCrawler()
        for i, company in enumerate(companies, 1):
            website = company.get("website")
            print(f"[{i}/{len(companies)}] Crawling {company['name']} ({website or 'no website'})...")
            crawl_result = crawler.crawl(website)
            company["leaders"] = crawl_result["leaders"]
            company["socials"] = crawl_result["socials"]
            if enricher and company["leaders"]:
                enricher.enrich(company["leaders"], company.get("name", ""))
            time.sleep(0.5)
    else:
        for company in companies:
            company["leaders"] = []
            company["socials"] = {}

    return save_results(
        companies=companies,
        location=args.location,
        industry=args.industry,
        output_dir=args.output_dir,
    )


def _crawl_company_pages(
    website: str,
    crawler: Crawl4AICrawler,
    helper: WebsiteCrawler,
    extractor: "IEExtractor | None" = None,
) -> dict:
    """Crawl homepage + about/team pages.
    Returns {"markdown": str, "leaders": list[dict]}
    If extractor is set, only keeps pages where leaders were found.
    """
    from src.browser_fetcher import fetch_html
    try:
        html = fetch_html(website, timeout=10)
        about_links = helper._find_about_links(html, website)
    except Exception:
        about_links = []

    seen = set()
    urls = []
    for u in [website] + about_links:
        if u not in seen:
            seen.add(u)
            urls.append(u)

    if len(urls) > 1:
        print(f"    Discovered {len(urls)} pages: homepage + {len(about_links)} about/team links")

    # Extract socials from homepage HTML
    socials = helper._extract_socials_from_html(html) if html else {}

    parts = []
    all_leaders = []
    seen_names = set()

    for url in urls:
        content = crawler.crawl_to_markdown(url)
        if not content:
            continue

        if extractor:
            leaders = extractor.extract(content)
            if not leaders:
                print(f"    [IE] No leaders found on {url} — skipped")
                continue
            for l in leaders:
                if l["name"] not in seen_names:
                    seen_names.add(l["name"])
                    all_leaders.append(l)
            print(f"    [IE] {url} → {[l['name'] + ' (' + l['title'] + ')' for l in leaders]}")

        parts.append(f"### {url}\n\n{content}")

    markdown = "\n\n---\n\n".join(parts)
    return {"markdown": markdown, "leaders": all_leaders, "socials": socials}


def run_markdown_mode(companies: list[dict], args, enricher=None):
    """SerpAPI flow: crawl each company website → one markdown file per company inside a timestamped folder."""
    import datetime
    crawler = Crawl4AICrawler()
    helper = WebsiteCrawler()
    extractor = build_extractor(args)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_location = args.location.replace(" ", "_").lower()
    safe_industry = args.industry.replace(" ", "_").lower()
    folder_name = f"companies_{safe_location}_{safe_industry}_{timestamp}"
    folder_path = os.path.join(args.output_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    saved_files = []

    for i, company in enumerate(companies, 1):
        website = company.get("website")
        name = company.get("name", "Unknown")
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip().replace(" ", "_")[:60]

        if not website:
            print(f"[{i}/{len(companies)}] Skipping {name} (no website)")
            continue

        print(f"[{i}/{len(companies)}] Crawling {name} ({website})...")
        result = _crawl_company_pages(website, crawler, helper, extractor)
        company["socials"] = result.get("socials", {})

        if extractor and not result["leaders"]:
            print(f"    No leaders found — skipped")
            continue

        if extractor and result["leaders"]:
            print(f"    Extracted {len(result['leaders'])} leader(s): {[l['name'] for l in result['leaders']]}")
        if enricher and result["leaders"]:
            enricher.enrich(result["leaders"], company.get("name", ""))
        company["leaders"] = result["leaders"]
        if result.get("socials"):
            print(f"    Socials: {list(result['socials'].keys())}")

        lines = [f"# {name}", ""]
        if website:
            lines += [f"**Website:** [{website}]({website})  ", ""]
        if company.get("address"):
            lines += [f"**Address:** {company['address']}  ", ""]
        if company.get("phone"):
            lines += [f"**Phone:** {company['phone']}  ", ""]
        if company.get("rating") is not None:
            rating_str = f"**Rating:** {company['rating']}"
            if company.get("reviews"):
                rating_str += f" ({company['reviews']} reviews)"
            lines += [rating_str + "  ", ""]
        if company.get("description"):
            lines += [f"**Description:** {company['description']}  ", ""]

        if company["leaders"]:
            lines += ["## Leadership", ""]
            for l in company["leaders"]:
                lines.append(f"- **{l['name']}** — {l['title']}")
            lines.append("")

        if result["markdown"]:
            lines += ["## Website Content", "", result["markdown"].strip(), ""]

        filepath = os.path.join(folder_path, f"{safe_name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        saved_files.append(filepath)

    print(f"\nSaved {len(saved_files)} file(s) to folder: {folder_path}")
    return folder_path


def run_single_url_mode(args):
    """Crawl một URL, tự động discover tất cả trang about/team/leadership rồi lưu markdown riêng."""
    from src.browser_fetcher import fetch_html

    base_url = args.url
    domain = urlparse(base_url).netloc or "crawl"
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Fetch homepage, discover about/team/leadership links
    print(f"Fetching homepage: {base_url}...")
    try:
        html = fetch_html(base_url, timeout=10)
    except Exception as e:
        print(f"ERROR fetching homepage: {e}")
        return []

    helper = WebsiteCrawler()
    about_links = helper._find_about_links(html, base_url)

    # 2. Unique list: homepage trước, sau đó about links
    seen = set()
    urls_to_crawl = []
    for u in [base_url] + about_links:
        if u not in seen:
            seen.add(u)
            urls_to_crawl.append(u)

    print(f"Found {len(urls_to_crawl)} pages: homepage + {len(about_links)} about/team/leadership pages")

    # 3. Crawl từng trang với crawl4ai, lưu file markdown riêng trong subfolder
    crawler = Crawl4AICrawler()
    extractor = build_extractor(args)
    saved_files = []

    folder_name = f"{domain}_{timestamp}"
    folder_path = os.path.join(args.output_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    for i, url in enumerate(urls_to_crawl, 1):
        path = urlparse(url).path.strip("/").replace("/", "-") or "home"
        slug = path[:50]
        filename = f"{slug}.md"
        filepath = os.path.join(folder_path, filename)

        print(f"[{i}/{len(urls_to_crawl)}] Crawling {url}...")
        content = crawler.crawl_to_markdown(url)
        if not content:
            print(f"  -> Skipped (empty content)")
            continue

        if extractor:
            leaders = extractor.extract(content)
            if not leaders:
                print(f"  -> Skipped (no leaders found by IE model)")
                continue
            print(f"  -> Leaders: {[l['name'] + ' (' + l['title'] + ')' for l in leaders]}")
            leaders_md = "\n".join(f"- **{l['name']}** — {l['title']}" for l in leaders)
            content = f"## Extracted Leaders\n\n{leaders_md}\n\n---\n\n{content}"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {url}\n\n")
            f.write(content)
        saved_files.append(filepath)
        print(f"  -> Saved: {filename}")

    print(f"\nSaved {len(saved_files)} file(s) to folder: {folder_path}")
    return saved_files


def main():
    args = parse_args()

    if args.url:
        saved_files = run_single_url_mode(args)
        print(f"\nDone! {len(saved_files)} file(s) saved:")
        for f in saved_files:
            print(f"  {f}")
        return

    client = build_client(args.source)

    print(f"[{args.source}] Searching for '{args.industry}' companies in '{args.location}' (pages={args.pages}, ~{args.pages * 20} max results)...")
    companies = client.search(location=args.location, industry=args.industry, pages=args.pages, start_page=args.start_page)
    print(f"Found {len(companies)} companies.")

    enricher = build_enricher(args)

    if args.format == "markdown":
        run_markdown_mode(companies, args, enricher=enricher)
    else:
        output_path = run_json_mode(companies, args, enricher=enricher)
        print(f"\nDone! Results saved to: {output_path}")

    if args.sheets:
        from src.sheets_writer import save_to_sheet
        print("\nSaving to Google Sheets...")
        save_to_sheet(companies, sheet_name=args.sheet_name)


if __name__ == "__main__":
    main()