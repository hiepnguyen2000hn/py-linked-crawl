"""
Helper script — chạy Crawl4AICrawler trong process riêng, tránh conflict event loop với FastAPI.
Dùng chung src/crawl4ai_crawler.py với from_sheet_full_enrich.py
Usage: python -u _crawl_one.py <url>
Output: JSON dòng cuối stdout
"""
import asyncio
import sys
import json
import os

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from dotenv import load_dotenv
load_dotenv()

from src.crawl4ai_crawler import Crawl4AICrawler


def main(url: str):
    crawler = Crawl4AICrawler()
    markdown = crawler.crawl_to_markdown(url)
    if markdown:
        print(json.dumps({"ok": True, "url": url, "markdown": markdown}))
    else:
        print(json.dumps({"ok": False, "url": url, "markdown": "", "error": "Crawl failed or empty"}))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "url": "", "markdown": "", "error": "No URL provided"}))
        sys.exit(1)
    main(sys.argv[1])
