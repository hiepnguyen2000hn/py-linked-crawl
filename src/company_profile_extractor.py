import json
import os
import re
from openai import OpenAI

DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_SYSTEM = (
    "You are a precise business intelligence assistant. "
    "Extract specific company information from website content and return ONLY valid JSON."
)

_USER_TEMPLATE = """\
Đọc nội dung website công ty bên dưới và trích xuất các thông tin sau.
Trả về ONLY một JSON object với đúng 5 key sau:

- "tuyen_dung": Danh sách tên các vị trí đang tuyển dụng hiện tại, mỗi vị trí 1 dòng dùng ký hiệu •. \
KHÔNG lấy URL hay link. Chỉ lấy tên công việc. Nếu không có: "".
- "blog": Tóm tắt 3 bài viết/tin tức gần nhất tìm được trong nội dung, mỗi bài 1 dòng dùng ký hiệu •, \
chỉ lấy text tóm tắt nội dung, không lấy URL. QUAN TRỌNG: giữ nguyên ngôn ngữ gốc của bài viết, KHÔNG dịch sang ngôn ngữ khác. \
Nếu không có: "".
- "linh_vuc": Lĩnh vực hoạt động chính của công ty (ngắn gọn, cách nhau bằng dấu phẩy). \
Ví dụ: "Fintech, Payment, B2B SaaS".
- "du_an_gan_nhat": Tên và mô tả ngắn dự án/sản phẩm gần đây nhất được đề cập. Nếu không có: "".
- "doi_tac": Danh sách đối tác hoặc khách hàng nổi bật được nhắc đến (cách nhau bằng dấu phẩy). \
Nếu không có: "".

Chỉ trả về JSON, không giải thích thêm. Ví dụ:
{{
  "tuyen_dung": "• Senior Backend Engineer\n• Product Manager\n• DevOps Engineer",
  "blog": "• Ra mắt sản phẩm X hỗ trợ thanh toán QR\n• Công ty đạt chứng chỉ ISO 27001\n• Hợp tác chiến lược với VNPT",
  "linh_vuc": "E-commerce, Logistics Technology",
  "du_an_gan_nhat": "Hệ thống quản lý kho ABC triển khai Q1 2026",
  "doi_tac": "Vietcombank, VNPT, FPT"
}}

Nội dung website:
{text}"""

_EMPTY = {
    "tuyen_dung": "",
    "blog": "",
    "linh_vuc": "",
    "du_an_gan_nhat": "",
    "doi_tac": "",
}


class CompanyProfileExtractor:
    """DeepSeek-based extractor for 5 company profile fields."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not set. Add it to your .env file.")
        self._client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def extract(self, text: str) -> dict:
        """Extract 5 profile fields from markdown text. Always returns all 5 keys."""
        if not text or not text.strip():
            return dict(_EMPTY)
        truncated = text[:30000]
        try:
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
        except Exception as e:
            print(f"    [ProfileExtractor] API error: {e}")
            return dict(_EMPTY)

    def _parse(self, text: str) -> dict:
        result = dict(_EMPTY)
        try:
            match = re.search(r"\{.*?\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                for key in _EMPTY:
                    if key in data and isinstance(data[key], str):
                        result[key] = data[key].strip()
        except Exception:
            pass
        return result
