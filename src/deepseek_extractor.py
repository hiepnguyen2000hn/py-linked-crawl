import json
import os
import re
from openai import OpenAI

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are an information extraction assistant. "
    "Extract leadership personnel from text and return ONLY a JSON array."
)
_USER_TEMPLATE = """\
Extract all leadership personnel (CEO, CTO, CFO, COO, Founder, Co-founder, \
Director, President, Managing Director, Giám đốc, Tổng giám đốc, Chủ tịch) \
from the following text.
Return ONLY a JSON array like: [{{"name": "...", "title": "..."}}]
If none found, return []

Text:
{text}"""


class DeepSeekExtractor:
    """DeepSeek API-based leadership extractor. Same interface as IEExtractor."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def extract(self, text: str) -> list[dict]:
        """Extract [{name, title}] from text. Returns [] if none found."""
        truncated = text[:4000]
        response = self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _USER_TEMPLATE.format(text=truncated)},
            ],
            temperature=0,
            max_tokens=512,
        )
        generated = response.choices[0].message.content or ""
        return self._parse(generated)

    def _parse(self, text: str) -> list[dict]:
        try:
            match = re.search(r"\[.*?\]", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return [
                    d for d in data
                    if isinstance(d, dict) and "name" in d and "title" in d
                ]
        except Exception:
            pass
        return []
