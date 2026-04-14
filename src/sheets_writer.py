# src/sheets_writer.py
import os
import re
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import InstalledAppFlow

_URL_RE = re.compile(r'https?://[^\s\]\)>,\'"]+')

_LINK_COLOR = {"red": 0.06, "green": 0.47, "blue": 0.93}  # Google blue


def _build_text_format_runs(text: str) -> list:
    """Tạo textFormatRuns cho Sheets API: URL trong text → blue underline hyperlink."""
    runs = []
    last_end = 0
    for m in _URL_RE.finditer(text):
        s, e = m.start(), m.end()
        if s > last_end:
            runs.append({"startIndex": last_end, "format": {}})
        runs.append({
            "startIndex": s,
            "format": {
                "link": {"uri": m.group()},
                "foregroundColorStyle": {"rgbColor": _LINK_COLOR},
                "underline": True,
            },
        })
        last_end = e
    if last_end > 0 and last_end < len(text):
        runs.append({"startIndex": last_end, "format": {}})
    return runs

SPREADSHEET_ID = "1PW5LnQyXjyl0h16ooufYNYjR1_eb8DgfnCEGLNjsf10"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Company Name", "Website", "Address", "Phone",
    "Company Email", "Company Phones",
    "LinkedIn (Co.)", "Facebook", "Instagram", "Twitter", "YouTube",
    "WhatsApp", "WeChat", "Telegram", "Line", "TikTok", "Zalo",
    "Services", "Summary",
    "Person Title", "Person Name", "Person LinkedIn", "Person Email",
]


def _get_client() -> gspread.Client:
    """Auth via service account JSON (env: GOOGLE_SERVICE_ACCOUNT_JSON path)
    or OAuth2 credentials (env: GOOGLE_OAUTH_CLIENT_SECRET path)."""
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_path and os.path.exists(sa_path):
        creds = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        return gspread.authorize(creds)

    oauth_path = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "client_secret.json")
    token_path = "token.json"

    if os.path.exists(token_path):
        creds = OAuthCredentials.from_authorized_user_file(token_path, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(oauth_path, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return gspread.authorize(creds)


def _flatten_companies(companies: list[dict]) -> list[list]:
    """One company row (with socials) + one sub-row per leader below it."""
    rows = []
    EMPTY_PERSON = ["", "", "", ""]

    for c in companies:
        name = c.get("name") or c.get("company_name") or ""
        website = c.get("website") or ""
        address = c.get("address") or ""
        phone = c.get("phone") or ""

        analysis = c.get("analysis") or {}
        services = " | ".join(analysis.get("services") or [])
        summary = analysis.get("summary") or ""
        leaders = c.get("leaders") or analysis.get("leadership") or []

        socials = c.get("socials") or {}
        co_email = socials.get("email", "")
        phones_str = " | ".join(socials.get("phones") or [])
        linkedin_co = socials.get("linkedin", "")
        facebook = socials.get("facebook", "")
        instagram = socials.get("instagram", "")
        twitter = socials.get("twitter", "")
        youtube = socials.get("youtube", "")
        whatsapp = socials.get("whatsapp", "")
        wechat = socials.get("wechat", "")
        telegram = socials.get("telegram", "")
        line_app = socials.get("line", "")
        tiktok = socials.get("tiktok", "")
        zalo = socials.get("zalo", "")

        company_cols = [
            name, website, address, phone,
            co_email, phones_str,
            linkedin_co, facebook, instagram, twitter, youtube,
            whatsapp, wechat, telegram, line_app, tiktok, zalo,
            services, summary,
        ]

        # Company row (no person info)
        rows.append(company_cols + EMPTY_PERSON)

        # One sub-row per leader (company cols empty except name for reference)
        for l in leaders:
            if not l.get("name"):
                continue
            person_cols = [
                l.get("title", ""),
                l.get("name", ""),
                l.get("linkedin", ""),
                l.get("email", ""),
            ]
            empty_company = [""] * len(company_cols)
            rows.append(empty_company + person_cols)

    return rows


def save_to_sheet(
    companies: list[dict],
    sheet_name: str = "Sheet1",
    spreadsheet_id: str = SPREADSHEET_ID,
) -> str:
    """Write companies to Google Sheet. Returns the sheet URL."""
    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    try:
        sheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(HEADERS))

    rows = _flatten_companies(companies)

    existing = sheet.get_all_values()
    if not existing or existing[0] != HEADERS:
        # Sheet empty or different headers — write fresh
        sheet.clear()
        sheet.update([HEADERS] + rows, "A1")
        print(f"  [Sheets] Written {len(rows)} rows (fresh) to '{sheet_name}'")
    else:
        # Sheet has data — append below existing rows
        next_row = len(existing) + 1
        sheet.update(rows, f"A{next_row}")
        print(f"  [Sheets] Appended {len(rows)} rows at row {next_row} in '{sheet_name}'")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet.id}"
    print(f"  [Sheets] {url}")
    return url


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


def update_sheet_with_extra_cols(
    enriched_rows: list[dict],
    spreadsheet_id: str = SPREADSHEET_ID,
    sheet_name: str | None = None,
    gid: int | None = None,
) -> str:
    """Ghi đè tab nguồn: giữ nguyên các cột cũ + thêm các cột enriched sang phải.
    Dùng cùng gid/sheet_name đã đọc, KHÔNG tạo tab mới.
    """
    if not enriched_rows:
        print("  [Sheets] No rows to write.")
        return ""

    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    if gid is not None:
        sheet = spreadsheet.get_worksheet_by_id(gid)
    else:
        sheet = spreadsheet.worksheet(sheet_name or "Sheet1")

    # Header: tất cả key gốc (trừ key enriched) + ENRICHED_EXTRA_HEADERS
    original_keys = [
        k for k in enriched_rows[0].keys()
        if k not in ENRICHED_EXTRA_KEYS
    ]
    all_headers = original_keys + ENRICHED_EXTRA_HEADERS

    def make_row(row: dict) -> list:
        return (
            [str(row.get(k, "") or "") for k in original_keys]
            + [str(row.get(k, "") or "") for k in ENRICHED_EXTRA_KEYS]
        )

    data = [all_headers] + [make_row(r) for r in enriched_rows]
    sheet.clear()
    sheet.update(data, "A1")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet.id}"
    print(f"  [Sheets] Updated {len(enriched_rows)} row(s) in '{sheet.title}' (same tab)")
    print(f"  [Sheets] {url}")
    return url


def append_col_with_links(
    enriched_rows: list[dict],
    spreadsheet_id: str,
    col_key: str,
    col_header: str,
    sheet_name: str | None = None,
    gid: int | None = None,
) -> str:
    """Ghi thêm cột text vào tab; các URL trong nội dung sẽ thành hyperlink xanh.
    Dùng Sheets API updateCells với textFormatRuns.
    """
    if not enriched_rows:
        print("  [Sheets] No rows to write.")
        return ""

    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    if gid is not None:
        sheet = spreadsheet.get_worksheet_by_id(gid)
    else:
        sheet = spreadsheet.worksheet(sheet_name or "Sheet1")

    headers = sheet.row_values(1)
    if col_header in headers:
        col_idx = headers.index(col_header) + 1
    else:
        col_idx = len([h for h in headers if h]) + 1

    # Ghi header bằng update_cell thông thường
    sheet.update_cell(1, col_idx, col_header)

    # Build updateCells request cho từng data row
    row_data = []
    for row in enriched_rows:
        text = str(row.get(col_key, "") or "")
        runs = _build_text_format_runs(text)
        cell = {
            "userEnteredValue": {"stringValue": text},
        }
        if runs:
            cell["textFormatRuns"] = runs
        row_data.append({"values": [cell]})

    requests = [{
        "updateCells": {
            "rows": row_data,
            "fields": "userEnteredValue,textFormatRuns",
            "range": {
                "sheetId": sheet.id,
                "startRowIndex": 1,
                "endRowIndex": len(enriched_rows) + 1,
                "startColumnIndex": col_idx - 1,
                "endColumnIndex": col_idx,
            },
        }
    }]
    spreadsheet.batch_update({"requests": requests})

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet.id}"
    print(f"  [Sheets] Appended col '{col_header}' with links ({len(enriched_rows)} rows) in '{sheet.title}'")
    print(f"  [Sheets] {url}")
    return url


def append_checkbox_col_to_sheet(
    enriched_rows: list[dict],
    spreadsheet_id: str,
    col_key: str,
    col_header: str,
    sheet_name: str | None = None,
    gid: int | None = None,
) -> None:
    """Ghi thêm 1 cột checkbox (TRUE/FALSE) vào tab hiện tại.
    Áp dụng BOOLEAN data validation (checkbox) cho toàn cột dữ liệu.
    Mặc định FALSE cho ô chưa có giá trị.
    """
    if not enriched_rows:
        return

    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    if gid is not None:
        sheet = spreadsheet.get_worksheet_by_id(gid)
    else:
        sheet = spreadsheet.worksheet(sheet_name or "Sheet1")

    headers = sheet.row_values(1)
    if col_header in headers:
        col_idx = headers.index(col_header) + 1
    else:
        col_idx = len([h for h in headers if h]) + 1

    # Mở rộng sheet nếu cột vượt quá giới hạn hiện tại
    if col_idx > sheet.col_count:
        sheet.resize(cols=col_idx + 10)

    # Ghi header + giá trị TRUE/FALSE
    cells = [gspread.Cell(1, col_idx, col_header)]
    for i, row in enumerate(enriched_rows):
        val = row.get(col_key, False)
        # Chuẩn hoá về boolean Python để gspread ghi đúng kiểu
        cells.append(gspread.Cell(i + 2, col_idx, bool(val)))

    sheet.update_cells(cells, value_input_option="RAW")

    # Áp dụng checkbox format (BOOLEAN data validation)
    requests = [{
        "setDataValidation": {
            "range": {
                "sheetId": sheet.id,
                "startRowIndex": 1,
                "endRowIndex": len(enriched_rows) + 1,
                "startColumnIndex": col_idx - 1,
                "endColumnIndex": col_idx,
            },
            "rule": {
                "condition": {"type": "BOOLEAN"},
                "showCustomUi": True,
            },
        }
    }]
    spreadsheet.batch_update({"requests": requests})
    print(f"  [Sheets] Appended checkbox col '{col_header}' ({len(enriched_rows)} rows) in '{sheet.title}'")


def update_sheet_with_cols(
    enriched_rows: list[dict],
    spreadsheet_id: str,
    extra_keys: list[str],
    extra_headers: list[str],
    sheet_name: str | None = None,
    gid: int | None = None,
) -> str:
    """Generic version of update_sheet_with_extra_cols.
    Ghi đè tab nguồn: giữ nguyên các cột cũ + thêm extra_headers sang phải.
    extra_keys: dict keys chứa giá trị enriched (e.g. ["post_1", "post_2", "post_3"])
    extra_headers: tên cột hiển thị trong sheet (e.g. ["Bài Viết 1", "Bài Viết 2", "Bài Viết 3"])
    """
    if not enriched_rows:
        print("  [Sheets] No rows to write.")
        return ""

    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    if gid is not None:
        sheet = spreadsheet.get_worksheet_by_id(gid)
    else:
        sheet = spreadsheet.worksheet(sheet_name or "Sheet1")

    original_keys = [
        k for k in enriched_rows[0].keys()
        if k not in extra_keys
    ]
    all_headers = original_keys + extra_headers

    def make_row(row: dict) -> list:
        return (
            [str(row.get(k, "") or "") for k in original_keys]
            + [str(row.get(k, "") or "") for k in extra_keys]
        )

    data = [all_headers] + [make_row(r) for r in enriched_rows]
    sheet.clear()
    sheet.update(data, "A1")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet.id}"
    print(f"  [Sheets] Updated {len(enriched_rows)} row(s) in '{sheet.title}' (same tab)")
    print(f"  [Sheets] {url}")
    return url


def append_col_to_sheet(
    enriched_rows: list[dict],
    spreadsheet_id: str,
    col_key: str,
    col_header: str,
    sheet_name: str | None = None,
    gid: int | None = None,
) -> str:
    """Ghi thêm 1 cột mới vào tab hiện tại mà không xóa/ghi lại toàn bộ sheet.
    Tìm cột theo col_header trong hàng tiêu đề; nếu chưa có thì thêm vào cuối.
    enriched_rows phải theo đúng thứ tự hàng trong sheet (hàng 2 trở đi).
    """
    if not enriched_rows:
        print("  [Sheets] No rows to write.")
        return ""

    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)

    if gid is not None:
        sheet = spreadsheet.get_worksheet_by_id(gid)
    else:
        sheet = spreadsheet.worksheet(sheet_name or "Sheet1")

    headers = sheet.row_values(1)
    if col_header in headers:
        col_idx = headers.index(col_header) + 1  # 1-based
    else:
        col_idx = len([h for h in headers if h]) + 1

    # Mở rộng sheet nếu cột vượt quá giới hạn hiện tại
    if col_idx > sheet.col_count:
        sheet.resize(cols=col_idx + 10)

    cells = [gspread.Cell(1, col_idx, col_header)]
    for i, row in enumerate(enriched_rows):
        cells.append(gspread.Cell(i + 2, col_idx, str(row.get(col_key, "") or "")))

    sheet.update_cells(cells, value_input_option="RAW")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet.id}"
    print(f"  [Sheets] Appended col '{col_header}' ({len(enriched_rows)} rows) in '{sheet.title}'")
    print(f"  [Sheets] {url}")
    return url


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
