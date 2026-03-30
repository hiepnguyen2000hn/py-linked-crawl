# src/website_crawler.py
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tenacity import retry, stop_after_attempt, wait_exponential

LEADERSHIP_KEYWORDS = re.compile(
    r"\b(ceo|coo|cto|cfo|founder|co-founder|president|director|chief executive|"
    r"chief operating|chief technology|chief financial|managing director|"
    r"gi\u00e1m \u0111\u1ed1c|t\u1ed5ng gi\u00e1m \u0111\u1ed1c|ch\u1ee7 t\u1ecbch)\b",
    re.IGNORECASE
)

# High priority: actual "about us" pages
ABOUT_HIGH_PRIORITY = re.compile(
    r"\b(about-us|about us|ve-chung-toi|gioi-thieu|our story|who we are)\b"
    r"|v\u1ec1\s+(ch\u00fang\s*t\u00f4i|c\u00f4ng\s*ty)|gi\u1edbi\s*thi\u1ec7u",
    re.IGNORECASE
)

# Low priority: team/leadership section pages
ABOUT_LOW_PRIORITY = re.compile(
    r"\b(about|team|leadership|management|people|\u0111\u1ed9i\s*ng\u0169|ban\s*l\u00e3nh\s*\u0111\u1ea1o)\b",
    re.IGNORECASE
)


class WebsiteCrawler:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; CompanyCrawler/1.0)"
        })

    def crawl(self, website: str) -> list[dict]:
        if not website:
            return []
        try:
            homepage_html = self._fetch_page(website)
            leaders = self._extract_leaders_from_html(homepage_html)
            if leaders:
                return leaders

            for about_url in self._find_about_links(homepage_html, website):
                try:
                    about_html = self._fetch_page(about_url)
                    leaders = self._extract_leaders_from_html(about_html)
                    if leaders:
                        return leaders
                except Exception:
                    continue

            return leaders
        except Exception:
            return []

    def _find_about_links(self, html: str, base_url: str) -> list[str]:
        """Return about-like URLs: high-priority first, then low-priority."""
        soup = BeautifulSoup(html, "lxml")
        high, low = [], []
        seen = set()
        for tag in soup.find_all("a", href=True):
            text = tag.get_text(strip=True)
            href = tag["href"]
            combined = text + " " + href
            full_url = urljoin(base_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            if ABOUT_HIGH_PRIORITY.search(combined):
                high.append(full_url)
            elif ABOUT_LOW_PRIORITY.search(combined):
                low.append(full_url)
        return high + low

    def _extract_leaders_from_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        leaders = []
        seen_names = set()

        for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "span", "div"]):
            text = element.get_text(strip=True)
            if not text or len(text) > 100:
                continue
            if LEADERSHIP_KEYWORDS.search(text):
                name = self._find_nearby_name(element)
                if name and name not in seen_names:
                    seen_names.add(name)
                    leaders.append({"name": name, "title": text[:100]})

        return leaders

    def _find_nearby_name(self, element) -> str | None:
        # Strategy 1: previous sibling heading
        prev = element.find_previous_sibling(["h1", "h2", "h3", "h4"])
        if prev:
            candidate = prev.get_text(strip=True)
            if self._looks_like_name(candidate):
                return candidate

        # Strategy 2: name embedded in parent text before this element's text
        # e.g. parent div = "MS. HA DOANTổng Giám Đốc..." and element = "Tổng Giám Đốc..."
        parent = element.parent
        if parent:
            parent_text = parent.get_text(strip=True)
            element_text = element.get_text(strip=True)
            if element_text and element_text in parent_text:
                before = parent_text[: parent_text.index(element_text)].strip()
                if self._looks_like_name(before):
                    return before

        # Strategy 3: parent's previous sibling
        if parent:
            prev_p = parent.find_previous_sibling()
            if prev_p:
                candidate = prev_p.get_text(strip=True)
                if self._looks_like_name(candidate):
                    return candidate

        return None

    def _looks_like_name(self, text: str) -> bool:
        if not text or len(text) > 60:
            return False
        words = text.split()
        if not (2 <= len(words) <= 5):
            return False
        return all(w[0].isupper() for w in words if w)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def _fetch_page(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text
