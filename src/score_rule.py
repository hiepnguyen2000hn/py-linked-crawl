# src/score_rule.py
"""
Rule-based ICP scoring — 100 điểm.
Dùng sau khi enrich company sheet (có Blog, Tuyển Dụng, Dự Án Gần Nhất, Đối Tác).
"""
import re
from typing import TypedDict


class ScoreResult(TypedDict):
    ICP_Bucket: str
    Score_Total: int
    Tier:        str
    Reason_1:    str
    Reason_2:    str
    Reason_3:    str


# ── helpers ───────────────────────────────────────────────────────────────────

def _get(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _txt(row: dict, *keys: str) -> str:
    return _get(row, *keys).lower()


def _has(text: str, keywords: list) -> bool:
    return any(k in text for k in keywords)


def _parse_headcount(count: str, range_str: str):
    try:
        n = int(count)
        if n > 0:
            return n
    except (ValueError, TypeError):
        pass
    if range_str:
        m = re.match(r"(\d+)", range_str)
        if m:
            return int(m.group(1))
    return None


# ── A. Geography — 15 điểm ────────────────────────────────────────────────────

_GEO_TIER1 = [
    "united states", "canada", " us ", "usa",
    "singapore", "hong kong",
    "united kingdom", "ireland", "france", "germany", " uk ",
]
_GEO_EU = [
    "netherlands", "sweden", "denmark", "norway", "finland", "spain",
    "italy", "belgium", "austria", "switzerland", "poland", "czech",
    "portugal", "luxembourg", "hungary", "romania",
]


def _geo_pts(value: str):
    c = (" " + value + " ").lower()
    if _has(c, _GEO_TIER1): return 15
    if _has(c, _GEO_EU):    return 8
    return 0


def _score_geo(row: dict):
    country = _get(row, "country")
    city    = _get(row, "city")

    country_pts = _geo_pts(country) if country else 0
    city_pts    = _geo_pts(city)    if city    else 0

    pts  = max(country_pts, city_pts)
    best = country if country_pts >= city_pts else city

    if not country and not city:
        return 0, "No country/city data"
    if pts == 15:
        return 15, f"Target geo: {best}"
    if pts == 8:
        return 8, f"EU market: {best}"
    return 0, f"Out-of-target: {country or city or '?'}"


# ── B. Company Size — 15 điểm ─────────────────────────────────────────────────

def _score_size(row: dict):
    count = _get(row, "employee_count")
    rng   = _get(row, "employee_range")
    n     = _parse_headcount(count, rng)
    label = count or rng or "?"
    if n is None:
        return 0, None, "No headcount data"
    if n >= 1000: return 15, n, f"Enterprise: {label} employees"
    if n >= 250:  return 12, n, f"Mid-market: {label} employees"
    if n >= 100:  return 6,  n, f"SMB: {label} employees"
    return 0, n, f"Small (<100): {label} employees"


# ── C. Industry — 15 điểm ─────────────────────────────────────────────────────

_IND_TIER1 = [
    "finance", "financial services", "banking", "bank", "wealth", "payment",
    "insurance", "telco", "telecom", "telecommunications",
    "ecommerce", "e-commerce", "retail", "healthcare", "health tech",
    "healthtech", "medtech", "medical",
]
_IND_TIER2 = ["technology", "software", "saas", "fintech", "platform", "b2b software"]
_IND_TIER3 = ["staffing", "recruiting", "outsourcing", "it services", "consulting", "agency"]


def _score_industry(row: dict):
    t  = (_get(row, "industry") + " " + _get(row, "Lĩnh Vực") + " " + _get(row, "description")).lower()
    lbl = _get(row, "industry") or _get(row, "Lĩnh Vực") or "n/a"
    if _has(t, _IND_TIER1): return 15, f"Priority industry: {lbl}"
    if _has(t, _IND_TIER2): return 12, f"Tech/SaaS: {lbl}"
    if _has(t, _IND_TIER3): return 5,  f"IT vendor/agency: {lbl}"
    if not _get(row, "industry") and not _get(row, "Lĩnh Vực"):
        return 0, "No industry data"
    return 3, f"Non-priority: {lbl}"


# ── D. Company Type — 10 điểm ─────────────────────────────────────────────────

_AGENCY_KW = [
    "outsourcing", "software house", "it services", "staffing",
    "recruitment", "body leasing", "consulting", "offshore", "agency",
]


def _score_type(row: dict):
    t = (_get(row, "description") + " " + _get(row, "Dự Án Gần Nhất")).lower()
    if not t.strip():
        return 5, "Company type unknown (no description)"
    if _has(t, _AGENCY_KW):
        return 3, "Agency/outsourcing type"
    return 10, "End-user / product company"


# ── E. AI/DX Signals — 15 điểm ───────────────────────────────────────────────

_AI_STRONG = [
    "ai automation", "generative ai", "genai", "llm", "large language model",
    "rag", "retrieval augmented", "ocr", "intelligent document processing",
    "workflow automation", "chatbot", "virtual assistant", "knowledge base",
    "data pipeline", "mlops", "machine learning", "deep learning",
]
_AI_MEDIUM = [
    "digital transformation", "analytics", "data platform", "automation",
    "process improvement", "rpa", "robotic process automation",
]
_HIRE_AI = ["ai", "machine learning", "ml ", "nlp", "llm", "data engineer", "data scientist", "software engineer"]


def _score_ai(row: dict):
    desc    = (_get(row, "description") + " " + _get(row, "Lĩnh Vực")).lower()
    blog    = (_get(row, "Blog") + " " + _get(row, "Dự Án Gần Nhất")).lower()
    hire    = _get(row, "Tuyển Dụng").lower()
    posts   = _get(row, "Bài Viết").lower()

    # E1: description/specialties (max 8)
    strong_hits = [k for k in _AI_STRONG if k in desc]
    medium_hits = [k for k in _AI_MEDIUM if k in desc]
    e1 = 8 if strong_hits else (4 if medium_hits else 0)

    # E2: blog/project/posts (max 4)
    e2_t = blog + " " + posts
    e2 = 4 if (_has(e2_t, _AI_STRONG) or _has(e2_t, _AI_MEDIUM)) else 0

    # E3: hiring (max 3)
    e3 = 3 if _has(hire, _HIRE_AI) else 0

    total = min(15, e1 + e2 + e3)

    matched = strong_hits[:2] or medium_hits[:1]
    if matched:
        note = f"AI signals: {', '.join(matched[:2])}"
    elif e2 > 0:
        note = "AI signals in blog/projects"
    elif e3 > 0:
        note = "AI/tech hiring signals"
    else:
        note = "No AI/DX signals"

    return total, e1, note


# ── F. Service Fit — 10 điểm ─────────────────────────────────────────────────

_SVC_DOC = [
    "kyc", "aml", "claims", "underwriting", "invoice", "billing",
    "settlement", "reconciliation", "onboarding", "compliance reporting",
]
_SVC_DATA = ["data pipeline", "ml pipeline", "etl", "data warehouse", "data lake"]


def _score_service(row: dict):
    t = (_get(row, "description") + " " + _get(row, "Dự Án Gần Nhất")).lower()
    doc_hits = [k for k in _SVC_DOC if k in t]
    if doc_hits:
        return 10, f"Doc-heavy ops: {', '.join(doc_hits[:2])}"
    if _has(t, _SVC_DATA):
        return 8, "Data/ML pipeline needs"
    if not t.strip():
        return 3, "No description — service fit unclear"
    return 5, "General fit — no specific ops signals"


# ── G. Decision Maker — 20 điểm ──────────────────────────────────────────────

def _score_dm(row: dict):
    title = _get(row, "job_title", "occupation").lower()
    if not title:
        return 5, "No title data (default)"
    if _has(title, ["cto", "cio", "vp engineering", "head of engineering", "vp of engineering"]):
        return 20, f"C/VP tech: {title[:50]}"
    if _has(title, ["head of data", "head of ai", "head of digital", "chief data", "chief ai", "chief technology"]):
        return 18, f"AI/Data lead: {title[:50]}"
    if _has(title, ["head of product", "product director", "vp product", "vp of product"]):
        return 16, f"Product lead: {title[:50]}"
    if _has(title, ["coo", "operations director", "director of operations"]):
        return 12, f"Ops lead: {title[:50]}"
    if _has(title, ["engineering manager", "product owner", "program manager", "project manager", "tech lead"]):
        return 10, f"Manager: {title[:50]}"
    if _has(title, ["procurement", "vendor management"]):
        return 8, f"Procurement: {title[:50]}"
    if _has(title, ["director", "vp ", "vice president", "head "]):
        return 10, f"Director/VP: {title[:50]}"
    if _has(title, ["manager", "lead ", "senior"]):
        return 8, f"Senior/Manager: {title[:50]}"
    if _has(title, ["bd", "business development", "hr", "human resources", "recruiter", "sales"]):
        return 2, f"Non-technical: {title[:50]}"
    return 5, f"Unknown: {title[:50]}"


# ── H. Engagement — 5 điểm ───────────────────────────────────────────────────

def _score_engagement(row: dict):
    premium = _get(row, "premium").lower()
    posts   = _get(row, "Bài Viết")
    pts     = 0
    notes   = []
    if premium in ("true", "yes", "1", "premium"):
        pts += 2
        notes.append("Premium account")
    if posts and len(posts.strip()) > 20:
        pts += 3
        notes.append("Has recent posts")
    return pts, "; ".join(notes) if notes else "No engagement signals"


# ── Bonus / Penalty ───────────────────────────────────────────────────────────

_ENTERPRISE_PARTNERS = [
    "bank", "insurance", "telco", "government", "microsoft", "google",
    "aws", "amazon", "salesforce", "sap", "oracle", "visa", "mastercard",
]


def _bonus_penalty(row: dict):
    bonus   = 0
    penalty = 0

    partners = _get(row, "Đối Tác").lower()
    if _has(partners, _ENTERPRISE_PARTNERS):
        bonus += 3

    industry = _get(row, "industry")
    count    = _get(row, "employee_count")
    rng      = _get(row, "employee_range")
    desc     = _get(row, "description")

    if not industry and not count and not rng:
        penalty += 5
    elif not industry:
        penalty += 5
    elif not count and not rng:
        penalty += 5
    if not desc:
        penalty += 5

    return min(5, bonus), min(10, penalty)


# ── ICP Bucket ────────────────────────────────────────────────────────────────

def _icp_bucket(row: dict, size_n, ai_e1: int, dm_pts: int) -> str:
    ind_t = (_get(row, "industry") + " " + _get(row, "Lĩnh Vực")).lower()
    n = size_n or 0
    is_priority = _has(ind_t, _IND_TIER1)
    is_tech     = not is_priority and _has(ind_t, _IND_TIER2)
    if n >= 250 and is_priority and ai_e1 >= 8:
        return "Enterprise AI Automation (ICP-A)"
    if is_tech and ai_e1 >= 8 and dm_pts >= 10:
        return "Tech AI Product Delivery (ICP-B)"
    return "Not ICP"


# ── Main ──────────────────────────────────────────────────────────────────────

def score_company(row: dict) -> ScoreResult:
    """Score một company row theo ICP barem (100 điểm)."""
    geo_pts,  geo_note            = _score_geo(row)
    size_pts, size_n, size_note   = _score_size(row)
    ind_pts,  ind_note            = _score_industry(row)
    type_pts, type_note           = _score_type(row)
    ai_pts,   ai_e1, ai_note      = _score_ai(row)
    svc_pts,  svc_note            = _score_service(row)
    dm_pts,   dm_note             = _score_dm(row)
    eng_pts,  eng_note            = _score_engagement(row)
    bonus,    penalty             = _bonus_penalty(row)

    raw         = geo_pts + size_pts + ind_pts + type_pts + ai_pts + svc_pts + dm_pts + eng_pts
    score_total = max(0, min(100, raw + bonus - penalty))

    if   score_total >= 80: tier = "HOT"
    elif score_total >= 60: tier = "WARM"
    elif score_total >= 40: tier = "COLD"
    else:                   tier = "DROP"

    icp = _icp_bucket(row, size_n, ai_e1, dm_pts)

    dims = sorted([
        (geo_pts,  geo_note),
        (size_pts, size_note),
        (ind_pts,  ind_note),
        (type_pts, type_note),
        (ai_pts,   ai_note),
        (svc_pts,  svc_note),
        (dm_pts,   dm_note),
        (eng_pts,  eng_note),
    ], key=lambda x: -x[0])

    return ScoreResult(
        ICP_Bucket  = icp,
        Score_Total = score_total,
        Tier        = tier,
        Reason_1    = dims[0][1] if len(dims) > 0 else "",
        Reason_2    = dims[1][1] if len(dims) > 1 else "",
        Reason_3    = dims[2][1] if len(dims) > 2 else "",
    )