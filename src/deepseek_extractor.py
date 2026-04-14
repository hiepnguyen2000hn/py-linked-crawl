import json
import os
import re
from openai import OpenAI

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are a precise information extraction assistant. "
    "Extract leadership and management personnel from text and return ONLY valid JSON."
)

_USER_TEMPLATE = """\
Extract ALL leadership and management personnel from the text below.

Include anyone with a role such as:
CEO, CTO, CFO, COO, CPO, CMO, CRO, CISO, Founder, Co-founder,
President, Vice President, VP, SVP, EVP, Director, Managing Director,
Board Member, Chairman, Partner, Head of, Lead, Manager,
Giám đốc, Phó Giám đốc, Tổng Giám đốc, Chủ tịch, Trưởng phòng, Quản lý.

Return ONLY a JSON array. Each item must have:
- "name": full name of the person
- "title": their exact role/title
- "linkedin": their personal LinkedIn URL (linkedin.com/in/...) if found, else ""
- "email": their personal email if found, else ""

Example output:
[
  {{"name": "John Smith", "title": "CEO & Co-founder", "linkedin": "https://linkedin.com/in/johnsmith", "email": "john@company.com"}},
  {{"name": "Jane Doe", "title": "CTO", "linkedin": "", "email": ""}}
]

If no leadership personnel found, return []

Text:
{text}"""


class DeepSeekExtractor:
    """DeepSeek API-based leadership extractor."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def extract(self, text: str) -> list[dict]:
        """Extract [{name, title, linkedin, email}] from text. Returns [] if none found."""
        truncated = text[:30000]
        response = self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _USER_TEMPLATE.format(text=truncated)},
            ],
            temperature=0,
            max_tokens=1024,
        )
        generated = response.choices[0].message.content or ""
        return self._parse(generated)

    def _parse(self, text: str) -> list[dict]:
        try:
            match = re.search(r"\[.*?\]", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                results = []
                for d in data:
                    if not isinstance(d, dict) or not d.get("name"):
                        continue
                    results.append({
                        "name": d.get("name", "").strip(),
                        "title": d.get("title", "").strip(),
                        "linkedin": d.get("linkedin", "").strip(),
                        "email": d.get("email", "").strip(),
                    })
                return results
        except Exception:
            pass
        return []
