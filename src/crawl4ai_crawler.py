# src/crawl4ai_crawler.py
import asyncio
import json
import os
import sys
from typing import Optional

# Windows: force UTF-8 stdout/stderr to avoid charmap codec errors
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class Crawl4AICrawler:
    """Crawl a URL and return its content as clean markdown using crawl4ai."""

    def crawl_to_markdown(self, url: str, cookies: Optional[list] = None) -> str:
        # Nếu không truyền cookies, thử đọc từ env var (set bởi server.py khi gọi qua API)
        if cookies is None:
            raw = os.environ.get("LINKEDIN_COOKIES_JSON", "")
            if raw:
                try:
                    cookies = json.loads(raw)
                except Exception:
                    cookies = None
        try:
            return asyncio.run(self._crawl(url, cookies=cookies))
        except Exception as e:
            msg = str(e).encode("utf-8", errors="replace").decode("utf-8")
            print(f"  [crawl4ai] Error crawling {url}: {msg}")
            return ""

    async def _crawl(self, url: str, cookies: Optional[list] = None) -> str:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
        from crawl4ai.content_filter_strategy import PruningContentFilter

        # Build Cookie header string từ cookie list
        extra_headers = {}
        if cookies:
            cookie_str = "; ".join(
                f"{c['name']}={c['value']}"
                for c in cookies
                if c.get('name') and c.get('value')
            )
            if cookie_str:
                extra_headers["Cookie"] = cookie_str

        run_config = CrawlerRunConfig(
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(),
                options={"ignore_links": False, "ignore_images": False},
            ),
        )

        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            headers=extra_headers if extra_headers else {},
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            if not result.success:
                return ""
            md = result.markdown
            return md.fit_markdown or md.raw_markdown or ""