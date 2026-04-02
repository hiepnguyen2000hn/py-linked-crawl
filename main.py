# main.py
import argparse
import os
import sys
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
    parser.add_argument("--extract", action="store_true",
                        help="Use IE model to extract leaders; only keep pages with results")
    parser.add_argument("--extractor", choices=["qwen", "deepseek"], default="qwen",
                        help="IE extractor to use with --extract: qwen (local) or deepseek (API, requires DEEPSEEK_API_KEY)")
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


def run_json_mode(companies: list[dict], args):
    """Original flow: crawl leaders & socials, save as JSON."""
    if not args.no_crawl:
        crawler = WebsiteCrawler()
        for i, company in enumerate(companies, 1):
            website = company.get("website")
            print(f"[{i}/{len(companies)}] Crawling {company['name']} ({website or 'no website'})...")
            crawl_result = crawler.crawl(website)
            company["leaders"] = crawl_result["leaders"]
            company["socials"] = crawl_result["socials"]
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
    return {"markdown": markdown, "leaders": all_leaders}


def run_markdown_mode(companies: list[dict], args):
    """SerpAPI flow: crawl each company website (homepage + about/leadership pages) → one combined markdown."""
    crawler = Crawl4AICrawler()
    helper = WebsiteCrawler()
    extractor = build_extractor(args)

    for i, company in enumerate(companies, 1):
        website = company.get("website")
        name = company.get("name", "Unknown")

        if not website:
            print(f"[{i}/{len(companies)}] Skipping {name} (no website)")
            company["markdown_content"] = ""
            company["leaders"] = []
            continue

        print(f"[{i}/{len(companies)}] Crawling {name} ({website})...")
        result = _crawl_company_pages(website, crawler, helper, extractor)
        company["markdown_content"] = result["markdown"]
        company["leaders"] = result["leaders"]
        if extractor and result["leaders"]:
            print(f"    Extracted {len(result['leaders'])} leader(s): {[l['name'] for l in result['leaders']]}")

    return save_markdown_report(
        companies=companies,
        location=args.location,
        industry=args.industry,
        output_dir=args.output_dir,
    )


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

    # 3. Crawl từng trang với crawl4ai, lưu file markdown riêng
    crawler = Crawl4AICrawler()
    extractor = build_extractor(args)
    saved_files = []

    for i, url in enumerate(urls_to_crawl, 1):
        path = urlparse(url).path.strip("/").replace("/", "-") or "home"
        slug = path[:50]
        filename = f"{domain}_{slug}_{timestamp}.md"
        filepath = os.path.join(args.output_dir, filename)

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
    companies = client.search(location=args.location, industry=args.industry, pages=args.pages)
    print(f"Found {len(companies)} companies.")

    if args.format == "markdown":
        output_path = run_markdown_mode(companies, args)
    else:
        output_path = run_json_mode(companies, args)

    print(f"\nDone! Results saved to: {output_path}")


if __name__ == "__main__":
    main()