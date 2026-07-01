"""
Gen comment từ Google Sheet — đọc bài viết đã crawl (cột "Bài Viết"),
dùng DeepSeek sinh nội dung comment tự nhiên cho từng người,
ghi kết quả vào cột "Comment" trong sheet.

Cách dùng:
    python gen_comment.py --spreadsheet-id SHEET_ID --gid GID

Ví dụ:
    python gen_comment.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

COMMENT_KEY    = "comment"
COMMENT_HEADER = "Comment"
DONE_KEY       = "comment_generated"
DONE_HEADER    = "Comment_Generated"


def parse_args():
    p = argparse.ArgumentParser(description="Generate LinkedIn post comments → write to sheet")
    p.add_argument("--spreadsheet-id", required=True)
    p.add_argument("--gid",        type=int,   default=None)
    p.add_argument("--sheet-name", default=None)
    p.add_argument("--col-name",   default="fullName",  help="Column to display in log")
    p.add_argument("--delay",      type=float, default=1.0, help="Delay between API calls (s)")
    p.add_argument("--limit",      type=int,   default=0,   help="Max rows to process (0 = all)")
    p.add_argument("--regen",      action="store_true",     help="Re-generate even if already done")
    return p.parse_args()


def _is_done(row: dict) -> bool:
    val = row.get(DONE_HEADER, "")
    return val is True or str(val).upper() == "TRUE"


def _has_post(row: dict) -> bool:
    post = row.get("Bài Viết", "") or row.get("bai_viet", "") or row.get("post", "")
    return len(str(post).strip()) > 30


def main():
    args = parse_args()

    from src.sheets_writer import read_from_sheet, append_col_to_sheet, append_checkbox_col_to_sheet
    from src.comment_generator import CommentGenerator

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)

    generator = CommentGenerator(api_key=api_key)

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

    enriched = []
    skipped  = 0
    no_post  = 0

    for i, row in enumerate(rows, 1):
        name = row.get(args.col_name, "") or f"Row {i}"
        print(f"\n[{i}/{len(rows)}] {name}")

        enriched_row = dict(row)

        if not args.regen and _is_done(row):
            print(f"  Skip — already generated (Comment_Generated = TRUE)")
            enriched_row[COMMENT_KEY] = row.get(COMMENT_HEADER, "")
            enriched_row[DONE_KEY]    = True
            enriched.append(enriched_row)
            skipped += 1
            continue

        if not _has_post(row):
            print(f"  Skip — no crawled post content (cột 'Bài Viết' trống)")
            enriched_row[COMMENT_KEY] = ""
            enriched_row[DONE_KEY]    = False
            enriched.append(enriched_row)
            no_post += 1
            continue

        comment = generator.generate(row)
        if comment:
            preview = comment[:120].replace("\n", " ")
            print(f"  → {preview}")
        else:
            print(f"  → (generation failed)")

        enriched_row[COMMENT_KEY] = comment
        enriched_row[DONE_KEY]    = bool(comment)
        enriched.append(enriched_row)

        if i < len(rows):
            time.sleep(args.delay)

    newly = len(enriched) - skipped - no_post
    print(f"\nDone: {newly} generated, {skipped} skipped (already done), {no_post} skipped (no post).")

    print(f"\nWriting to [{tab_desc}] ...")
    kwargs = dict(
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )
    append_col_to_sheet(enriched_rows=enriched, col_key=COMMENT_KEY, col_header=COMMENT_HEADER, **kwargs)
    append_checkbox_col_to_sheet(enriched_rows=enriched, col_key=DONE_KEY, col_header=DONE_HEADER, **kwargs)
    print("Done!")


if __name__ == "__main__":
    main()
