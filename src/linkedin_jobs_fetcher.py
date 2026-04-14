"""
Fetch danh sách jobs từ LinkedIn company page.
Flow: resolve URL redirect → Playwright fetch /jobs → BeautifulSoup → DeepSeek extract.
"""
import json
import os
import re

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = "You are a job listing extractor. Return ONLY valid JSON."

_USER_TEMPLATE = """\
Extract all job titles currently listed on this LinkedIn jobs page.
Return ONLY JSON: {{"jobs": ["Job Title 1", "Job Title 2", ...]}}
If no jobs found, return {{"jobs": []}}
Do NOT translate job titles — keep original language.

Content:
{text}"""


def _resolve_linkedin_url(url: str) -> str:
    """Follow redirects để lấy URL canonical (ID số → company slug).
    Ví dụ: /company/18096007 → /company/emurgo-io/
    """
    try:
        resp = requests.head(
            url,
            allow_redirects=True,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"},
        )
        return resp.url
    except Exception as e:
        print(f"    [resolve] Error: {e}")
        return url


def _build_jobs_url(company_url: str) -> str:
    """Append /jobs vào flagship_url."""
    base = company_url.rstrip("/")
    if base.endswith("/jobs"):
        return base
    return base + "/jobs"


def _fetch_with_playwright(url: str) -> str:
    """Dùng Playwright headless để lấy HTML jobs page (JS-rendered)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Đợi job cards load — thử nhiều selector khác nhau
            _JOB_SELECTORS = (
                ".job-search-card, "                      # company /jobs tab
                ".base-search-card__title, "              # search results
                ".jobs-search__results-list li, "         # jobs list
                "[class*='job-search-card__title'], "
                "[class*='base-card__full-link'], "
                "h3.base-search-card__title"
            )
            try:
                page.wait_for_selector(_JOB_SELECTORS, timeout=12000)
            except Exception:
                pass
            # Scroll xuống để lazy-load thêm job cards
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(2000)
            html = page.content()
        finally:
            browser.close()
    return html


def _extract_job_titles_from_html(html: str) -> list[str]:
    """Trực tiếp parse HTML tìm job titles — fallback nhanh trước khi dùng DeepSeek."""
    soup = BeautifulSoup(html, "lxml")
    titles = []
    # Selector cho LinkedIn company /jobs tab và jobs search
    for sel in [
        "h3.base-search-card__title",
        ".job-search-card__title",
        "a.job-search-card__title",
        "[class*='job-search-card__title']",
        "h3[class*='base-search-card__title']",
    ]:
        for el in soup.select(sel):
            t = el.get_text(strip=True)
            if t and t not in titles:
                titles.append(t)
    return titles


def _html_to_markdown(html: str, base_url: str = "") -> str:
    """crawl4ai DefaultMarkdownGenerator — convert HTML → clean markdown.
    Không fetch lại, chỉ dùng markdown generator của crawl4ai.
    Context ngắn hơn HTML thô, DeepSeek đọc dễ hơn.
    """
    try:
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
        from crawl4ai.content_filter_strategy import PruningContentFilter

        generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter()
        )
        result = generator.generate_markdown(
            cleaned_html=html,
            base_url=base_url,
            html2text_options={},
        )
        md = getattr(result, "fit_markdown", None) or getattr(result, "raw_markdown", None) or ""
        if md and md.strip():
            return md
    except Exception as e:
        print(f"    [crawl4ai md] Error: {e}")

    # Fallback: BeautifulSoup plain text
    soup = BeautifulSoup(html, "lxml")
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
    return "\n".join(lines)


def fetch_company_jobs(company_url: str, api_key: str | None = None) -> list[str]:
    """Lấy job titles từ trang /jobs/ của công ty.
    1. Append /jobs vào flagship_url
    2. Playwright fetch /jobs
    3. DeepSeek extract titles
    """
    jobs_url = _build_jobs_url(company_url)
    print(f"    Jobs URL: {jobs_url}")

    html = _fetch_with_playwright(jobs_url)
    if not html:
        return []

    # Thử parse trực tiếp HTML trước — nhanh, zero token
    direct = _extract_job_titles_from_html(html)
    if direct:
        print(f"    [direct parse] Found {len(direct)} job(s)")
        return direct

    # Fallback: crawl4ai → markdown → DeepSeek
    text = _html_to_markdown(html, base_url=jobs_url)
    if not text:
        return []

    # Chỉ lấy 8000 chars — job listing thường ở đầu trang
    truncated = text[:8000]

    key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY not set.")

    client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _USER_TEMPLATE.format(text=truncated)},
            ],
            temperature=0,
            max_tokens=512,
        )
        raw = resp.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            jobs = data.get("jobs", [])
            return [j.strip() for j in jobs if isinstance(j, str) and j.strip()]
    except Exception as e:
        print(f"    [DeepSeek] Error: {e}")

    return []


def format_jobs(jobs: list[str]) -> str:
    if not jobs:
        return ""
    return "\n".join(f"• {j}" for j in jobs)
