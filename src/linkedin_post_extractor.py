import json
import os
import re
from openai import OpenAI


def clean_linkedin_content(text: str) -> str:
    """Strip LinkedIn noise: signup URLs, tracking links — giữ nguyên nội dung post."""
    # Xoá [...more](url) — chỉ xoá phần link, giữ nguyên text trước đó
    text = re.sub(r'\[\.\.\.more\]\([^)]*\)', '', text)
    # Xoá markdown links chứa signup hoặc trk= (tracking/ads) — giữ anchor text
    text = re.sub(r'\[([^\]]+)\]\(https?://[^\)]*(?:signup|trk=)[^\)]*\)', r'\1', text)
    # Xoá URL trần chứa linkedin.com/signup hoặc tracking
    text = re.sub(r'https?://\S*(?:signup|trk=)\S*', '', text)
    # Xoá dòng trắng thừa nhưng giữ nguyên nội dung
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return '\n'.join(lines)

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are a precise social media analyst. "
    "Extract recent LinkedIn posts from profile page content and return ONLY valid JSON."
)

_USER_TEMPLATE = """\
The content below is from a LinkedIn recent-activity/all/ page (posts, comments, reposts mixed).
Extract the 3 most recent ORIGINAL posts that the user themselves wrote (skip comments on others' posts, skip pure reposts with no added text).
Return ONLY a JSON object with exactly 1 key:

- "post": The 3 most recent posts, one per line using bullet •, format:
  "• [date if available]: [full original post content]\\n• ...\\n• ..."
  Keep the EXACT original wording. Do NOT summarize, shorten, or paraphrase.
  If no posts found, use "".

Return ONLY JSON, no explanation. Example:
{{
  "post": "• 3mo: When it comes to writing - of all kinds (including textbooks!) people know what they like to read. It isn't AI generated.\\n• 1yr: Hi folks! I currently have availability for 1 or 2 new fractional CTO clients...\\n• 2yr: We're hiring a Senior Engineer to join our team"
}}

IMPORTANT: Keep each post in its ORIGINAL language and ORIGINAL wording. Do NOT translate.

LinkedIn activity page content:
{text}"""

_EMPTY = {
    "post": "",
}


class LinkedInPostExtractor:
    """DeepSeek-based extractor for 3 most recent LinkedIn posts."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def extract(self, text: str) -> dict:
        """Extract 3 recent posts from LinkedIn profile content. Always returns all 3 keys."""
        if not text or not text.strip():
            return dict(_EMPTY)
        text = clean_linkedin_content(text)
        truncated = text[:30000]
        try:
            response = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _USER_TEMPLATE.format(text=truncated)},
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
        result = dict(_EMPTY)
        try:
            match = re.search(r"\{.*?\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                if "post" in data and isinstance(data["post"], str):
                    result["post"] = data["post"].strip()
        except Exception:
            pass
        return result
