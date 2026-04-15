# src/score_rule.py
"""
Rule-based ICP scoring — 100 điểm.
ICP-A: Enterprise End-user (AI Automation & DX) — SG/HK, 250+, Finance/Telco/Health...
ICP-B: Tech/Fintech/SaaS (Build AI Features & Data) — SG/HK, 100-1000, Tech/Fintech...
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
# Primary: SG/HK (15) — core markets cho cả ICP-A và ICP-B
# Secondary: US/CA/UK/EU (10) — có thể qualify nhưng không focus
# EU rest: 5
# Others: 0

_GEO_PRIMARY   = ["singapore", "hong kong"]
_GEO_SECONDARY = [
    "united states", "canada", " us ", "usa",
    "united kingdom", "ireland", "france", "germany", " uk ",
    "australia", "new zealand",
]
_GEO_EU = [
    "netherlands", "sweden", "denmark", "norway", "finland", "spain",
    "italy", "belgium", "austria", "switzerland", "poland", "czech",
    "portugal", "luxembourg", "hungary", "romania",
]


def _geo_pts(value: str):
    c = (" " + value + " ").lower()
    if _has(c, _GEO_PRIMARY):   return 15
    if _has(c, _GEO_SECONDARY): return 10
    if _has(c, _GEO_EU):        return 5
    return 0


def _score_geo(row: dict):
    country = _get(row, "country")
    city    = _get(row, "city")

    country_pts = _geo_pts(country) if country else 0
    city_pts    = _geo_pts(city)    if city    else 0

    pts  = max(country_pts, city_pts)
    best = country if country_pts >= city_pts else city

    if not country and not city:
        return 0, False, "No country/city data"
    if pts == 15:
        return 15, True,  f"Primary market: {best} (SG/HK)"
    if pts == 10:
        return 10, False, f"Secondary market: {best}"
    if pts == 5:
        return 5,  False, f"EU market: {best}"
    return 0, False, f"Out-of-target: {country or city or '?'}"


# ── B. Company Size — 15 điểm ─────────────────────────────────────────────────

def _score_size(row: dict):
    count = _get(row, "employee_count")
    rng   = _get(row, "employee_range")
    n     = _parse_headcount(count, rng)
    label = count or rng or "?"
    if n is None:
        return 0, None, "No headcount data"
    if n >= 1000: return 15, n, f"Enterprise 1000+: {label} employees"
    if n >= 250:  return 12, n, f"Mid-market 250-999: {label} employees"
    if n >= 100:  return 6,  n, f"SMB 100-249: {label} employees"
    return 0, n, f"Small (<100): {label} employees"


# ── C. Industry — 15 điểm ─────────────────────────────────────────────────────
# ICP-A priority: Finance/Banking/Insurance/Telco/Ecom/Health (end-user)
# ICP-B priority: Tech/SaaS/Fintech/Platform

_IND_A = [
    "finance", "financial services", "banking", "bank", "wealth", "payment",
    "insurance", "telco", "telecom", "telecommunications",
    "ecommerce", "e-commerce", "retail", "healthcare", "health tech",
    "healthtech", "medtech", "medical",
]
_IND_B = ["technology", "software", "saas", "fintech", "platform", "b2b software"]
_IND_VENDOR = ["staffing", "recruiting", "outsourcing", "it services", "consulting", "agency", "software house"]


def _score_industry(row: dict):
    t   = (_get(row, "industry") + " " + _get(row, "Lĩnh Vực") + " " + _get(row, "description")).lower()
    lbl = _get(row, "industry") or _get(row, "Lĩnh Vực") or "n/a"
    if _has(t, _IND_A):      return 15, lbl, f"ICP-A industry: {lbl}"
    if _has(t, _IND_B):      return 12, lbl, f"ICP-B industry (Tech/SaaS): {lbl}"
    if _has(t, _IND_VENDOR): return 5,  lbl, f"Vendor/agency: {lbl}"
    if not _get(row, "industry") and not _get(row, "Lĩnh Vực"):
        return 0, "", "No industry data"
    return 3, lbl, f"Non-priority: {lbl}"


# ── D. Company Type — 10 điểm ─────────────────────────────────────────────────
# Disqualifier signal: freelancer/marketplace → giảm thêm

_AGENCY_KW = [
    "outsourcing", "software house", "it services", "staffing", "staff augmentation",
    "recruitment", "body leasing", "consulting firm", "offshore development", "agency",
]
_FREELANCE_KW = ["freelancer", "marketplace", "contractor", "gig platform"]


def _score_type(row: dict):
    t = (_get(row, "description") + " " + _get(row, "Dự Án Gần Nhất")).lower()
    if not t.strip():
        return 5, "Company type unknown (no description)"
    if _has(t, _FREELANCE_KW):
        return 0, "Freelancer/marketplace platform (disqualifier)"
    if _has(t, _AGENCY_KW):
        return 3, "Agency/outsourcing type"
    return 10, "End-user / product company"


# ── E. AI/DX Signals — 15 điểm ───────────────────────────────────────────────
# E1: description/Lĩnh Vực (max 8)
# E2: Blog/Dự Án Gần Nhất/Bài Viết (max 4)
# E3: Tuyển Dụng (max 3)

_AI_STRONG = [
    # Core AI/ML
    "ai automation", "generative ai", "genai", "llm", "large language model",
    "rag", "retrieval augmented", "ocr", "intelligent document processing",
    "workflow automation", "chatbot", "virtual assistant", "knowledge base",
    "data pipeline", "mlops", "machine learning", "deep learning",
    # ICP-B specific
    "copilot", "ai assistant", "summarization", "classification", "recommendation engine",
    "vector database", "vector db", "embedding", "semantic search",
    "etl", "elt", "data observability", "feature store",
]
_AI_MEDIUM = [
    "digital transformation", "analytics", "data platform", "automation",
    "process improvement", "rpa", "robotic process automation",
    # ICP-A triggers
    "erp migration", "crm migration", "sharepoint migration", "modernization",
    "compliance", "audit", "regulatory", "cost reduction",
    "operations overload", "scalability",
    # ICP-B triggers
    "ai features", "product roadmap", "series a", "series b", "funded", "recently raised",
]
_HIRE_AI = [
    "ai engineer", "ml engineer", "machine learning", "data scientist",
    "data engineer", "nlp", "llm", "software engineer", "backend engineer",
]


def _score_ai(row: dict):
    desc  = (_get(row, "description") + " " + _get(row, "Lĩnh Vực")).lower()
    blog  = (_get(row, "Blog") + " " + _get(row, "Dự Án Gần Nhất")).lower()
    hire  = _get(row, "Tuyển Dụng").lower()
    posts = _get(row, "Bài Viết").lower()

    # E1: description/specialties (max 8)
    strong_hits = [k for k in _AI_STRONG if k in desc]
    medium_hits = [k for k in _AI_MEDIUM if k in desc]
    e1 = 8 if strong_hits else (4 if medium_hits else 0)

    # E2: blog/project/posts (max 4)
    e2_t = blog + " " + posts
    e2 = 4 if (_has(e2_t, _AI_STRONG) or _has(e2_t, _AI_MEDIUM)) else 0

    # E3: hiring AI/data/engineering (max 3)
    e3 = 3 if _has(hire, _HIRE_AI) else 0

    total = min(15, e1 + e2 + e3)

    matched = strong_hits[:2] or medium_hits[:1]
    if matched:
        note = f"AI/DX signals: {', '.join(matched[:2])}"
    elif e2 > 0:
        note = "AI signals in blog/projects"
    elif e3 > 0:
        note = "AI/tech hiring signals"
    else:
        note = "No AI/DX signals"

    return total, e1, note


# ── F. Service Fit — 10 điểm ─────────────────────────────────────────────────
# ICP-A: document-heavy ops, compliance, ERP/CRM integration
# ICP-B: data engineering, AI feature delivery, integration modules

_SVC_DOC = [
    "kyc", "aml", "claims", "underwriting", "invoice", "billing",
    "settlement", "reconciliation", "onboarding", "compliance reporting",
    "erp", "crm", "sharepoint", "document management",
]
_SVC_DATA = [
    "data pipeline", "ml pipeline", "etl", "elt", "data warehouse", "data lake",
    "vector database", "feature store", "data observability", "analytics foundation",
    "partner integration", "api integration",
]
_SVC_AI_FEATURE = [
    "copilot", "ai feature", "summarization", "classification", "recommendation",
    "knowledge assistant", "internal assistant", "rag",
]


def _score_service(row: dict):
    t = (_get(row, "description") + " " + _get(row, "Dự Án Gần Nhất")).lower()
    doc_hits = [k for k in _SVC_DOC if k in t]
    if doc_hits:
        return 10, f"Doc/compliance ops: {', '.join(doc_hits[:2])}"
    if _has(t, _SVC_AI_FEATURE):
        return 9, "AI feature delivery fit"
    if _has(t, _SVC_DATA):
        return 8, "Data/ML pipeline needs"
    if not t.strip():
        return 3, "No description — service fit unclear"
    return 5, "General fit — no specific ops signals"


# ── G. Decision Maker — 20 điểm ──────────────────────────────────────────────
# ICP-A buying committee: CIO/CTO, Head of Engineering, Head of Data/AI/DX, COO
# ICP-B buying committee: CTO/VP Eng, Head of Product, Head of Data/ML, EM/PM

def _score_dm(row: dict):
    title = _get(row, "job_title", "occupation").lower()
    if not title:
        return 5, "No title data (default)"

    # Tier 1 — 20pts: C-level tech / VP Engineering
    if _has(title, ["cto", "cio", "chief technology", "chief information",
                    "vp engineering", "vp of engineering", "vice president of engineering",
                    "head of engineering"]):
        return 20, f"C/VP tech: {title[:50]}"

    # Tier 2 — 18pts: Head of Data/AI/DX
    if _has(title, ["head of data", "head of ai", "head of digital transformation",
                    "head of digital", "chief data", "chief ai",
                    "director of data", "director of ai", "director of digital"]):
        return 18, f"Data/AI/DX lead: {title[:50]}"

    # Tier 3 — 16pts: Head of Product / Product Director
    if _has(title, ["head of product", "product director", "vp product",
                    "vp of product", "chief product"]):
        return 16, f"Product lead: {title[:50]}"

    # Tier 4 — 12pts: COO / Head of Operations (ICP-A)
    if _has(title, ["coo", "chief operating", "head of operations",
                    "operations director", "director of operations"]):
        return 12, f"Ops lead: {title[:50]}"

    # Tier 5 — 10pts: Engineering Manager / PM / Tech Lead (ICP-B champions)
    if _has(title, ["engineering manager", "product owner", "program manager",
                    "project manager", "tech lead", "technical lead"]):
        return 10, f"Manager/Lead: {title[:50]}"

    # Tier 6 — 8pts: Director / VP generic / Senior
    if _has(title, ["procurement", "vendor management"]):
        return 8, f"Procurement: {title[:50]}"
    if _has(title, ["director", "vp ", "vice president", "head "]):
        return 10, f"Director/VP: {title[:50]}"
    if _has(title, ["manager", "lead ", "senior"]):
        return 8, f"Senior/Manager: {title[:50]}"

    # Non-technical — 2pts
    if _has(title, ["business development", " hr ", "human resources",
                    "recruiter", "talent acquisition", "marketing", "sales"]):
        return 2, f"Non-technical: {title[:50]}"

    return 5, f"Unknown title: {title[:50]}"


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
    "bank", "insurance", "telco", "government", "mas ", "monetary authority",
    "microsoft", "google", "aws", "amazon", "salesforce", "sap", "oracle",
    "visa", "mastercard", "stripe", "grab", "sea group", "dbs", "ocbc", "uob",
]
_DISQUALIFIER_KW = [
    "freelancer", "marketplace contractor", "looking for freelancer",
    "no ai owner", "no budget", "pre-product",
]


def _bonus_penalty(row: dict):
    bonus   = 0
    penalty = 0

    # Bonus: enterprise / regulated partners (+3)
    partners = _get(row, "Đối Tác").lower()
    if _has(partners, _ENTERPRISE_PARTNERS):
        bonus += 3

    # Bonus: C-level employees visible (+2) — key_employees hoặc jobs
    jobs_text = _get(row, "jobs linked").lower()
    if _has(jobs_text, ["cto", "cio", "coo", "head of", "vp ", "director"]):
        bonus += 2

    # Penalty: missing critical data
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

    # Penalty: disqualifier signals
    all_text = (desc + " " + _get(row, "Dự Án Gần Nhất")).lower()
    if _has(all_text, _DISQUALIFIER_KW):
        penalty += 5

    return min(5, bonus), min(10, penalty)


# ── ICP Bucket ────────────────────────────────────────────────────────────────

def _icp_bucket(row: dict, size_n, geo_primary: bool, ai_e1: int, dm_pts: int,
                ind_label: str, type_pts: int) -> str:
    ind_t       = ind_label.lower()
    n           = size_n or 0
    is_a_ind    = _has(ind_t, _IND_A)
    is_b_ind    = not is_a_ind and _has(ind_t, _IND_B)
    is_end_user = type_pts >= 10  # not agency

    # ICP-A: Enterprise End-user AI Automation & DX
    # SG/HK primary, size >= 250, ICP-A industry, end-user, AI signals present
    if geo_primary and n >= 250 and is_a_ind and is_end_user and ai_e1 >= 8:
        return "Enterprise AI Automation (ICP-A)"

    # ICP-B: Tech/Fintech/SaaS building AI features
    # SG/HK primary, size 100-1000, ICP-B industry, has product, AI signals, tech DM
    if geo_primary and 100 <= n <= 1000 and is_b_ind and ai_e1 >= 8 and dm_pts >= 10:
        return "Tech AI Product Delivery (ICP-B)"

    # Relaxed ICP-A: secondary market but strong signals
    if not geo_primary and n >= 500 and is_a_ind and is_end_user and ai_e1 >= 8:
        return "Enterprise AI Automation (ICP-A)"

    return "Not ICP"


# ── Main ──────────────────────────────────────────────────────────────────────

def score_company(row: dict) -> ScoreResult:
    """Score một company row theo ICP barem (100 điểm)."""
    geo_pts,  geo_primary, geo_note   = _score_geo(row)
    size_pts, size_n, size_note       = _score_size(row)
    ind_pts,  ind_lbl, ind_note       = _score_industry(row)
    type_pts, type_note               = _score_type(row)
    ai_pts,   ai_e1, ai_note          = _score_ai(row)
    svc_pts,  svc_note                = _score_service(row)
    dm_pts,   dm_note                 = _score_dm(row)
    eng_pts,  eng_note                = _score_engagement(row)
    bonus,    penalty                 = _bonus_penalty(row)

    raw         = geo_pts + size_pts + ind_pts + type_pts + ai_pts + svc_pts + dm_pts + eng_pts
    score_total = max(0, min(100, raw + bonus - penalty))

    if   score_total >= 80: tier = "HOT"
    elif score_total >= 60: tier = "WARM"
    elif score_total >= 40: tier = "COLD"
    else:                   tier = "DROP"

    icp = _icp_bucket(row, size_n, geo_primary, ai_e1, dm_pts, ind_lbl, type_pts)

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