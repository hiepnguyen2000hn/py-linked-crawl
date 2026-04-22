"""
Gen connect message từ Google Sheet — đọc danh sách leads,
dùng DeepSeek sinh LinkedIn connection message cho từng người,
ghi kết quả vào cột "Connect_Message" trong sheet.

Cách dùng:
    python gen_connect_message.py --spreadsheet-id SHEET_ID --gid GID

Ví dụ:
    python gen_connect_message.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147
"""
import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

MSG_KEY    = "message"
MSG_HEADER = "message"
DONE_KEY   = "msg_generated"
DONE_HEADER = "Msg_Generated"


def parse_args():
    p = argparse.ArgumentParser(description="Generate LinkedIn connect messages → write to sheet")
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


def main():
    args = parse_args()

    from src.sheets_writer import read_from_sheet, append_col_to_sheet, append_checkbox_col_to_sheet
    from src.connect_message_generator import ConnectMessageGenerator

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        sys.exit(1)

    generator = ConnectMessageGenerator(api_key=api_key)

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
            print(f"  Skip — already generated (Msg_Generated = TRUE)")
            enriched_row[MSG_KEY]  = row.get(MSG_HEADER, "")
            enriched_row[DONE_KEY] = True
            enriched.append(enriched_row)
            skipped += 1
            continue

        msg = generator.generate(row)
        if msg:
            preview = msg[:100].replace("\n", " ")
            print(f"  → {preview}")
        else:
            print(f"  → (generation failed)")

        enriched_row[MSG_KEY]  = msg
        enriched_row[DONE_KEY] = True
        enriched.append(enriched_row)

        if i < len(rows):
            time.sleep(args.delay)

    newly   = len(enriched) - skipped
    print(f"\nDone: {newly} generated, {skipped} skipped.")

    print(f"\nWriting to [{tab_desc}] ...")
    kwargs = dict(
        spreadsheet_id=args.spreadsheet_id,
        sheet_name=args.sheet_name,
        gid=args.gid,
    )
    append_col_to_sheet(enriched_rows=enriched, col_key=MSG_KEY,  col_header=MSG_HEADER,  **kwargs)
    append_checkbox_col_to_sheet(enriched_rows=enriched, col_key=DONE_KEY, col_header=DONE_HEADER, **kwargs)
    print("Done!")


if __name__ == "__main__":
    main()
