"""
Đọc danh sách leads từ Google Sheet → crawl LinkedIn profile → DeepSeek extract
3 bài viết gần nhất → ghi kết quả vào tab nguồn (thêm/cập nhật 2 cột).

Cột "Bài Viết": tóm tắt 3 bài viết gần nhất (gạch đầu dòng •).
Cột "Đã Crawl": checkbox TRUE/FALSE — dùng để skip hàng đã crawl ở lần sau.

Cách dùng:
    python from_sheet_linkedin.py --spreadsheet-id SHEET_ID [OPTIONS]

Ví dụ:
    python from_sheet_linkedin.py --spreadsheet-id 1nmyj76On7Sc33N9OSf3l6u9gNJMPBWAWjQIS8P3iSt8 --gid 0 --limit 3
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

POST_KEY = "post"
POST_HEADER = "Bài Viết"
CRAWLED_KEY = "da_crawl"
CRAWLED_HEADER = "Đã Crawl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sheet linkedUrl → crawl LinkedIn → DeepSeek extract 3 posts → write back"
    )
    parser.add_argument(
        "--spreadsheet-id", required=True,
        help="Google Spreadsheet ID (từ URL: /spreadsheets/d/<ID>/)"
    )
    parser.add_argument(
        "--sheet-name", default=None,
        help="Tên tab nguồn (dùng thay --gid nếu biết tên tab)"
    )
    parser.add_argument(
        "--gid", type=int, default=None,
        help="GID số của tab nguồn — lấy từ URL #gid=<số> (ưu tiên hơn --sheet-name)"
    )
    parser.add_argument(
        "--col-linkedin", default="linkedUrl",
        help="Tên cột chứa LinkedIn URL (default: linkedUrl)"
    )
    parser.add_argument(
        "--col-name", default="fullName",
        help="Tên cột chứa tên người dùng (default: fullName)"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Số giây nghỉ giữa các request (default: 2.0)"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Chỉ xử lý N hàng đầu (0 = tất cả, default: 0)"
    )
    return parser.parse_args()


def _is_crawled(row: dict) -> bool:
    """Kiểm tra hàng đã được crawl chưa (cột Đã Crawl = TRUE)."""
    val = row.get(CRAWLED_HEADER, "")
    return val is True or str(val).upper() == "TRUE"


def _to_activity_url(linkedin_url: str) -> str:
    """Chuyển profile URL → trang recent-activity/all/ để lấy đầy đủ posts, comments, reposts.

    https://linkedin.com/in/username   →  https://linkedin.com/in/username/recent-activity/all/
    https://linkedin.com/in/username/recent-activity/...  →  (unchanged)
    """
    url = linkedin_url.rstrip('/')
    if '/recent-activity' not in url:
        url = url + '/recent-activity/all/'
    return url


def _load_cookies_from_env() -> list:
    """Đọc LinkedIn cookies từ env var LINKEDIN_COOKIES_JSON (set bởi server.py)."""
    raw = os.environ.get("LINKEDIN_COOKIES_JSON", "")
    if not raw:
        return []
    try:
        import json as _json
        cookies = _json.loads(raw)
        print(f"  [cookies] Loaded {len(cookies)} LinkedIn cookies from env")
        return cookies
    except Exception as e:
        print(f"  [cookies] Failed to parse LINKEDIN_COOKIES_JSON: {e}")
        return []


def _crawl_with_playwright_cookies(url: str, cookies: list) -> str:
    """Playwright với LinkedIn session cookies inject trực tiếp vào browser context."""
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # DEBUG: hiện cửa sổ để xem LinkedIn render gì
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            slow_mo=500,  # chậm 500ms mỗi action để dễ quan sát
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        # Inject cookies vào browser context (đây là cách đúng, không phải HTTP header)
        if cookies:
            _samesite_map = {"None": "None", "Lax": "Lax", "Strict": "Strict",
                             "no_restriction": "None", "lax": "Lax", "strict": "Strict",
                             "unspecified": "Lax"}
            pw_cookies = []
            for c in cookies:
                if not c.get("name") or not c.get("value"):
                    continue
                pw_cookies.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".linkedin.com"),
                    "path": c.get("path", "/"),
                    "secure": bool(c.get("secure", False)),
                    "httpOnly": bool(c.get("httpOnly", False)),
                    "sameSite": _samesite_map.get(str(c.get("sameSite", "Lax")), "Lax"),
                })
            ctx.add_cookies(pw_cookies)
            print(f"    Injected {len(pw_cookies)} cookies into Playwright context")

        page = ctx.new_page()
        page.add_init_script("""
            // Ẩn dấu hiệu automation
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            // Mock chrome runtime
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            // Mock plugins (headless thường trả về [])
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            // Override permission query
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) =>
                params.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : origQuery(params);
        """)
        try:
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            print(f"    [playwright] title={page.title()!r} url={page.url}")

            # ── Xử lý login / account chooser ────────────────────────────────
            _MAX_REDIRECTS = 3
            for _attempt in range(_MAX_REDIRECTS):
                current_url = page.url
                title = page.title()

                # Không phải linkedin.com → không xử lý
                if "linkedin.com" not in current_url:
                    break

                # Đã vào đúng trang (có "Activity" hoặc "LinkedIn" profile)
                if "/recent-activity" in current_url or (
                    "linkedin.com/in/" in current_url and "login" not in current_url
                ):
                    break

                # Trang login hoặc account chooser
                if "login" in current_url or "checkpoint" in current_url or "Choose an account" in title or "Login" in title:
                    print(f"    [playwright] Auth page detected (attempt {_attempt+1}) — trying to select account ...")

                    # Dùng JS tìm tất cả link/button trông như account item rồi click cái đầu
                    selector_clicked = page.evaluate("""
                        () => {
                            const candidates = [
                                // LinkedIn account picker (uas/login multi-account)
                                'a[href*="sessionPassword"]',
                                'a[href*="session_password"]',
                                'a[href*="switchAccount"]',
                                'a[href*="switch-account"]',
                                // Generic list items chứa email
                                ...Array.from(document.querySelectorAll('ul li')).filter(
                                    el => el.textContent.includes('@') || el.querySelector('a[href]')
                                ).map(el => { el.querySelector('a') && el.querySelector('a').click(); return 'ul li[email]'; }),
                            ];
                            for (const sel of candidates) {
                                if (typeof sel !== 'string') continue;
                                const el = document.querySelector(sel);
                                if (el) { el.click(); return sel; }
                            }
                            // Last resort: click thẳng phần tử đầu tiên trong form
                            const formLinks = document.querySelectorAll('form a, .account-picker a, ul.accounts li a');
                            if (formLinks.length > 0) { formLinks[0].click(); return 'form/picker link'; }
                            return null;
                        }
                    """)

                    if selector_clicked:
                        print(f"    [playwright] Clicked: {selector_clicked}")
                    else:
                        print(f"    [playwright] No clickable account found — dumping page links ...")
                        links = page.evaluate("""
                            () => Array.from(document.querySelectorAll('a[href]'))
                                      .slice(0, 15)
                                      .map(a => a.href + ' | ' + a.textContent.trim().slice(0, 60))
                        """)
                        for lnk in links:
                            print(f"      {lnk}")
                        break  # không click được → dừng, lấy nội dung hiện tại

                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    page.wait_for_timeout(2000)
                    print(f"    [playwright] After click: url={page.url}")
                else:
                    break  # không nhận ra trang → dừng

            # ── Đợi posts render (lazy-load, không dùng wait_for_selector vì gây redirect) ──
            page.wait_for_timeout(4000)  # posts load chậm → đợi đủ
            html = page.content()
            print(f"    [playwright] Final url={page.url} | content={len(html)} chars")
        except Exception as e:
            print(f"    [playwright] Error: {e}")
            html = ""
        finally:
            browser.close()

    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)


def _crawl_linkedin(url: str) -> str:
    """Crawl LinkedIn URL → markdown/text.

    Ưu tiên: Playwright với cookies (authenticated) > crawl4ai > Playwright ẩn danh
    Tự động chuyển profile URL → recent-activity/shares/ để lấy nội dung posts.
    """
    from src.crawl4ai_crawler import Crawl4AICrawler

    activity_url = _to_activity_url(url)
    if activity_url != url:
        print(f"  Activity URL: {activity_url}")

    cookies = _load_cookies_from_env()

    # Step 1: Playwright với session cookies (nếu có)
    if cookies:
        print(f"  Using authenticated Playwright ({len(cookies)} cookies) ...")
        try:
            content = _crawl_with_playwright_cookies(activity_url, cookies)
            if content and len(content) > 500:
                return content
            print(f"  [playwright+cookies] Too short ({len(content)} chars) — trying crawl4ai ...")
        except Exception as e:
            print(f"  [playwright+cookies] Error: {e}")

    # Step 2: crawl4ai (headless, không cookies)
    try:
        crawler = Crawl4AICrawler()
        markdown = crawler.crawl_to_markdown(activity_url)
        if markdown and len(markdown.strip()) > 500:
            return markdown
        print(f"  [crawl4ai] Too short ({len(markdown)} chars) — fallback ...")
    except Exception as e:
        print(f"  [crawl4ai] Error: {e}")

    # Step 3: Playwright ẩn danh (không cookies)
    print(f"  [fallback] Playwright anonymous ...")
    try:
        from src.browser_fetcher import fetch_html
        from bs4 import BeautifulSoup
        html = fetch_html(activity_url)
        if html:
            soup = BeautifulSoup(html, "lxml")
            text = soup.get_text(separator="\n")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            return "\n".join(lines)
    except Exception as e:
        print(f"  [browser_fetcher] Error: {e}")

    return ""


def main():
    args = parse_args()

    from src.sheets_writer import read_from_sheet, append_col_with_links, append_checkbox_col_to_sheet
    from src.linkedin_post_extractor import LinkedInPostExtractor

    # 1. Đọc sheet
    tab_desc = f"gid={args.gid}" if args.gid is not None else f"sheet='{args.sheet_name}'"
    print(f"Reading [{tab_desc}] from spreadsheet {args.spreadsheet_id} ...")
    rows = read_from_sheet(
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )
    print(f"Found {len(rows)} row(s).")

    if not rows:
        print("No data. Exiting.")
        return

    if args.limit > 0:
        rows = rows[: args.limit]
        print(f"Processing first {args.limit} row(s) only (--limit).")

    # 2. Build extractor
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)
    extractor = LinkedInPostExtractor(api_key=api_key)

    # 3. Crawl + extract từng người (skip hàng đã crawl)
    enriched = []
    skipped = 0
    for i, row in enumerate(rows, 1):
        name = row.get(args.col_name, "") or f"Row {i}"
        linkedin_url = (row.get(args.col_linkedin, "") or "").strip()

        print(f"\n[{i}/{len(rows)}] {name}")

        # Skip nếu đã crawl
        if _is_crawled(row):
            print(f"  Skipping — already crawled (Đã Crawl = TRUE)")
            enriched_row = dict(row)
            enriched_row[POST_KEY] = row.get(POST_HEADER, "")  # giữ giá trị cũ
            enriched_row[CRAWLED_KEY] = True
            enriched.append(enriched_row)
            skipped += 1
            continue

        if not linkedin_url:
            print(f"  Skipping — no URL in column '{args.col_linkedin}'")
            enriched_row = dict(row)
            enriched_row[POST_KEY] = ""
            enriched_row[CRAWLED_KEY] = False
            enriched.append(enriched_row)
            continue

        print(f"  Crawling {linkedin_url} ...")
        content = _crawl_linkedin(linkedin_url)

        enriched_row = dict(row)
        if not content:
            print(f"  [WARN] Empty content for {name}")
            enriched_row[POST_KEY] = ""
            enriched_row[CRAWLED_KEY] = False
        else:
            print(f"  Extracting posts ({len(content)} chars) ...")
            # Debug: in 300 chars đầu để thấy LinkedIn trả về gì
            preview = content[:300].replace('\n', ' ')
            print(f"  [preview] {preview}")
            posts = extractor.extract(content)
            val = posts.get(POST_KEY, "")
            if val:
                print(f"    post: {val[:200].replace(chr(10), ' ')}")
            else:
                print(f"    [WARN] No posts extracted — LinkedIn có thể đang block (trả về trang login?)")
            enriched_row[POST_KEY] = val
            enriched_row[CRAWLED_KEY] = True

        enriched.append(enriched_row)

        if i < len(rows):
            time.sleep(args.delay)

    newly_crawled = sum(1 for r in enriched if r.get(CRAWLED_KEY) is True) - skipped
    print(f"\nDone crawling: {newly_crawled} mới, {skipped} đã skip.")

    # 4. Ghi thêm/cập nhật 2 cột vào tab nguồn
    print(f"\nWriting cols to source tab [{tab_desc}] ...")
    url = append_col_with_links(
        enriched_rows=enriched,
        spreadsheet_id=args.spreadsheet_id,
        col_key=POST_KEY,
        col_header=POST_HEADER,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )
    append_checkbox_col_to_sheet(
        enriched_rows=enriched,
        spreadsheet_id=args.spreadsheet_id,
        col_key=CRAWLED_KEY,
        col_header=CRAWLED_HEADER,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )

    print(f"\nDone! View results at:\n  {url}")


if __name__ == "__main__":
    main()
