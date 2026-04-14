# From-Sheet Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Script `from_sheet.py` đọc danh sách công ty từ Google Sheet (ID: `19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E`, GID: `1566842879`), crawl website của từng công ty ra markdown, dùng DeepSeek trích xuất 5 trường thông tin mới (tuyển dụng, blog, lĩnh vực, dự án gần nhất, đối tác), rồi ghi kết quả enriched vào tab mới "Enriched" trong cùng spreadsheet.

**Sheet columns thực tế:**
- Cột tên công ty: `company_name` (cột A)
- Cột website: `website` (cột K — chứa URL như http://emurgo.io)
- Tab nguồn mở bằng GID: `1566842879` (dùng `--gid` flag thay vì `--sheet-name`)

**Architecture:** 3 lớp độc lập — `src/company_profile_extractor.py` (DeepSeek prompt cho 5 trường mới), `src/sheets_writer.py` thêm 2 hàm (`read_from_sheet`, `write_enriched_sheet`), và `from_sheet.py` là CLI orchestrator gọi đúng thứ tự: read → crawl → extract → write. Tab output là "Enriched" (tạo mới, không ghi đè dữ liệu gốc).

**Tech Stack:** Python 3.11+, gspread, crawl4ai (`Crawl4AICrawler`), DeepSeek API (openai-compatible), argparse, python-dotenv

---

## Tổng quan luồng dữ liệu

```
Google Sheet (tab nguồn)
    │  read_from_sheet() → list[dict]  (mỗi dict = 1 hàng, key = header)
    ▼
Lọc các hàng có cột "website" không rỗng
    │
    ▼ (mỗi công ty)
_crawl_company_pages(website, crawler, helper, extractor=None)
    → {"markdown": str, "leaders": list, "socials": dict}
    │
    ▼
CompanyProfileExtractor.extract(markdown)
    → {"tuyen_dung": str, "blog": str, "linh_vuc": str,
       "du_an_gan_nhat": str, "doi_tac": str}
    │
    ▼
Merge vào dict gốc của hàng → enriched_row
    │
write_enriched_sheet(enriched_rows, spreadsheet_id, sheet_name="Enriched")
    → URL sheet kết quả
```

---

### Task 1: Tạo `src/company_profile_extractor.py`

**Files:**
- Create: `src/company_profile_extractor.py`
- Test: `tests/test_company_profile_extractor.py`

**Step 1: Viết failing test**

```python
# tests/test_company_profile_extractor.py
from src.company_profile_extractor import CompanyProfileExtractor

def test_extract_returns_five_keys():
    """Kết quả luôn có đủ 5 key dù không tìm thấy gì."""
    extractor = CompanyProfileExtractor.__new__(CompanyProfileExtractor)
    result = extractor._parse("[]")
    assert set(result.keys()) == {"tuyen_dung", "blog", "linh_vuc", "du_an_gan_nhat", "doi_tac"}

def test_parse_valid_json():
    extractor = CompanyProfileExtractor.__new__(CompanyProfileExtractor)
    raw = '''
    {
      "tuyen_dung": "Tuyển Senior Backend",
      "blog": "https://company.com/blog",
      "linh_vuc": "Fintech, Payments",
      "du_an_gan_nhat": "Dự án ABC cho VCB",
      "doi_tac": "Vietcombank, NAPAS"
    }
    '''
    result = extractor._parse(raw)
    assert result["tuyen_dung"] == "Tuyển Senior Backend"
    assert result["linh_vuc"] == "Fintech, Payments"
    assert result["doi_tac"] == "Vietcombank, NAPAS"

def test_parse_invalid_json_returns_empty_strings():
    extractor = CompanyProfileExtractor.__new__(CompanyProfileExtractor)
    result = extractor._parse("không phải json")
    assert result["tuyen_dung"] == ""
    assert result["blog"] == ""
```

**Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/test_company_profile_extractor.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.company_profile_extractor'`

**Step 3: Implement `CompanyProfileExtractor`**

```python
# src/company_profile_extractor.py
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

- "tuyen_dung": Thông tin tuyển dụng hiện tại — vị trí đang tuyển, link trang careers nếu có. \
Nếu không có: "".
- "blog": Link trang blog hoặc news của công ty, hoặc tiêu đề + link bài viết gần nhất nếu tìm được. \
Nếu không có: "".
- "linh_vuc": Lĩnh vực hoạt động chính của công ty (ngắn gọn, cách nhau bằng dấu phẩy). \
Ví dụ: "Fintech, Payment, B2B SaaS".
- "du_an_gan_nhat": Tên và mô tả ngắn dự án/sản phẩm gần đây nhất được đề cập. Nếu không có: "".
- "doi_tac": Danh sách đối tác hoặc khách hàng nổi bật được nhắc đến (cách nhau bằng dấu phẩy). \
Nếu không có: "".

Chỉ trả về JSON, không giải thích thêm. Ví dụ:
{{
  "tuyen_dung": "Tuyển Senior Backend Engineer — https://company.com/careers",
  "blog": "https://company.com/blog — Bài gần nhất: 'Ra mắt sản phẩm X'",
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
```

**Step 4: Chạy lại test**

```bash
pytest tests/test_company_profile_extractor.py -v
```

Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add src/company_profile_extractor.py tests/test_company_profile_extractor.py
git commit -m "feat: add CompanyProfileExtractor — deepseek extract 5 profile fields"
```

---

### Task 2: Thêm `read_from_sheet()` và `write_enriched_sheet()` vào `src/sheets_writer.py`

**Files:**
- Modify: `src/sheets_writer.py` (thêm vào cuối file)
- Test: `tests/test_sheets_writer_read_write.py`

**Step 1: Viết failing test**

```python
# tests/test_sheets_writer_read_write.py
from unittest.mock import patch, MagicMock
from src.sheets_writer import read_from_sheet, write_enriched_sheet

def _mock_client(records=None, headers=None):
    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = records or []
    mock_sheet.row_values.return_value = headers or []
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_sheet
    mock_spreadsheet.add_worksheet.return_value = mock_sheet
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet
    return mock_client, mock_sheet

def test_read_from_sheet_returns_records():
    records = [{"Company Name": "Acme", "Website": "https://acme.com"}]
    client, _ = _mock_client(records=records)
    with patch("src.sheets_writer._get_client", return_value=client):
        result = read_from_sheet("fake_id", "Sheet1")
    assert result == records

def test_write_enriched_sheet_calls_update():
    client, mock_sheet = _mock_client()
    rows = [
        {
            "Company Name": "Acme", "Website": "https://acme.com",
            "tuyen_dung": "Tuyển BE", "blog": "", "linh_vuc": "Fintech",
            "du_an_gan_nhat": "", "doi_tac": "VCB",
        }
    ]
    with patch("src.sheets_writer._get_client", return_value=client):
        write_enriched_sheet(rows, "fake_id", "Enriched")
    mock_sheet.update.assert_called_once()
```

**Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/test_sheets_writer_read_write.py -v
```

Expected: `ImportError` — `read_from_sheet`, `write_enriched_sheet` chưa tồn tại.

**Step 3: Thêm 2 hàm vào cuối `src/sheets_writer.py`**

```python
# Thêm vào cuối src/sheets_writer.py

ENRICHED_EXTRA_HEADERS = [
    "Tuyển Dụng", "Blog", "Lĩnh Vực", "Dự Án Gần Nhất", "Đối Tác",
]

ENRICHED_EXTRA_KEYS = [
    "tuyen_dung", "blog", "linh_vuc", "du_an_gan_nhat", "doi_tac",
]


def read_from_sheet(
    spreadsheet_id: str = SPREADSHEET_ID,
    sheet_name: str | None = None,
    gid: int | None = None,
) -> list[dict]:
    """Read all rows from a Google Sheet tab.
    Opens by gid (numeric tab id) if provided, else by sheet_name.
    Returns list of dicts (header row as keys).
    """
    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    if gid is not None:
        sheet = spreadsheet.get_worksheet_by_id(gid)
    else:
        sheet = spreadsheet.worksheet(sheet_name or "Sheet1")
    return sheet.get_all_records()


def write_enriched_sheet(
    enriched_rows: list[dict],
    spreadsheet_id: str = SPREADSHEET_ID,
    sheet_name: str = "Enriched",
) -> str:
    """Write enriched rows (original cols + 5 new profile cols) to a sheet tab.
    Detects original column order from the first row's keys.
    Returns the sheet URL.
    """
    if not enriched_rows:
        print("  [Sheets] No rows to write.")
        return ""

    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    try:
        sheet = spreadsheet.worksheet(sheet_name)
        sheet.clear()
    except Exception:
        sheet = spreadsheet.add_worksheet(
            title=sheet_name, rows=len(enriched_rows) + 10, cols=40
        )

    # Build header: original keys (minus extra keys) + extra headers
    original_keys = [
        k for k in enriched_rows[0].keys()
        if k not in ENRICHED_EXTRA_KEYS and k not in ("leaders", "socials")
    ]
    all_headers = original_keys + ENRICHED_EXTRA_HEADERS

    def make_row(row: dict) -> list:
        original_vals = [str(row.get(k, "") or "") for k in original_keys]
        extra_vals = [str(row.get(k, "") or "") for k in ENRICHED_EXTRA_KEYS]
        return original_vals + extra_vals

    data = [all_headers] + [make_row(r) for r in enriched_rows]
    sheet.update(data, "A1")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet.id}"
    print(f"  [Sheets] Written {len(enriched_rows)} row(s) to '{sheet_name}'")
    print(f"  [Sheets] {url}")
    return url
```

**Step 4: Chạy lại test**

```bash
pytest tests/test_sheets_writer_read_write.py -v
```

Expected: 2 tests PASS

**Step 5: Commit**

```bash
git add src/sheets_writer.py tests/test_sheets_writer_read_write.py
git commit -m "feat: add read_from_sheet and write_enriched_sheet to sheets_writer"
```

---

### Task 3: Tạo `from_sheet.py` — CLI orchestrator

**Files:**
- Create: `from_sheet.py`
- Test: `tests/test_from_sheet.py`

**Step 1: Viết failing test**

```python
# tests/test_from_sheet.py
import sys
from unittest.mock import patch, MagicMock

def _set_argv(*args):
    sys.argv = ["from_sheet.py", "--spreadsheet-id", "abc123"] + list(args)

def test_parse_args_defaults():
    _set_argv()
    import importlib
    import from_sheet
    importlib.reload(from_sheet)
    args = from_sheet.parse_args()
    assert args.spreadsheet_id == "abc123"
    assert args.sheet_name == "Sheet1"
    assert args.col_website == "Website"
    assert args.output_sheet == "Enriched"
    assert args.delay == 1.0

def test_parse_args_custom():
    _set_argv("--sheet-name", "RawData", "--output-sheet", "Done", "--delay", "2.5")
    import from_sheet
    import importlib
    importlib.reload(from_sheet)
    args = from_sheet.parse_args()
    assert args.sheet_name == "RawData"
    assert args.output_sheet == "Done"
    assert args.delay == 2.5
```

**Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/test_from_sheet.py -v
```

Expected: `ModuleNotFoundError: No module named 'from_sheet'`

**Step 3: Implement `from_sheet.py`**

```python
# from_sheet.py
"""
Đọc danh sách công ty từ Google Sheet → crawl website → DeepSeek extract
5 trường profile → ghi kết quả vào tab mới trong cùng spreadsheet.

Cách dùng:
    python from_sheet.py --spreadsheet-id SHEET_ID [OPTIONS]

Xem thêm: docs/commands/from-sheet-commands.md
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sheet → crawl → DeepSeek extract → write enriched sheet"
    )
    parser.add_argument(
        "--spreadsheet-id", required=True,
        help="Google Spreadsheet ID (từ URL: /spreadsheets/d/<ID>/)"
    )
    parser.add_argument(
        "--sheet-name", default=None,
        help="Tên tab nguồn (dùng thay --gid nếu biết tên tab)"
    )
    parser.add_argument(
        "--gid", type=int, default=None,
        help="GID số của tab nguồn — lấy từ URL #gid=<số> (ưu tiên hơn --sheet-name)"
    )
    parser.add_argument(
        "--col-website", default="website",
        help="Tên cột chứa URL website (default: website)"
    )
    parser.add_argument(
        "--col-name", default="company_name",
        help="Tên cột chứa tên công ty (default: company_name)"
    )
    parser.add_argument(
        "--output-sheet", default="Enriched",
        help="Tên tab output trong cùng spreadsheet (default: Enriched)"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Số giây nghỉ giữa các công ty (default: 1.0)"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Chỉ xử lý N hàng đầu (0 = tất cả, default: 0)"
    )
    return parser.parse_args()


def _build_profile_extractor():
    from src.company_profile_extractor import CompanyProfileExtractor
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)
    return CompanyProfileExtractor(api_key=api_key)


def _crawl_and_extract(
    company_name: str,
    website: str,
    profile_extractor,
) -> dict:
    """Crawl website → markdown → extract 5 profile fields. Returns dict of 5 keys."""
    from src.crawl4ai_crawler import Crawl4AICrawler
    from src.website_crawler import WebsiteCrawler
    from src.browser_fetcher import fetch_html
    from main import _crawl_company_pages

    crawler = Crawl4AICrawler()
    helper = WebsiteCrawler()

    print(f"  Crawling {website} ...")
    try:
        result = _crawl_company_pages(website, crawler, helper, extractor=None)
        markdown = result.get("markdown", "")
    except Exception as e:
        print(f"  [ERROR] Crawl failed: {e}")
        markdown = ""

    if not markdown:
        print(f"  [WARN] Empty markdown for {company_name}")
        return {"tuyen_dung": "", "blog": "", "linh_vuc": "", "du_an_gan_nhat": "", "doi_tac": ""}

    print(f"  Extracting profile info ({len(markdown)} chars) ...")
    profile = profile_extractor.extract(markdown)

    # Log kết quả ngắn
    for key, val in profile.items():
        if val:
            preview = val[:80].replace("\n", " ")
            print(f"    {key}: {preview}")

    return profile


def main():
    args = parse_args()

    from src.sheets_writer import read_from_sheet, write_enriched_sheet

    # 1. Đọc sheet
    tab_desc = f"gid={args.gid}" if args.gid else f"sheet='{args.sheet_name}'"
    print(f"Reading [{tab_desc}] from spreadsheet {args.spreadsheet_id} ...")
    rows = read_from_sheet(
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )
    print(f"Found {len(rows)} row(s).")

    if not rows:
        print("No data. Exiting.")
        return

    if args.limit > 0:
        rows = rows[: args.limit]
        print(f"Processing first {args.limit} row(s) only (--limit).")

    # 2. Build extractor
    profile_extractor = _build_profile_extractor()

    # 3. Crawl + extract từng công ty
    enriched = []
    for i, row in enumerate(rows, 1):
        name = row.get(args.col_name, "") or f"Row {i}"
        website = (row.get(args.col_website, "") or "").strip()

        print(f"\n[{i}/{len(rows)}] {name}")

        if not website:
            print(f"  Skipping — no website in column '{args.col_website}'")
            enriched.append(row)
            continue

        profile = _crawl_and_extract(name, website, profile_extractor)

        enriched_row = dict(row)
        enriched_row.update(profile)
        enriched.append(enriched_row)

        if i < len(rows):
            time.sleep(args.delay)

    # 4. Ghi kết quả
    print(f"\nWriting {len(enriched)} enriched row(s) to tab '{args.output_sheet}' ...")
    url = write_enriched_sheet(
        enriched_rows=enriched,
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.output_sheet,
    )

    print(f"\nDone! View results at:\n  {url}")


if __name__ == "__main__":
    main()
```

**Step 4: Chạy test**

```bash
pytest tests/test_from_sheet.py -v
```

Expected: 2 tests PASS

**Step 5: Commit**

```bash
git add from_sheet.py tests/test_from_sheet.py
git commit -m "feat: add from_sheet.py — sheet → crawl → deepseek → enriched sheet"
```

---

### Task 4: Viết file commands reference

**Files:**
- Create: `docs/commands/from-sheet-commands.md`

**Step 1: Tạo thư mục nếu chưa có**

```bash
mkdir -p docs/commands
```

**Step 2: Tạo file**

```markdown
# from_sheet.py — Command Reference

Script đọc danh sách công ty từ Google Sheet, crawl website, trích xuất
5 trường thông tin bằng DeepSeek AI, rồi ghi kết quả vào tab "Enriched"
trong cùng spreadsheet.

## Yêu cầu môi trường (.env)

```env
DEEPSEEK_API_KEY=sk-...

# Google Sheets — chọn 1 trong 2:
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service_account.json
# hoặc OAuth2 (sẽ mở trình duyệt lần đầu):
GOOGLE_OAUTH_CLIENT_SECRET=client_secret.json
```

## Cột bắt buộc trong sheet nguồn

| Cột | Mô tả |
|-----|-------|
| `Company Name` | Tên công ty (dùng để log) |
| `Website` | URL website đầy đủ (https://...) |

Tên cột có thể tùy chỉnh bằng `--col-name` và `--col-website`.

## Các cột được thêm vào sheet Enriched

| Cột mới | Key DeepSeek | Mô tả |
|---------|-------------|-------|
| Tuyển Dụng | `tuyen_dung` | Vị trí đang tuyển, link careers |
| Blog | `blog` | Link trang blog / bài viết gần nhất |
| Lĩnh Vực | `linh_vuc` | Lĩnh vực hoạt động chính |
| Dự Án Gần Nhất | `du_an_gan_nhat` | Tên + mô tả ngắn dự án/sản phẩm gần nhất |
| Đối Tác | `doi_tac` | Danh sách đối tác / khách hàng nổi bật |

## Lệnh thường dùng

### Sheet thực tế — dùng GID (khuyến nghị)

```bash
# Spreadsheet ID: 19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E
# GID của tab nguồn: 1566842879 (lấy từ URL #gid=1566842879)

python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --gid 1566842879 \
  --output-sheet "Enriched"
```

### Test nhanh 3 hàng đầu

```bash
python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --gid 1566842879 \
  --limit 3
```

### Chỉ định tab theo tên (nếu biết tên tab)

```bash
python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --sheet-name "Sheet1" \
  --output-sheet "Enriched_Apr2026"
```

### Tên cột khác với mặc định

```bash
python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --gid 1566842879 \
  --col-website "website" \
  --col-name "company_name" \
  --delay 3.0
```

## Cách lấy Spreadsheet ID

Từ URL Google Sheet:
```
https://docs.google.com/spreadsheets/d/1PW5LnQyXjyl0h16ooufYNYjR1_eb8DgfnCEGLNjsf10/edit
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       đây là spreadsheet ID
```

## Tất cả flags

| Flag | Mặc định | Mô tả |
|------|----------|-------|
| `--spreadsheet-id` | bắt buộc | ID của Google Spreadsheet |
| `--gid` | — | GID số của tab (từ URL `#gid=<số>`) — ưu tiên hơn `--sheet-name` |
| `--sheet-name` | — | Tên tab nguồn (dùng nếu không có `--gid`) |
| `--col-website` | `website` | Tên cột chứa URL website |
| `--col-name` | `company_name` | Tên cột chứa tên công ty |
| `--output-sheet` | `Enriched` | Tab output trong cùng spreadsheet |
| `--delay` | `1.0` | Delay (giây) giữa các công ty |
| `--limit` | `0` (tất cả) | Chỉ xử lý N hàng đầu |
```

**Step 3: Commit**

```bash
git add docs/commands/from-sheet-commands.md
git commit -m "docs: add from-sheet-commands.md with full CLI reference"
```

---

## Tóm tắt thứ tự implement

1. `src/company_profile_extractor.py` + test → commit
2. `src/sheets_writer.py` thêm 2 hàm + test → commit
3. `from_sheet.py` + test → commit
4. `docs/commands/from-sheet-commands.md` → commit

## Kiểm tra tổng thể sau khi xong

```bash
pytest tests/test_company_profile_extractor.py tests/test_sheets_writer_read_write.py tests/test_from_sheet.py -v
```

Expected: tất cả PASS
