# From-Sheet Crawler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Thêm script `from_sheet.py` — đọc danh sách công ty từ Google Sheet, crawl website của từng công ty ra markdown, chạy DeepSeek extract lãnh đạo, rồi ghi kết quả enriched về sheet mới.

**Architecture:** Script độc lập `from_sheet.py` tái dùng `_crawl_company_pages` từ `main.py`, `DeepSeekExtractor` từ `src/deepseek_extractor.py`, và `save_to_sheet` từ `src/sheets_writer.py`. Thêm hàm `read_from_sheet()` vào `src/sheets_writer.py` để đọc dữ liệu sheet. Script nhận `--spreadsheet-id`, `--sheet-name`, `--col-website`, `--output-sheet` qua CLI.

**Tech Stack:** Python 3.11+, gspread, crawl4ai (`Crawl4AICrawler`), DeepSeek API (`DeepSeekExtractor`), argparse

---

### Task 1: Thêm hàm `read_from_sheet()` vào `src/sheets_writer.py`

**Files:**
- Modify: `src/sheets_writer.py`
- Test: `tests/test_sheets_writer.py` (tạo mới nếu chưa có)

**Step 1: Viết failing test**

```python
# tests/test_sheets_writer.py
from unittest.mock import patch, MagicMock
from src.sheets_writer import read_from_sheet

def test_read_from_sheet_returns_dicts():
    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = [
        {"Company Name": "Acme", "Website": "https://acme.com"},
        {"Company Name": "Beta", "Website": ""},
    ]
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_sheet
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    with patch("src.sheets_writer._get_client", return_value=mock_client):
        rows = read_from_sheet("fake_id", "Sheet1")

    assert len(rows) == 2
    assert rows[0]["Company Name"] == "Acme"
    assert rows[1]["Website"] == ""
```

**Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/test_sheets_writer.py::test_read_from_sheet_returns_dicts -v
```

Expected: `ImportError` hoặc `AttributeError` — hàm chưa tồn tại.

**Step 3: Implement `read_from_sheet()`**

Thêm vào cuối `src/sheets_writer.py`:

```python
def read_from_sheet(
    spreadsheet_id: str = SPREADSHEET_ID,
    sheet_name: str = "Sheet1",
) -> list[dict]:
    """Read all rows from a Google Sheet. Returns list of dicts (header as keys)."""
    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    sheet = spreadsheet.worksheet(sheet_name)
    return sheet.get_all_records()
```

**Step 4: Chạy lại test**

```bash
pytest tests/test_sheets_writer.py::test_read_from_sheet_returns_dicts -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/sheets_writer.py tests/test_sheets_writer.py
git commit -m "feat: add read_from_sheet() to sheets_writer"
```

---

### Task 2: Tạo `from_sheet.py` — CLI script chính

**Files:**
- Create: `from_sheet.py`

**Step 1: Viết failing test**

```python
# tests/test_from_sheet.py
import pytest
from unittest.mock import patch, MagicMock

def test_parse_args_requires_no_positional():
    """Script có thể import và parse args mà không crash."""
    import importlib, sys
    # Giả lập sys.argv
    sys.argv = [
        "from_sheet.py",
        "--spreadsheet-id", "abc123",
        "--sheet-name", "Sheet1",
        "--col-website", "Website",
        "--output-sheet", "Enriched",
    ]
    import from_sheet
    args = from_sheet.parse_args()
    assert args.spreadsheet_id == "abc123"
    assert args.sheet_name == "Sheet1"
    assert args.col_website == "Website"
    assert args.output_sheet == "Enriched"
```

**Step 2: Chạy test để xác nhận FAIL**

```bash
pytest tests/test_from_sheet.py::test_parse_args_requires_no_positional -v
```

Expected: `ModuleNotFoundError: No module named 'from_sheet'`

**Step 3: Implement `from_sheet.py`**

```python
# from_sheet.py
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from src.sheets_writer import read_from_sheet, save_to_sheet
from src.crawl4ai_crawler import Crawl4AICrawler
from src.website_crawler import WebsiteCrawler
from src.deepseek_extractor import DeepSeekExtractor

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read companies from Google Sheet → crawl → DeepSeek → write back"
    )
    parser.add_argument("--spreadsheet-id", required=True, help="Google Spreadsheet ID")
    parser.add_argument("--sheet-name", default="Sheet1", help="Source tab name (default: Sheet1)")
    parser.add_argument("--col-website", default="Website", help="Column header for website URL (default: Website)")
    parser.add_argument("--col-name", default="Company Name", help="Column header for company name (default: Company Name)")
    parser.add_argument("--output-sheet", default="Enriched", help="Tab name to write results (default: Enriched)")
    parser.add_argument("--output-spreadsheet-id", default=None,
                        help="Spreadsheet ID for output (default: same as input)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay in seconds between companies (default: 1.0)")
    return parser.parse_args()


def build_extractor() -> DeepSeekExtractor:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set. Add it to your .env file.")
        sys.exit(1)
    return DeepSeekExtractor(api_key=api_key)


def enrich_company(row: dict, col_website: str, col_name: str,
                   crawler: Crawl4AICrawler, helper: WebsiteCrawler,
                   extractor: DeepSeekExtractor) -> dict:
    """Crawl website + DeepSeek extract. Returns updated row dict."""
    from main import _crawl_company_pages

    website = row.get(col_website, "").strip()
    name = row.get(col_name, "Unknown")

    if not website:
        print(f"  Skipping '{name}' — no website")
        return row

    print(f"  Crawling '{name}' ({website})...")
    result = _crawl_company_pages(website, crawler, helper, extractor)

    leaders = result.get("leaders") or []
    socials = result.get("socials") or {}

    # Ghi lãnh đạo đầu tiên vào row (giữ nguyên các cột cũ)
    updated = dict(row)
    updated["leaders"] = leaders
    updated["socials"] = socials

    if leaders:
        print(f"    Found {len(leaders)} leader(s): {[l['name'] for l in leaders]}")
    if socials:
        print(f"    Socials: {list(socials.keys())}")

    return updated


def main():
    args = parse_args()

    print(f"Reading from sheet '{args.sheet_name}' (ID: {args.spreadsheet_id})...")
    rows = read_from_sheet(
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
    )
    print(f"Found {len(rows)} row(s).")

    if not rows:
        print("No data found. Exiting.")
        return

    crawler = Crawl4AICrawler()
    helper = WebsiteCrawler()
    extractor = build_extractor()

    enriched = []
    for i, row in enumerate(rows, 1):
        print(f"\n[{i}/{len(rows)}]", end=" ")
        updated = enrich_company(
            row=row,
            col_website=args.col_website,
            col_name=args.col_name,
            crawler=crawler,
            helper=helper,
            extractor=extractor,
        )
        enriched.append(updated)
        time.sleep(args.delay)

    out_id = args.output_spreadsheet_id or args.spreadsheet_id
    print(f"\nWriting {len(enriched)} enriched row(s) to sheet '{args.output_sheet}'...")
    url = save_to_sheet(
        companies=enriched,
        sheet_name=args.output_sheet,
        spreadsheet_id=out_id,
    )
    print(f"\nDone! Results at: {url}")


if __name__ == "__main__":
    main()
```

**Step 4: Chạy test**

```bash
pytest tests/test_from_sheet.py::test_parse_args_requires_no_positional -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add from_sheet.py tests/test_from_sheet.py
git commit -m "feat: add from_sheet.py — read sheet → crawl → deepseek → write back"
```

---

### Task 3: Smoke test thực tế (manual)

> Bước này không tự động, cần chạy tay với sheet thật.

**Step 1: Chuẩn bị sheet test**

Tạo 1 Google Sheet với ít nhất 2 cột: `Company Name`, `Website`.  
Thêm 2–3 dòng công ty có website thật.

**Step 2: Chạy lệnh**

```bash
python from_sheet.py \
  --spreadsheet-id "1PW5LnQyXjyl0h16ooufYNYjR1_eb8DgfnCEGLNjsf10" \
  --sheet-name "Sheet1" \
  --col-website "Website" \
  --output-sheet "Enriched"
```

**Step 3: Kiểm tra kết quả**

- Tab `Enriched` được tạo trong cùng spreadsheet
- Mỗi công ty có thêm thông tin lãnh đạo, social links
- Log in terminal hiển thị tên lãnh đạo tìm được

**Step 4: Commit nếu cần fix nhỏ**

```bash
git add .
git commit -m "fix: adjust from_sheet.py based on smoke test"
```

---

## Lệnh chạy sau khi hoàn thành

```bash
# Dùng cùng spreadsheet, đọc Sheet1, ghi ra tab "Enriched"
python from_sheet.py \
  --spreadsheet-id "YOUR_SHEET_ID" \
  --sheet-name "Sheet1" \
  --col-website "Website" \
  --output-sheet "Enriched"

# Ghi sang spreadsheet khác
python from_sheet.py \
  --spreadsheet-id "SOURCE_ID" \
  --output-spreadsheet-id "DEST_ID" \
  --sheet-name "RawData" \
  --output-sheet "Enriched" \
  --delay 2.0
```
