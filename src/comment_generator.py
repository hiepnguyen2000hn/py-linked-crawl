"""
Comment generator — dùng DeepSeek để sinh nội dung comment tự nhiên,
tương tác dưới bài viết LinkedIn đã crawl (cột "Bài Viết").

Khác với ConnectMessageGenerator (sinh lời mời kết nối), class này sinh
1 câu/đoạn comment ngắn để post trực tiếp dưới bài viết của lead — mục
đích tạo tương tác (like/reply) trước khi gửi connect request.
"""
import os
from openai import OpenAI

DEEPSEEK_MODEL    = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are a professional who writes genuine, human-sounding LinkedIn comments. "
    "You engage with the specific substance of a post — agree/disagree with a point, "
    "add a related insight, or ask a thoughtful follow-up question. "
    "You never sound like a bot, never use generic praise alone (e.g. 'Great post!'), "
    "and never pitch a product or service. "
    "Return ONLY the comment text — no quotes, no hashtags, no explanation."
)

_PROMPT_WITH_POST = """\
Write a short LinkedIn comment (1-3 sentences, ≤400 characters) reacting to this person's post.
Engage with a specific point they made — do not just praise it generically.

Author: {first_name}, {job_title} at {company_name}
Post content:
{post_ref}

Rules: natural conversational tone, no sales pitch, no hashtags, return ONLY the comment text."""


def _get(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _has_post(row: dict) -> bool:
    post = _get(row, "Bài Viết", "bai_viet", "post", "posts")
    return len(post) > 30


class CommentGenerator:
    """Generate a genuine, personalised LinkedIn comment from a lead's crawled post."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def generate(self, row: dict) -> str:
        """
        Generate a comment for one lead row, based on their crawled post content.
        Returns comment string (≤400 chars), or "" if there's no post to react to
        or generation fails.
        """
        if not _has_post(row):
            return ""

        first_name   = _get(row, "firstName") or (_get(row, "fullName").split() or ["there"])[0]
        job_title    = _get(row, "job_title")
        company_name = _get(row, "company_name")
        post_ref     = _get(row, "Bài Viết", "bai_viet", "post", "posts")[:2000]

        prompt = _PROMPT_WITH_POST.format(
            first_name=first_name,
            job_title=job_title or "professional",
            company_name=company_name or "their company",
            post_ref=post_ref,
        )

        try:
            response = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.7,
                max_tokens=150,
            )
            comment = (response.choices[0].message.content or "").strip()
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1].strip()
            return comment
        except Exception as e:
            print(f"    [CommentGenerator] API error: {e}")
            return ""
