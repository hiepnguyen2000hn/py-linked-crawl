"""
Full enrichment từ Google Sheet — chạy 2 luồng cho mỗi công ty:
  1. flagship_url/jobs → Playwright → DeepSeek → cột "jobs linked"
  2. website           → crawl4ai  → DeepSeek → cột Tuyển Dụng, Blog, Lĩnh Vực, Dự Án Gần Nhất, Đối Tác

Ghi 6 cột mới vào tab nguồn + 1 checkbox "Đã Crawl".

Cách dùng:
    python from_sheet_full_enrich.py --spreadsheet-id SHEET_ID --gid GID

Ví dụ:
    python from_sheet_full_enrich.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

# ── Cột kết quả ──────────────────────────────────────────────────────────────
JOBS_KEY        = "jobs"
JOBS_HEADER     = "jobs linked"

BLOG_KEY        = "blog"
LINH_VUC_KEY    = "linh_vuc"
DU_AN_KEY       = "du_an_gan_nhat"
DOI_TAC_KEY     = "doi_tac"

TUYEN_DUNG_KEY  = "tuyen_dung"

WEBSITE_KEYS    = [TUYEN_DUNG_KEY, BLOG_KEY, LINH_VUC_KEY, DU_AN_KEY, DOI_TAC_KEY]
WEBSITE_HEADERS = ["Tuyển Dụng", "Blog", "Lĩnh Vực", "Dự Án Gần Nhất", "Đối Tác"]

CRAWLED_KEY     = "da_enrich"
CRAWLED_HEADER  = "Đã Crawl"


def parse_args():
    p = argparse.ArgumentParser(
        description="Full enrich: LinkedIn jobs + website profile → write 6 cols back"
    )
    p.add_argument("--spreadsheet-id", required=True)
    p.add_argument("--gid", type=int, default=None,
                   help="GID số của tab (từ URL #gid=...)")
    p.add_argument("--sheet-name", default=None)
    p.add_argument("--col-linkedin", default="flagship_url",
                   help="Cột website URL để crawl /jobs (default: flagship_url)")
    p.add_argument("--col-website",  default="website",
                   help="Cột website URL (default: website)")
    p.add_argument("--col-name",     default="tuyển d",
                   help="Cột tên công ty để hiển thị log")
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--limit", type=int,  default=0)
    return p.parse_args()


def _is_done(row: dict) -> bool:
    val = row.get(CRAWLED_HEADER, "")
    return val is True or str(val).upper() == "TRUE"


def _enrich_linkedin_jobs(linkedin_url: str, api_key: str) -> str:
    """Crawl /jobs/ → DeepSeek → bullet string."""
    from src.linkedin_jobs_fetcher import fetch_company_jobs, format_jobs
    if not linkedin_url:
        return ""
    jobs = fetch_company_jobs(linkedin_url, api_key=api_key)
    return format_jobs(jobs)


def _enrich_website(website: str, profile_extractor) -> dict:
    """Crawl website → DeepSeek extract 4 profile fields."""
    from src.crawl4ai_crawler import Crawl4AICrawler
    from src.website_crawler import WebsiteCrawler
    from main import _crawl_company_pages

    if not website:
        return {k: "" for k in WEBSITE_KEYS}

    crawler = Crawl4AICrawler()
    helper  = WebsiteCrawler()
    try:
        result   = _crawl_company_pages(website, crawler, helper, extractor=None)
        markdown = result.get("markdown", "")
    except Exception as e:
        print(f"    [website crawl] Error: {e}")
        markdown = ""

    if not markdown:
        return {k: "" for k in WEBSITE_KEYS}

    full = profile_extractor.extract(markdown)
    return {k: full.get(k, "") for k in WEBSITE_KEYS}


def main():
    args = parse_args()

    from src.sheets_writer import (
        read_from_sheet,
        append_col_to_sheet,
        append_checkbox_col_to_sheet,
    )
    from src.company_profile_extractor import CompanyProfileExtractor

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)

    profile_extractor = CompanyProfileExtractor(api_key=api_key)

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

    # 2. Enrich từng công ty
    enriched = []
    skipped  = 0

    for i, row in enumerate(rows, 1):
        name         = row.get(args.col_name, "") or f"Row {i}"
        linkedin_url = (row.get(args.col_linkedin, "") or "").strip()
        website      = (row.get(args.col_website,  "") or "").strip()

        print(f"\n[{i}/{len(rows)}] {name}")

        enriched_row = dict(row)

        if _is_done(row):
            print(f"  Skip — already enriched (Đã Enrich = TRUE)")
            enriched_row[JOBS_KEY]  = row.get(JOBS_HEADER, "")
            for k in WEBSITE_KEYS:
                enriched_row[k] = row.get(k, "")
            enriched_row[CRAWLED_KEY] = True
            enriched.append(enriched_row)
            skipped += 1
            continue

        # ── Luồng 1: LinkedIn jobs ──────────────────────────────────────────
        print(f"  [1/2] LinkedIn jobs: {linkedin_url or '(trống)'}")
        jobs_text = _enrich_linkedin_jobs(linkedin_url, api_key)
        if jobs_text:
            preview = jobs_text[:80].replace("\n", " | ")
            print(f"    → {preview}")
        else:
            print(f"    → (không tìm được jobs)")

        # ── Luồng 2: Website profile ────────────────────────────────────────
        print(f"  [2/2] Website: {website or '(trống)'}")
        profile = _enrich_website(website, profile_extractor)
        for k, v in profile.items():
            if v:
                print(f"    {k}: {v[:80].replace(chr(10), ' ')}")

        enriched_row[JOBS_KEY]    = jobs_text
        enriched_row[CRAWLED_KEY] = True
        enriched_row.update(profile)
        enriched.append(enriched_row)

        if i < len(rows):
            time.sleep(args.delay)

    newly = len(enriched) - skipped
    print(f"\nDone: {newly} enriched, {skipped} skipped.")

    # 3. Ghi tất cả cột về sheet
    print(f"\nWriting to [{tab_desc}] ...")

    kwargs = dict(
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )

    # Cột "jobs linked"
    append_col_to_sheet(enriched_rows=enriched, col_key=JOBS_KEY, col_header=JOBS_HEADER, **kwargs)

    # 4 cột website — append từng cột riêng, không rewrite sheet
    for key, header in zip(WEBSITE_KEYS, WEBSITE_HEADERS):
        append_col_to_sheet(enriched_rows=enriched, col_key=key, col_header=header, **kwargs)

    # Checkbox "Đã Crawl"
    append_checkbox_col_to_sheet(enriched_rows=enriched, col_key=CRAWLED_KEY, col_header=CRAWLED_HEADER, **kwargs)

    print(f"\nDone!")


if __name__ == "__main__":
    main()
