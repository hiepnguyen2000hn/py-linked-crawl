"""
Connect message generator — dùng DeepSeek để tạo LinkedIn connection request message
cá nhân hoá từ thông tin lead, theo ICP-A / ICP-B template.

ICP-A: Enterprise End-user (Finance/Telco/Healthcare) — DX/automation/compliance angle
ICP-B: Tech/Fintech/SaaS building AI features & data pipelines
"""
import os
from openai import OpenAI

DEEPSEEK_MODEL    = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are an expert at writing warm, professional LinkedIn connection request messages. "
    "Messages must be concise (under 300 characters), natural, and never sound like a sales pitch. "
    "Return ONLY the message text — no quotes, no explanation, no subject line."
)

# ── ICP-A: Enterprise End-user (Finance/Telco/Healthcare) ────────────────────

_PROMPT_A_WITH_POST = """\
Write a LinkedIn connection note (≤300 characters) for this lead.
Use this exact style — fill in the bracketed parts with real specifics from their post:
"Hi [Name], your point on [DX/automation/compliance topic from their post] resonates \
— we see the same execution gap in SG/HK enterprises. Integrating AI workflows that \
survive governance is harder than the model. Open to connect and exchange notes?"

Lead info:
- First name: {first_name}
- Job title: {job_title}
- Company: {company_name}
- Country: {country}
- Recent post/activity: {post_ref}

Rules: under 300 characters, natural tone, NO sales pitch, return ONLY the message."""

_PROMPT_A_NO_POST = """\
Write a LinkedIn connection note (≤300 characters) for this lead.
Use this exact style — fill in the bracketed parts with real specifics:
"Hi [Name], I noticed [Company] is pushing on [DX/AI/automation area relevant to their industry] \
— the integration and governance layer is where most SG/HK enterprise teams lose weeks. \
Open to connect and exchange practical notes?"

Lead info:
- First name: {first_name}
- Job title: {job_title}
- Company: {company_name}
- Country: {country}
- Profile bio: {occupation}

Rules: under 300 characters, natural tone, NO sales pitch, return ONLY the message."""

# ── ICP-B: Tech/Fintech/SaaS building AI features & data pipelines ────────────

_PROMPT_B_WITH_POST = """\
Write a LinkedIn connection note (≤300 characters) for this lead.
Use this exact style — fill in the bracketed parts with real specifics from their post:
"Hi [Name], your take on [AI/data pipeline topic from their post] is spot on \
— the integration layer is where most teams lose time. Open to connect and share \
what we've seen work in SG/HK product teams?"

Lead info:
- First name: {first_name}
- Job title: {job_title}
- Company: {company_name}
- Country: {country}
- Recent post/activity: {post_ref}

Rules: under 300 characters, natural tone, NO sales pitch, return ONLY the message."""

_PROMPT_B_NO_POST = """\
Write a LinkedIn connection note (≤300 characters) for this lead.
Use this exact style — fill in the bracketed parts with real specifics:
"Hi [Name], I noticed [Company] is building out [AI/data capability based on their profile] \
— the integration layer is where most product teams lose time. Open to connect and share \
notes on reliable delivery?"

Lead info:
- First name: {first_name}
- Job title: {job_title}
- Company: {company_name}
- Country: {country}
- Profile bio: {occupation}

Rules: under 300 characters, natural tone, NO sales pitch, return ONLY the message."""

# ── Fallback (Unknown ICP) ────────────────────────────────────────────────────

_PROMPT_FALLBACK = """\
Write a short LinkedIn connection request note (≤300 characters) for this lead.

Lead info:
- First name: {first_name}
- Job title: {job_title}
- Company: {company_name}
- Country: {country}
- Profile bio: {occupation}

Rules: under 300 characters, personalise using their name/role/company, \
warm human tone, end with a soft CTA, NO sales pitch, return ONLY the message."""

# ── ICP classification keywords ───────────────────────────────────────────────

_ICP_A_KW = [
    "finance", "financial", "banking", "bank", "wealth", "payment", "insurance",
    "telco", "telecom", "telecommunications", "ecommerce", "e-commerce", "retail",
    "healthcare", "health tech", "healthtech", "medtech", "medical", "hospital",
    "government", "public sector",
]
_ICP_B_KW = [
    "technology", "software", "saas", "fintech", "platform", "b2b software",
    "startup", "cloud", "data", "ai ", "machine learning", "product company",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _determine_icp(row: dict) -> str:
    # Ưu tiên ICP_Bucket nếu sheet đã có từ bước enrich
    bucket = _get(row, "ICP_Bucket", "icp_bucket")
    if "ICP-A" in bucket or "Enterprise AI" in bucket:
        return "ICP-A"
    if "ICP-B" in bucket or "Tech AI" in bucket:
        return "ICP-B"

    # Fallback: phân loại từ industry + occupation + company name
    text = " ".join([
        _get(row, "industry", "Industry", "Lĩnh Vực"),
        _get(row, "occupation"),
        _get(row, "company_name"),
        _get(row, "description"),
    ]).lower()

    if any(k in text for k in _ICP_A_KW):
        return "ICP-A"
    if any(k in text for k in _ICP_B_KW):
        return "ICP-B"
    return "Unknown"


def _has_post(row: dict) -> bool:
    post = _get(row, "Bài Viết", "bai_viet", "posts")
    return len(post) > 30


# ── Main class ────────────────────────────────────────────────────────────────

class ConnectMessageGenerator:
    """Generate personalised ICP-based LinkedIn connect messages using DeepSeek."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def determine_icp(self, row: dict) -> str:
        return _determine_icp(row)

    def generate(self, row: dict) -> str:
        """
        Generate a connect message for one lead row.
        Returns message string (≤300 chars), or "" on failure.
        """
        first_name   = (_get(row, "firstName") or _get(row, "fullName").split()[0] or "there")
        job_title    = _get(row, "job_title")
        company_name = _get(row, "company_name")
        country      = _get(row, "country", "location")
        occupation   = _get(row, "occupation")[:200]
        post_ref     = _get(row, "Bài Viết", "bai_viet", "posts")[:300]

        icp      = _determine_icp(row)
        has_post = _has_post(row)

        if icp == "ICP-A":
            template = _PROMPT_A_WITH_POST if has_post else _PROMPT_A_NO_POST
        elif icp == "ICP-B":
            template = _PROMPT_B_WITH_POST if has_post else _PROMPT_B_NO_POST
        else:
            template = _PROMPT_FALLBACK

        prompt = template.format(
            first_name=first_name,
            job_title=job_title or "professional",
            company_name=company_name or "your company",
            country=country or "Asia",
            occupation=occupation or "(no bio)",
            post_ref=post_ref or "",
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
            msg = (response.choices[0].message.content or "").strip()
            if msg.startswith('"') and msg.endswith('"'):
                msg = msg[1:-1].strip()
            return msg
        except Exception as e:
            print(f"    [ConnectMessageGenerator] API error: {e}")
            return ""
