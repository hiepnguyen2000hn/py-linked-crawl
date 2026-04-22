"""
Connect message generator — dùng DeepSeek để tạo LinkedIn connection request message
cá nhân hoá từ thông tin lead lấy từ sheet.
"""
import os
from openai import OpenAI

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are an expert at writing warm, professional LinkedIn connection request messages. "
    "Messages must be concise (under 300 characters), natural, and never sound like a sales pitch. "
    "Return ONLY the message text — no quotes, no explanation, no subject line."
)

# ── Prompt template ────────────────────────────────────────────────────────────
# TODO: customise this prompt to reflect your actual outreach context.
# Current placeholder: generic connection request from an AI/automation services company.
_USER_TEMPLATE = """\
Write a short LinkedIn connection request message in English for this lead:

Name: {first_name}
Job Title: {job_title}
Company: {company_name}
Industry: {industry}
Country: {country}

Context about the sender:
- We build AI automation and data pipeline solutions for tech companies
- We help teams automate repetitive workflows, document processing, and data enrichment
- We want to connect genuinely — no hard sell, just explore potential fit

Rules:
- Under 300 characters (LinkedIn InMail limit for connection notes)
- Personalise using their name, role, or company — do NOT use a generic opener
- Warm and human tone, not corporate
- End with a soft call-to-action (e.g. "Would love to connect!")
- Output ONLY the message, nothing else"""


class ConnectMessageGenerator:
    """Generate personalised LinkedIn connection request messages using DeepSeek."""

    def __init__(self, api_key: str | None = None):
        # TODO: uncomment khi dùng DeepSeek
        # key = api_key or os.getenv("DEEPSEEK_API_KEY")
        # if not key:
        #     raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        # self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
        pass

    def generate(self, row: dict) -> str:
        """
        Generate a connection message for one lead row.
        Expects keys: firstName, fullName, job_title, company_name, industry, country.
        Returns the message string, or "" on failure.
        """
        # TODO: uncomment để dùng DeepSeek, xoá dòng return "hello" bên dưới
        # first_name   = (row.get("firstName") or row.get("fullName", "").split()[0] or "there").strip()
        # job_title    = (row.get("job_title") or "").strip()
        # company_name = (row.get("company_name") or "").strip()
        # industry     = (row.get("industry") or "").strip()
        # country      = (row.get("country") or row.get("location") or "").strip()
        #
        # prompt = _USER_TEMPLATE.format(
        #     first_name=first_name,
        #     job_title=job_title or "professional",
        #     company_name=company_name or "your company",
        #     industry=industry or "Technology",
        #     country=country or "",
        # )
        #
        # try:
        #     response = self._client.chat.completions.create(
        #         model=DEEPSEEK_MODEL,
        #         messages=[
        #             {"role": "system", "content": _SYSTEM},
        #             {"role": "user",   "content": prompt},
        #         ],
        #         temperature=0.7,
        #         max_tokens=150,
        #     )
        #     msg = (response.choices[0].message.content or "").strip()
        #     if msg.startswith('"') and msg.endswith('"'):
        #         msg = msg[1:-1].strip()
        #     return msg
        # except Exception as e:
        #     print(f"    [ConnectMessageGenerator] API error: {e}")
        #     return ""

        return "hello"
