# debug_crawl.py — chạy: python debug_crawl.py <website_url>
import sys
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from src.browser_fetcher import fetch_html

LEADERSHIP_KEYWORDS = re.compile(
    r"\b(ceo|coo|cto|cfo|founder|co-founder|president|director|chief executive|"
    r"chief operating|chief technology|chief financial|managing director|"
    r"giám đốc|tổng giám đốc|chủ tịch)\b",
    re.IGNORECASE
)

ABOUT_LINK_KEYWORDS = re.compile(
    r"\b(about|team|leadership|management|people|who we are|về chúng tôi|đội ngũ)\b",
    re.IGNORECASE
)

LANG_PREFIXES = ["vi", "en", "jp", "ja", "zh", "ko", "fr", "de", "es"]

url = sys.argv[1] if len(sys.argv) > 1 else input("Website URL: ").strip()

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})


def fetch(u):
    html = fetch_html(u, timeout=10)

    class _R:
        status_code = 200
        text = html
        url = u

    return _R()


def scan_page(u, html, label=""):
    tag = f" [{label}]" if label else ""
    print(f"\n{'='*60}")
    print(f"FETCHING{tag}: {u}")
    print('='*60)
    soup = BeautifulSoup(html, "lxml")

    all_links = soup.find_all("a", href=True)
    print(f"\n--- ALL LINKS ({len(all_links)}) ---")
    for a in all_links:
        text = a.get_text(strip=True)[:40]
        href = a["href"][:60]
        match = "<<ABOUT>>" if ABOUT_LINK_KEYWORDS.search(text) or ABOUT_LINK_KEYWORDS.search(href) else ""
        print(f"  [{text}] -> {href} {match}")

    print(f"\n--- LEADERSHIP KEYWORD MATCHES ---")
    found = 0
    for el in soup.find_all(["h1","h2","h3","h4","p","span","div"]):
        text = el.get_text(strip=True)
        if not text or len(text) > 150:
            continue
        if LEADERSHIP_KEYWORDS.search(text):
            found += 1
            print(f"  TAG={el.name} | TEXT={text[:100]}")
            prev = el.find_previous_sibling(["h1","h2","h3","h4"])
            if prev:
                print(f"    ^ prev_sibling: {prev.get_text(strip=True)[:60]}")
            parent = el.parent
            if parent:
                pp = parent.find_previous_sibling()
                if pp:
                    print(f"    ^ parent_prev:  {pp.get_text(strip=True)[:60]}")
    if found == 0:
        print("  (none found)")

    about_url = None
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if ABOUT_LINK_KEYWORDS.search(text) or ABOUT_LINK_KEYWORDS.search(href):
            about_url = urljoin(u, href)
            break

    if about_url:
        print(f"\n--- FOLLOWING ABOUT LINK: {about_url} ---")
        try:
            r2 = fetch(about_url)
            soup2 = BeautifulSoup(r2.text, "lxml")
            found2 = 0
            for el in soup2.find_all(["h1","h2","h3","h4","p","span","div"]):
                text = el.get_text(strip=True)
                if not text or len(text) > 150:
                    continue
                if LEADERSHIP_KEYWORDS.search(text):
                    found2 += 1
                    print(f"  TAG={el.name} | TEXT={text[:100]}")
                    prev = el.find_previous_sibling(["h1","h2","h3","h4"])
                    if prev:
                        print(f"    ^ prev_sibling: {prev.get_text(strip=True)[:60]}")
                    parent = el.parent
                    if parent:
                        pp = parent.find_previous_sibling()
                        if pp:
                            print(f"    ^ parent_prev:  {pp.get_text(strip=True)[:60]}")
            if found2 == 0:
                print("  (no leadership keywords found on about page either)")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("\n--- NO ABOUT LINK FOUND ---")


def detect_lang_variants(base_url):
    """Detect existing language subpath variants, e.g. domain/vi, domain/en."""
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    found = []
    print(f"\n{'='*60}")
    print(f"CHECKING LANGUAGE VARIANTS for {root}")
    print('='*60)
    for lang in LANG_PREFIXES:
        candidate = f"{root}/{lang}"
        try:
            r = session.head(candidate, timeout=6, allow_redirects=True)
            # Accept 200 or redirect that doesn't loop back to root
            final_url = r.url.rstrip("/")
            root_clean = root.rstrip("/")
            if r.status_code == 200 and final_url != root_clean:
                print(f"  FOUND: {candidate} -> {r.url} [{r.status_code}]")
                found.append(r.url)
            else:
                print(f"  skip:  {candidate} [{r.status_code}] -> {r.url}")
        except Exception as e:
            print(f"  skip:  {candidate} [ERROR: {e}]")
    return found


# ── Main flow ────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"FETCHING: {url}")
print('='*60)

try:
    r = fetch(url)
    html = r.text
    print(f"Status: {r.status_code} | Size: {len(html)} chars")
except Exception as e:
    print(f"ERROR fetching: {e}")
    sys.exit(1)

# 1. Scan homepage
scan_page(url, html, label="homepage")

# 2. Detect and scan language variants
lang_urls = detect_lang_variants(url)
for lang_url in lang_urls:
    try:
        rl = fetch(lang_url)
        scan_page(lang_url, rl.text, label=lang_url.split("/")[-1])
    except Exception as e:
        print(f"\nERROR fetching {lang_url}: {e}")

print(f"\n{'='*60}\nDone.\n")
