"""
Gen post comment từ Google Sheet — đọc cột "Bài Viết" (nội dung bài viết LinkedIn),
dùng DeepSeek sinh comment ngắn gọn để thả dưới bài viết,
ghi kết quả vào cột "Post_Comment" trong sheet.

Cách dùng:
    python gen_post_comment.py --spreadsheet-id SHEET_ID --gid GID

Ví dụ:
    python gen_post_comment.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

COMMENT_KEY    = "postComment"
COMMENT_HEADER = "Post_Comment"
DONE_KEY       = "comment_generated"
DONE_HEADER    = "Comment_Generated"


def parse_args():
    p = argparse.ArgumentParser(description="Generate LinkedIn post comments → write to sheet")
    p.add_argument("--spreadsheet-id", required=True)
    p.add_argument("--gid",        type=int,   default=None)
    p.add_argument("--sheet-name", default=None)
    p.add_argument("--post-col",   default="Bài Viết", help="Column containing post content")
    p.add_argument("--col-name",   default="fullName",  help="Column to display in log")
    p.add_argument("--delay",      type=float, default=1.0, help="Delay between API calls (s)")
    p.add_argument("--limit",      type=int,   default=0,   help="Max rows to process (0 = all)")
    p.add_argument("--regen",      action="store_true",     help="Re-generate even if already done")
    return p.parse_args()


def _is_done(row: dict) -> bool:
    val = row.get(DONE_HEADER, "")
    return val is True or str(val).upper() == "TRUE"


def main():
    args = parse_args()

    from src.sheets_writer import read_from_sheet, append_col_to_sheet, append_checkbox_col_to_sheet
    from src.post_comment_generator import PostCommentGenerator

    generator = PostCommentGenerator()

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

        comment = generator.generate(row, post_col=args.post_col)
        if comment:
            preview = comment[:120].replace("\n", " ")
            print(f"  → {preview}")
        else:
            print(f"  → (skip — no post content or generation failed)")

        enriched_row[COMMENT_KEY] = comment
        enriched_row[DONE_KEY]    = bool(comment)
        enriched.append(enriched_row)

        if i < len(rows):
            time.sleep(args.delay)

    newly = len(enriched) - skipped
    print(f"\nDone: {newly} generated, {skipped} skipped.")

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
