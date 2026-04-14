# src/website_crawler.py
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from src.browser_fetcher import fetch_html

LEADERSHIP_KEYWORDS = re.compile(
    r"\b(ceo|coo|cto|cfo|founder|co-founder|president|director|chief executive|"
    r"chief operating|chief technology|chief financial|managing director|"
    r"giám đốc|tổng giám đốc|chủ tịch)\b",
    re.IGNORECASE
)

ABOUT_HIGH_PRIORITY = re.compile(
    r"\b(about-us|about us|ve-chung-toi|gioi-thieu|our story|who we are)\b"
    r"|về\s+(chúng\s*tôi|công\s*ty)|giới\s*thiệu",
    re.IGNORECASE
)

ABOUT_LOW_PRIORITY = re.compile(
    r"\b(about|team|leadership|management|people|đội\s*ngũ|ban\s*lãnh\s*đạo)\b",
    re.IGNORECASE
)

BLOG_PATTERNS = re.compile(
    r"\b(blog|news|insights|resources|press|tin-tuc|tin\s*tức|bai-viet|bài\s*viết|"
    r"updates|articles|media|newsroom|stories)\b",
    re.IGNORECASE
)

SOCIAL_PATTERNS = {
    "linkedin":  re.compile(r"linkedin\.com/(company|in)/", re.IGNORECASE),
    "facebook":  re.compile(r"facebook\.com/(?!sharer|share|dialog)", re.IGNORECASE),
    "instagram": re.compile(r"instagram\.com/", re.IGNORECASE),
    "twitter":   re.compile(r"(twitter\.com|x\.com)/(?!intent|share)", re.IGNORECASE),
    "youtube":   re.compile(r"youtube\.com/(channel|c|@|user)/", re.IGNORECASE),
    "whatsapp":  re.compile(r"(wa\.me|whatsapp\.com/send|api\.whatsapp\.com)", re.IGNORECASE),
    "wechat":    re.compile(r"(weixin\.qq\.com|wechat\.com)", re.IGNORECASE),
    "telegram":  re.compile(r"t\.me/", re.IGNORECASE),
    "line":      re.compile(r"line\.me/", re.IGNORECASE),
    "tiktok":    re.compile(r"tiktok\.com/@", re.IGNORECASE),
    "zalo":      re.compile(r"zalo\.me/", re.IGNORECASE),
}

PHONE_PATTERN = re.compile(
    r"(?:tel:|href=[\"']tel:)?\+?[\d][\d\s\-\(\)\.]{7,18}[\d]",
    re.IGNORECASE,
)


class WebsiteCrawler:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def crawl(self, website: str) -> dict:
        if not website:
            return {"leaders": [], "socials": {}}
        try:
            homepage_html = self._fetch_page(website)
            socials = self._extract_socials_from_html(homepage_html)
            leaders = self._extract_leaders_from_html(homepage_html)

            if not leaders:
                for about_url in self._find_about_links(homepage_html, website):
                    try:
                        about_html = self._fetch_page(about_url)
                        leaders = self._extract_leaders_from_html(about_html)
                        if leaders:
                            break
                    except Exception:
                        continue

            return {"leaders": leaders, "socials": socials}
        except Exception:
            return {"leaders": [], "socials": {}}

    def _extract_socials_from_html(self, html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        result = {}
        phones = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()

            if href.startswith("mailto:") and "email" not in result:
                result["email"] = href[len("mailto:"):]
                continue

            if href.startswith("tel:"):
                phone = href[4:].strip()
                if phone and phone not in phones:
                    phones.append(phone)
                continue

            for platform, pattern in SOCIAL_PATTERNS.items():
                if platform not in result and pattern.search(href):
                    result[platform] = href
                    break

        if phones:
            result["phones"] = phones

        return result

    def _find_about_links(self, html: str, base_url: str) -> list[str]:
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

    def _find_blog_links(self, html: str, base_url: str) -> list[str]:
        """Tìm link trang blog/news từ homepage HTML."""
        soup = BeautifulSoup(html, "lxml")
        seen, results = set(), []
        for tag in soup.find_all("a", href=True):
            combined = tag.get_text(strip=True) + " " + tag["href"]
            full_url = urljoin(base_url, tag["href"])
            if full_url not in seen and BLOG_PATTERNS.search(combined):
                seen.add(full_url)
                results.append(full_url)
        return results[:3]  # tối đa 3 trang blog/news

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
        prev = element.find_previous_sibling(["h1", "h2", "h3", "h4"])
        if prev:
            candidate = prev.get_text(strip=True)
            if self._looks_like_name(candidate):
                return candidate

        parent = element.parent
        if parent:
            parent_text = parent.get_text(strip=True)
            element_text = element.get_text(strip=True)
            if element_text and element_text in parent_text:
                before = parent_text[: parent_text.index(element_text)].strip()
                if self._looks_like_name(before):
                    return before

        # Strategy 3: iterate ALL previous siblings of parent (skip empty ones)
        if parent:
            for prev_p in parent.find_previous_siblings():
                candidate = prev_p.get_text(strip=True)
                if candidate and self._looks_like_name(candidate):
                    return candidate

        # Strategy 4: same but one level up (grandparent's previous siblings)
        grandparent = parent.parent if parent else None
        if grandparent:
            for prev_gp in grandparent.find_previous_siblings():
                candidate = prev_gp.get_text(strip=True)
                if candidate and self._looks_like_name(candidate):
                    return candidate

        return None

    def _looks_like_name(self, text: str) -> bool:
        if not text or len(text) > 60:
            return False
        words = text.split()
        if not (2 <= len(words) <= 5):
            return False
        return all(w[0].isupper() for w in words if w)

    def _fetch_page(self, url: str) -> str:
        return fetch_html(url, timeout=self.timeout)
