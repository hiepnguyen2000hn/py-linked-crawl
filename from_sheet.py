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

    for key, val in profile.items():
        if val:
            preview = val[:80].replace("\n", " ")
            print(f"    {key}: {preview}")

    return profile


def main():
    args = parse_args()

    from src.sheets_writer import read_from_sheet, update_sheet_with_extra_cols

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

    # 4. Ghi kết quả ngược lại tab nguồn (thêm cột, không tạo tab mới)
    tab_desc = f"gid={args.gid}" if args.gid else f"sheet='{args.sheet_name}'"
    print(f"\nWriting {len(enriched)} enriched row(s) back to source tab [{tab_desc}] ...")
    url = update_sheet_with_extra_cols(
        enriched_rows=enriched,
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )

    print(f"\nDone! View results at:\n  {url}")


if __name__ == "__main__":
    main()
