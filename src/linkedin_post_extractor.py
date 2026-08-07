import json
import os
import re
from openai import OpenAI


def clean_linkedin_content(text: str) -> str:
    """Strip LinkedIn noise: signup URLs, tracking links — giữ nguyên nội dung post."""
    text = re.sub(r'\[\.\.\.more\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\)]*(?:signup|trk=)[^\)]*\)', r'\1', text)
    text = re.sub(r'https?://\S*(?:signup|trk=)\S*', '', text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return '\n'.join(lines)


def _parse_urn_from_componentkey(componentkey: str) -> tuple[str, str]:
    """Parse componentkey attribute → (urn_string, post_url).

    LinkedIn encode post ID trong componentkey attribute của <p> text block, ví dụ:
      contentUrnUgcPostUrn=...userGeneratedContentId=7474857215565430784
      contentUrnShareUrn=...shareId=7123456789
      contentUrnActivityUrn / activityId=7123456789
    """
    # UGC post (phổ biến nhất cho bài viết thường)
    m = re.search(r"userGeneratedContentId=(\d+)", componentkey)
    if m:
        post_id = m.group(1)
        urn = f"urn:li:ugcPost:{post_id}"
        return urn, f"https://www.linkedin.com/feed/update/{urn}/"

    # Share URN
    m = re.search(r"shareId=(\d+)", componentkey)
    if m:
        post_id = m.group(1)
        urn = f"urn:li:share:{post_id}"
        return urn, f"https://www.linkedin.com/feed/update/{urn}/"

    # Activity URN fallback
    m = re.search(r"activityId=(\d+)", componentkey)
    if m:
        post_id = m.group(1)
        urn = f"urn:li:activity:{post_id}"
        return urn, f"https://www.linkedin.com/feed/update/{urn}/"

    return "", ""


def extract_posts_with_metadata(html: str) -> list[dict]:
    """Parse LinkedIn HTML → list of post dicts với activityId, URL, type, user_text.

    Strategy 1: carousel li items từ profile page widget.
    Cấu trúc: section[data-testid="carousel"] > ul > li[data-testid="carousel-child-container"]
    Mỗi li = đúng 1 post, không bị duplicate.

    Type:
        1 = original post (user tự viết)
        2 = pure repost (không có thêm text)
        3 = repost with thoughts (repost + user thêm text)
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    posts = []
    seen_urns: set[str] = set()

    # ── Strategy 1: carousel li items (profile page widget) ──────────────────
    # Mỗi li[data-testid="carousel-child-container"] = 1 post duy nhất
    carousel_items = soup.find_all("li", attrs={"data-testid": "carousel-child-container"})
    print(f"    [meta] carousel-child-container items: {len(carousel_items)}")

    for li in carousel_items:
        # Tìm link /feed/update/ → dùng làm linkPost URL
        feed_link = li.find("a", href=re.compile(r"/feed/update/urn:li:"))
        if not feed_link:
            continue

        href = feed_link.get("href", "")
        if href.startswith("/"):
            href = "https://www.linkedin.com" + href
        post_url = href.split("?")[0].rstrip("/") + "/"

        # Phân loại bài viết dựa trên 3 tín hiệu từ HTML:
        #
        # "reposted this" banner → type 2 (pure repost, không có thoughts)
        # feed-original-share-description_* → type 3 (user thêm thoughts + reshared content bên dưới)
        # Còn lại → type 1 (bài gốc của user, dù encode bằng feed-commentary hay translatable-commentary)
        #
        # Lưu ý: feed-commentary_* xuất hiện cả trong type 1 (user's text) VÀ type 2 (reshared text)
        # → KHÔNG thể dùng riêng để phân biệt type 1 vs type 2

        feed_elem = li.find(attrs={"componentkey": re.compile(r"^feed-commentary_")})
        trans_elem = li.find(attrs={"componentkey": re.compile(r"^translatable-commentary")})
        orig_share_elem = li.find(attrs={"componentkey": re.compile(r"^feed-original-share-description_")})
        repost_banner = li.find(string=re.compile(r"reposted\s+this", re.IGNORECASE))

        if orig_share_elem:
            post_type = 3   # user viết thoughts + reshared content hiển thị bên dưới
        elif bool(repost_banner):
            post_type = 2   # pure repost, không có thoughts riêng
        else:
            post_type = 1   # bài gốc của user

        # activityId từ <a href="/feed/update/urn:li:..."> — đây là activity chính của post
        m = re.search(r"(urn:li:[^/?#]+)", href)
        activity_urn = m.group(1) if m else ""

        # Với type 2 (pure repost): thử lấy ugcPost/share URN từ translatable-commentary componentkey
        # để dùng làm activityId chính xác hơn
        if post_type == 2 and trans_elem:
            trans_ck = trans_elem.get("componentkey", "")
            parsed_urn, _ = _parse_urn_from_componentkey(trans_ck)
            if parsed_urn:
                activity_urn = parsed_urn

        if not activity_urn or activity_urn in seen_urns:
            continue
        seen_urns.add(activity_urn)

        # Lấy text content:
        # type 1: user_text từ feed_elem (feed-commentary) hoặc trans_elem (translatable-commentary)
        # type 2: user_text từ feed_elem (là text của bài được repost) hoặc trans_elem
        # type 3: user_text từ feed_elem (user's own thoughts, KHÔNG phải reshared content)
        if post_type == 3:
            text_elem = feed_elem  # thoughts của user
        else:
            text_elem = feed_elem or trans_elem  # text chính của post

        user_text = ""
        if text_elem:
            for btn in text_elem.find_all("button"):
                btn.decompose()
            user_text = re.sub(r'\s*…\s*more\s*$', '', text_elem.get_text(separator=" ", strip=True)).strip()

        posts.append({
            "activityId": activity_urn,
            "url": post_url,
            "type": post_type,
            "user_text": user_text[:500],
            "has_content": bool(user_text),
        })

    if posts:
        return posts

    # ── Strategy 2: data-urn attribute (cũ, một số version LinkedIn) ─────────
    all_urn_elems = soup.find_all(attrs={"data-urn": re.compile(r"urn:li:activity:")})
    print(f"    [meta] data-urn elements: {len(all_urn_elems)}")
    for elem in all_urn_elems:
        urn = elem.get("data-urn", "")
        if urn in seen_urns:
            continue
        seen_urns.add(urn)
        url = f"https://www.linkedin.com/feed/update/{urn}/"
        for noise in elem.find_all(class_=re.compile(r"social-details|social-counts|reactions-count")):
            noise.decompose()
        reshare_elems = elem.find_all(class_=re.compile(r"mini-update|reshared|shared-update|feed-shared-mini"))
        nested = [c for c in elem.find_all(attrs={"data-urn": re.compile(r"urn:li:")}) if c != elem]
        has_reshare = len(reshare_elems) > 0 or len(nested) > 0
        text_elem = elem.find(class_=re.compile(r"commentary|description|inline-show-more-text|update-components-text"))
        user_text = ""
        if text_elem:
            user_text = re.sub(r'\s*…\s*more\s*$', '', text_elem.get_text(separator=" ", strip=True)).strip()
        post_type = 1 if not has_reshare else (3 if len(user_text) > 10 else 2)
        posts.append({"activityId": urn, "url": url, "type": post_type, "user_text": user_text[:500], "has_content": bool(user_text)})

    if posts:
        return posts

    # ── Strategy 3: href /feed/update/ links ─────────────────────────────────
    activity_links = soup.find_all("a", href=re.compile(r"/feed/update/urn:li:"))
    print(f"    [meta] /feed/update/ href links: {len(activity_links)}")
    for link in activity_links:
        href = link.get("href", "")
        m = re.search(r"(urn:li:(?:activity|ugcPost|share):\d+)", href)
        if not m:
            continue
        urn = m.group(1)
        if urn in seen_urns:
            continue
        seen_urns.add(urn)
        url = f"https://www.linkedin.com/feed/update/{urn}/"
        posts.append({"activityId": urn, "url": url, "type": 1, "user_text": "", "has_content": False})

    # ── Strategy 4: scan raw HTML cho 19-digit IDs ───────────────────────────
    if not posts:
        ids = re.findall(r'\buserGeneratedContentId[=:]\D*?(\d{18,20})\b', html)
        unique_ids = list(dict.fromkeys(ids))
        print(f"    [meta] raw HTML ugcPost IDs: {len(unique_ids)}")
        for post_id in unique_ids[:10]:
            urn = f"urn:li:ugcPost:{post_id}"
            if urn in seen_urns:
                continue
            seen_urns.add(urn)
            url = f"https://www.linkedin.com/feed/update/{urn}/"
            posts.append({"activityId": urn, "url": url, "type": 1, "user_text": "", "has_content": False})

    return posts


DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are a precise social media analyst. "
    "Extract recent LinkedIn posts from profile page content and return ONLY valid JSON."
)

_USER_TEMPLATE_WITH_META = """\
The content below is from a LinkedIn recent-activity/all/ page.

## Post metadata extracted from HTML (use these EXACTLY — do not modify activityId or url):
{metadata_block}

## Task
From the full text content below, extract the 3 most recent posts (newest first).
For each post:
- Copy the EXACT activityId and url from metadata (match by text preview similarity)
- Use the type from metadata (1=original, 2=pure repost, 3=repost with own thoughts)
- Extract FULL content, keep original wording, do NOT summarize or translate
- REMOVE all reaction/like/comment/share counts (numbers like "1,234 reactions", "45 comments")
- type 2: content = "(Repost of [author]: [original post text])"
- type 3: content = "[user's added thought] | Reshared: [original post snippet]"

Return ONLY valid JSON:
{{
  "posts": [
    {{"type": 1, "activityId": "urn:li:ugcPost:7474857215565430784", "url": "https://www.linkedin.com/feed/update/urn:li:ugcPost:7474857215565430784/", "date": "3mo", "content": "full post text"}},
    {{"type": 3, "activityId": "urn:li:ugcPost:XXXX", "url": "https://...", "date": "1mo", "content": "user thought | Reshared: ..."}},
    {{"type": 2, "activityId": "urn:li:ugcPost:XXXX", "url": "https://...", "date": "2mo", "content": "(Repost of John: ...)"}}
  ]
}}

IMPORTANT: Return ONLY JSON, no explanation. If url not matchable use "".

LinkedIn activity page content:
{text}"""

_USER_TEMPLATE_NO_META = """\
The content below is from a LinkedIn recent-activity/all/ page (posts, comments, reposts mixed).
Extract the 3 most recent posts (skip comments on others' posts).

Classify type:
- type 1: user wrote it themselves (original)
- type 2: pure repost, no added text
- type 3: repost with user's own thoughts

Return ONLY valid JSON:
{{
  "posts": [
    {{"type": 1, "activityId": "", "url": "", "date": "3mo", "content": "full post text"}},
    {{"type": 3, "activityId": "", "url": "", "date": "1mo", "content": "user thought | Reshared: ..."}},
    {{"type": 2, "activityId": "", "url": "", "date": "2mo", "content": "(Repost of John: ...)"}}
  ]
}}

IMPORTANT: Keep ORIGINAL language. Remove reaction/like/comment count numbers.

LinkedIn activity page content:
{text}"""

_EMPTY = {"post": ""}


def _format_posts_output(posts: list[dict]) -> str:
    """Chuyển list posts → chuỗi bullet cho cột 'Bài Viết'."""
    lines = []
    type_labels = {1: "original", 2: "repost", 3: "repost+thought"}
    for p in posts:
        t = p.get("type", 1)
        url = p.get("url", "")
        activity_id = p.get("activityId", "")
        date = p.get("date", "")
        content = p.get("content", "").strip()

        parts = [f"[type:{t}({type_labels.get(t, '?')})]"]
        if activity_id:
            parts.append(f"[activityId: {activity_id}]")
        if url:
            parts.append(f"[linkPost: {url}]")
        if date:
            parts.append(f"{date}:")
        parts.append(content)

        lines.append("• " + " ".join(parts))
    return "\n".join(lines)


class LinkedInPostExtractor:
    """DeepSeek-based extractor for 3 most recent LinkedIn posts."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def extract(self, text: str, html: str | None = None) -> dict:
        """Extract 3 recent posts. Nếu có html, dùng metadata (URL, type) từ BeautifulSoup."""
        if not text or not text.strip():
            return dict(_EMPTY)

        text = clean_linkedin_content(text)
        truncated = text[:30000]

        # Lấy metadata từ HTML nếu có
        posts_meta: list[dict] = []
        if html:
            try:
                posts_meta = extract_posts_with_metadata(html)
                print(f"    [meta] Found {len(posts_meta)} activity containers in HTML")
            except Exception as e:
                print(f"    [meta] BeautifulSoup parse error: {e}")

        # Build prompt
        if posts_meta:
            meta_lines = []
            for i, m in enumerate(posts_meta[:10], 1):
                type_label = {1: "original", 2: "repost", 3: "repost+thought"}.get(m["type"], "?")
                preview = m["user_text"][:100].replace("\n", " ") if m["user_text"] else "(no text detected)"
                meta_lines.append(
                    f"{i}. activityId={m['activityId']} | type={m['type']}({type_label}) | url={m['url']} | preview: {preview}"
                )
            metadata_block = "\n".join(meta_lines)
            prompt = _USER_TEMPLATE_WITH_META.format(metadata_block=metadata_block, text=truncated)
        else:
            prompt = _USER_TEMPLATE_NO_META.format(text=truncated)

        try:
            response = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=2048,
            )
            generated = response.choices[0].message.content or ""
            return self._parse(generated)
        except Exception as e:
            print(f"    [LinkedInPostExtractor] API error: {e}")
            return dict(_EMPTY)

    def _parse(self, text: str) -> dict:
        # Dùng greedy match để lấy toàn bộ JSON object lớn nhất
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group())
                posts = data.get("posts", [])
                if isinstance(posts, list) and posts:
                    return {"post": _format_posts_output(posts)}
            except json.JSONDecodeError:
                # Thử parse từng chunk nếu DeepSeek trả về markdown code block
                code_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
                if code_match:
                    try:
                        data = json.loads(code_match.group(1))
                        posts = data.get("posts", [])
                        if isinstance(posts, list) and posts:
                            return {"post": _format_posts_output(posts)}
                    except Exception:
                        pass
        # Debug: log raw response khi parse fail
        print(f"    [parse] Failed. Raw response (200 chars): {text[:200].replace(chr(10), ' ')}")
        return dict(_EMPTY)
