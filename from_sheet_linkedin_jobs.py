"""
Đọc linkedin_url (công ty) từ Google Sheet → crawl trang /jobs/ → lấy tất cả job đang tuyển
→ ghi vào cột "tuyển d" trong cùng tab. ZERO token — không dùng LLM.

Cách dùng:
    python from_sheet_linkedin_jobs.py --spreadsheet-id SHEET_ID --gid 0

Ví dụ:
    python from_sheet_linkedin_jobs.py --spreadsheet-id 1nmyj76On7Sc33N9OSf3l6u9gNJMPBWAWjQIS8P3iSt8 --gid 0 --limit 3
"""
import argparse
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

JOBS_KEY = "jobs"
JOBS_HEADER = "jobs linked"
CRAWLED_KEY = "jobs_crawled"
CRAWLED_HEADER = "Đã Crawl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sheet linkedin_url → crawl /jobs/ → extract job titles → write back (zero token)"
    )
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--gid", type=int, default=None,
                        help="GID số của tab (từ URL #gid=...)")
    parser.add_argument("--sheet-name", default=None,
                        help="Tên tab (thay thế --gid)")
    parser.add_argument("--col-linkedin", default="flagship_url",
                        help="Tên cột chứa website URL của công ty (default: flagship_url)")
    parser.add_argument("--col-name", default="tuyển d",
                        help="Tên cột hiển thị tên công ty trong log (default: tuyển d)")
    parser.add_argument("--col-jobs", default="tuyển d",
                        help="Tên cột ghi kết quả jobs (default: tuyển d)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Giây nghỉ giữa các request (default: 2.0)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Chỉ xử lý N hàng đầu (0 = tất cả)")
    return parser.parse_args()


def _is_crawled(row: dict) -> bool:
    val = row.get(CRAWLED_HEADER, "")
    return val is True or str(val).upper() == "TRUE"


def main():
    args = parse_args()

    import os
    from src.sheets_writer import read_from_sheet, append_col_to_sheet, append_checkbox_col_to_sheet
    from src.linkedin_jobs_fetcher import fetch_company_jobs, format_jobs

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)

    # 1. Đọc sheet
    tab_desc = f"gid={args.gid}" if args.gid is not None else f"sheet='{args.sheet_name}'"
    print(f"Reading [{tab_desc}] from {args.spreadsheet_id} ...")
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
        print(f"Processing first {args.limit} row(s) only.")

    # 2. Fetch jobs từng công ty
    enriched = []
    skipped = 0
    for i, row in enumerate(rows, 1):
        company = row.get(args.col_name, "") or f"Row {i}"
        linkedin_url = (row.get(args.col_linkedin, "") or "").strip()

        print(f"\n[{i}/{len(rows)}] {company}")

        enriched_row = dict(row)

        if _is_crawled(row):
            print(f"  Skip — already crawled")
            enriched_row[JOBS_KEY] = row.get(args.col_jobs, "")
            enriched_row[CRAWLED_KEY] = True
            enriched.append(enriched_row)
            skipped += 1
            continue

        if not linkedin_url:
            print(f"  Skip — no flagship_url")
            enriched_row[JOBS_KEY] = ""
            enriched_row[CRAWLED_KEY] = False
            enriched.append(enriched_row)
            continue

        jobs = fetch_company_jobs(linkedin_url, api_key=api_key)
        formatted = format_jobs(jobs)

        if jobs:
            print(f"  Found {len(jobs)} job(s): {', '.join(jobs[:3])}{'...' if len(jobs) > 3 else ''}")
        else:
            print(f"  [WARN] No jobs found (LinkedIn may require login)")

        enriched_row[JOBS_KEY] = formatted
        enriched_row[CRAWLED_KEY] = bool(jobs)
        enriched.append(enriched_row)

        if i < len(rows):
            time.sleep(args.delay)

    newly = sum(1 for r in enriched if r.get(CRAWLED_KEY) is True) - skipped
    print(f"\nDone: {newly} newly crawled, {skipped} skipped.")

    # 3. Ghi 2 cột vào tab nguồn
    print(f"\nWriting to [{tab_desc}] ...")
    url = append_col_to_sheet(
        enriched_rows=enriched,
        spreadsheet_id=args.spreadsheet_id,
        col_key=JOBS_KEY,
        col_header=JOBS_HEADER,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )
    append_checkbox_col_to_sheet(
        enriched_rows=enriched,
        spreadsheet_id=args.spreadsheet_id,
        col_key=CRAWLED_KEY,
        col_header=CRAWLED_HEADER,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )

    print(f"\nDone! {url}")


if __name__ == "__main__":
    main()
