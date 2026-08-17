"""
ICP Scorer — chấm điểm Ideal Customer Profile cho từng lead.

Tiêu chí chấm (tổng 100 điểm):
  - Seniority / quyền quyết định  : 30 pts
  - Độ phù hợp ngành              : 25 pts
  - Quy mô công ty                : 20 pts
  - Mức độ hoạt động LinkedIn     : 15 pts
  - Tín hiệu mua (buying signals) : 10 pts

Output per lead:
  {
    "icp_score": 0-100,
    "tier":      "A" | "B" | "C" | "D",
    "reasons":   "...",   # 1-2 câu giải thích
    "priority":  "High" | "Medium" | "Low"
  }
"""
import os
import json


# ── ICP Config (tuỳ chỉnh theo từng business) ───────────────────────────────

DEFAULT_ICP_CONFIG = {
    "target_industries": [
        "technology", "software", "IT services", "fintech", "e-commerce",
        "digital marketing", "startup", "SaaS", "AI", "công nghệ",
        "phần mềm", "thương mại điện tử", "tài chính",
    ],
    "target_titles": [
        "CEO", "CTO", "CPO", "Founder", "Co-founder", "Director", "VP",
        "Head of", "Manager", "Lead", "Giám đốc", "Trưởng phòng",
    ],
    "target_company_sizes": ["11-50", "51-200", "201-500", "501-1000", "1000+"],
    "buying_signals": [
        "hiring", "tuyển dụng", "expanding", "mở rộng", "digital transformation",
        "chuyển đổi số", "funding", "gọi vốn", "series A", "series B",
        "new product", "sản phẩm mới", "partnership", "hợp tác",
    ],
}


SCORE_PROMPT = """Bạn là chuyên gia sales B2B. Chấm điểm ICP (Ideal Customer Profile) cho lead sau.

=== ICP Config của chúng tôi ===
Ngành mục tiêu: {target_industries}
Chức vụ mục tiêu: {target_titles}
Quy mô công ty: {target_company_sizes}
Tín hiệu mua: {buying_signals}

=== Thông tin Lead ===
Tên: {name}
Chức vụ: {title}
Công ty: {company}
Ngành: {industry}
Quy mô công ty: {company_size}
Bài viết gần nhất: {recent_post}
Mô tả LinkedIn: {about}

=== Yêu cầu ===
Chấm điểm từ 0-100 theo tiêu chí:
1. Seniority/quyền quyết định (0-30): C-level/Founder=28-30, Director/VP=22-27, Manager=12-18, Individual=0-8
2. Độ phù hợp ngành (0-25): Đúng ngành=22-25, Gần ngành=12-18, Không phù hợp=0-8
3. Quy mô công ty (0-20): Phù hợp target=18-20, Gần=10-15, Không phù hợp=0-8
4. Hoạt động LinkedIn (0-15): Post gần đây + engagement cao=13-15, Còn active=7-10, Không active=0-4
5. Buying signals (0-10): Có tín hiệu rõ=8-10, Tín hiệu yếu=4-6, Không có=0-2

Trả về JSON đúng format sau (không markdown, không giải thích ngoài JSON):
{{
  "icp_score": <số nguyên 0-100>,
  "tier": "<A nếu >=75, B nếu 50-74, C nếu 30-49, D nếu <30>",
  "priority": "<High nếu tier A/B, Medium nếu tier C, Low nếu tier D>",
  "score_breakdown": {{
    "seniority": <0-30>,
    "industry_fit": <0-25>,
    "company_size": <0-20>,
    "linkedin_activity": <0-15>,
    "buying_signals": <0-10>
  }},
  "reasons": "<1-2 câu tóm tắt điểm mạnh và điểm yếu của lead này>",
  "suggested_approach": "<1 câu gợi ý cách tiếp cận phù hợp nhất>"
}}"""


class ICPScorer:
    def __init__(self, api_key: str | None = None, icp_config: dict | None = None,
                 ai_router=None):
        """
        ai_router: AIRouter instance (multi-provider). Nếu None, dùng DeepSeek mặc định.
        """
        self.config = icp_config or DEFAULT_ICP_CONFIG
        if ai_router:
            self._router = ai_router
        else:
            from src.providers.ai_providers import AIRouter, DeepSeekProvider
            self._router = AIRouter([DeepSeekProvider(api_key or os.getenv("DEEPSEEK_API_KEY", ""))])

    def score_lead(self, lead: dict) -> dict:
        """
        Chấm điểm 1 lead.
        lead dict keys: name, title, company, industry, company_size, recent_post, about
        """
        prompt = SCORE_PROMPT.format(
            target_industries=", ".join(self.config["target_industries"][:8]),
            target_titles=", ".join(self.config["target_titles"][:8]),
            target_company_sizes=", ".join(self.config["target_company_sizes"]),
            buying_signals=", ".join(self.config["buying_signals"][:8]),
            name=lead.get("name", "N/A"),
            title=lead.get("title", "N/A"),
            company=lead.get("company", "N/A"),
            industry=lead.get("industry", "N/A"),
            company_size=lead.get("company_size", "N/A"),
            recent_post=(lead.get("recent_post", "") or "")[:500],
            about=(lead.get("about", "") or "")[:300],
        )

        try:
            result = self._router.complete_json(prompt, temperature=0.2, max_tokens=600)
            if not result:
                raise ValueError("No JSON response from AI router")
            return {
                "icp_score":          int(result.get("icp_score", 0)),
                "tier":               result.get("tier", "D"),
                "priority":           result.get("priority", "Low"),
                "score_breakdown":    result.get("score_breakdown", {}),
                "reasons":            result.get("reasons", ""),
                "suggested_approach": result.get("suggested_approach", ""),
                "ok": True,
            }
        except Exception as e:
            print(f"[icp-scorer] Error for {lead.get('name')}: {e}")
            return {"icp_score": 0, "tier": "D", "priority": "Low", "reasons": "", "ok": False, "error": str(e)}

    def score_batch(self, leads: list[dict], on_progress=None) -> list[dict]:
        """Chấm điểm danh sách leads, trả về list kết quả."""
        results = []
        for i, lead in enumerate(leads):
            result = self.score_lead(lead)
            result["index"] = lead.get("index", i)
            result["name"]  = lead.get("name", "")
            results.append(result)
            score = result.get("icp_score", 0)
            tier  = result.get("tier", "?")
            print(f"[icp-scorer] [{i+1}/{len(leads)}] {lead.get('name', '?')} → {score}/100 (Tier {tier})")
            if on_progress:
                on_progress(i + 1, len(leads), result)
        return results
