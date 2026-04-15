"""
FastAPI server — expose crawl4ai as HTTP API
Run: python -m uvicorn server:app --port 3006 --reload
"""
import asyncio
import sys

# Windows fix: ProactorEventLoop required for Playwright subprocess support
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Crawl API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_CRAWL_SCRIPT = os.path.join(_HERE, "_crawl_one.py")


def _crawl_url_sync(url: str) -> dict:
    """Chạy _crawl_one.py trong subprocess riêng — tránh event loop conflict với Playwright trên Windows."""
    import subprocess
    import json as _json

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, "-u", _CRAWL_SCRIPT, url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_HERE,
            timeout=60,
            env=env,
        )
        # lấy dòng JSON cuối cùng trong stdout
        lines = [l for l in result.stdout.strip().splitlines() if l.startswith("{")]
        if lines:
            return _json.loads(lines[-1])
        err = result.stderr.strip() or "No output"
        return {"ok": False, "url": url, "markdown": "", "error": err}
    except Exception as e:
        return {"ok": False, "url": url, "markdown": "", "error": str(e)}


async def _crawl_url(url: str) -> dict:
    """Async wrapper — chạy crawl trong thread pool để không block event loop."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, _crawl_url_sync, url)


# ── Request schemas ───────────────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    url: str


class CrawlSheetRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    url_column: str = "website"   # tên cột chứa URL trong sheet
    limit: int | None = None      # giới hạn số dòng crawl (None = tất cả)


class EnrichSheetRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None


class LinkedInSheetRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None
    col_linkedin: str = "linkedUrl"
    col_name: str = "fullName"
    cookies: list[dict] | None = None  # LinkedIn cookies từ Chrome extension


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/crawl")
async def crawl_website(req: CrawlRequest):
    """
    Crawl 1 URL → trả về markdown.
    Body:     { "url": "https://example.com" }
    Response: { "ok": true, "url": "...", "markdown": "..." }
    """
    return await _crawl_url(req.url)


@app.post("/crawl-sheet")
async def crawl_from_sheet(req: CrawlSheetRequest):
    """
    Đọc danh sách URL từ Google Sheet → crawl từng URL → trả về kết quả.
    Body:     { "spreadsheet_id": "...", "gid": 0, "url_column": "website" }
    Response: { "ok": true, "total": N, "results": [ { ok, url, markdown } ] }

    Yêu cầu: GOOGLE_SERVICE_ACCOUNT_JSON phải được set trong .env
    """
    from src.sheets_writer import read_from_sheet

    try:
        rows = read_from_sheet(
            spreadsheet_id=req.spreadsheet_id,
            sheet_name=req.sheet_name,
            gid=req.gid,
        )
    except Exception as e:
        return {"ok": False, "total": 0, "results": [], "error": f"Sheet read failed: {e}"}

    # Lọc bỏ dòng không có URL trước, sau đó mới giới hạn
    url_rows = [r for r in rows if str(r.get(req.url_column, "") or "").strip()]
    if req.limit is not None:
        url_rows = url_rows[:req.limit]

    results = []
    for row in url_rows:
        url = str(row.get(req.url_column, "")).strip()
        result = await _crawl_url(url)
        result["row"] = row
        results.append(result)

    return {"ok": True, "total": len(results), "results": results}


@app.post("/enrich-sheet")
async def enrich_sheet(req: EnrichSheetRequest):
    """
    Gọi from_sheet_full_enrich.py và stream stdout line-by-line qua SSE.
    Body:     { "spreadsheet_id": "...", "gid": 1694881147, "limit": 15 }
    Response: text/event-stream — mỗi dòng stdout là 1 SSE event
              Dòng cuối: data: __EXIT__:<returncode>
    """
    script = os.path.join(_HERE, "from_sheet_full_enrich.py")
    cmd = [sys.executable, "-u", script, "--spreadsheet-id", req.spreadsheet_id]
    if req.gid is not None: cmd += ["--gid", str(req.gid)]
    if req.sheet_name:      cmd += ["--sheet-name", req.sheet_name]
    if req.limit:           cmd += ["--limit", str(req.limit)]
    return _make_streaming_response(cmd, "enrich-sheet")


def _make_streaming_response(cmd: list, tag: str, extra_env: dict | None = None):
    """Helper: chạy script qua subprocess, stream stdout qua SSE."""
    import queue, threading, subprocess

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    line_queue: queue.Queue = queue.Queue()

    print(f"\n[{tag}] cmd: {' '.join(cmd)}", flush=True)

    def _run():
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=_HERE, env=env, text=True,
                encoding="utf-8", errors="replace", bufsize=1,
            )
            for line in proc.stdout:
                s = line.rstrip()
                if s:
                    print(f"[{tag}] {s}", flush=True)
                    line_queue.put(s)
            proc.wait()
            print(f"[{tag}] exit: {proc.returncode}", flush=True)
            line_queue.put(f"__EXIT__:{proc.returncode}")
        except Exception as e:
            line_queue.put(f"__ERROR__:{e}")
            line_queue.put("__EXIT__:1")

    threading.Thread(target=_run, daemon=True).start()

    async def generate():
        while True:
            try:
                item = line_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            yield f"data: {item}\n\n"
            if item.startswith("__EXIT__:") or item.startswith("__ERROR__:"):
                break

    from fastapi.responses import StreamingResponse as SR
    return SR(generate(), media_type="text/event-stream")


class LinkedInRowsRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None
    col_linkedin: str = "linkedUrl"
    col_name: str = "fullName"

class LinkedInExtractRequest(BaseModel):
    text: str
    name: str = ""

class LinkedInWriteRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    col_linkedin: str = "linkedUrl"
    col_name: str = "fullName"
    results: list[dict]  # [{index, name, url, post, crawled}]


@app.post("/linkedin-rows")
async def linkedin_rows(req: LinkedInRowsRequest):
    """Đọc sheet, trả về danh sách rows chưa crawl (có linkedUrl)."""
    from src.sheets_writer import read_from_sheet
    try:
        rows = read_from_sheet(spreadsheet_id=req.spreadsheet_id, gid=req.gid, sheet_name=req.sheet_name)
    except Exception as e:
        return {"ok": False, "rows": [], "error": str(e)}
    if req.limit:
        rows = rows[:req.limit]
    result = []
    for i, row in enumerate(rows):
        url = (row.get(req.col_linkedin, "") or "").strip()
        name = row.get(req.col_name, "") or f"Row {i+1}"
        already = str(row.get("Đã Crawl", "")).upper() == "TRUE" or row.get("Đã Crawl") is True
        result.append({"index": i, "name": name, "url": url, "already_crawled": already})
    return {"ok": True, "rows": result, "total": len(rows)}


def _html_to_markdown(html: str) -> str:
    """Dùng crawl4ai markdown converter để clean HTML → markdown (không cần browser)."""
    try:
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
        from crawl4ai.content_filter_strategy import PruningContentFilter
        generator = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(),
            options={"ignore_links": True, "ignore_images": True},
        )
        # crawl4ai generator nhận raw HTML string
        result = generator.generate_markdown(
            cleaned_html=html,
            base_url="https://www.linkedin.com",
        )
        return result.fit_markdown or result.raw_markdown or ""
    except Exception as e:
        print(f"[html_to_markdown] crawl4ai failed ({e}), using fallback")
        # Fallback: BeautifulSoup
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]
        return "\n".join(lines)


@app.post("/linkedin-extract")
async def linkedin_extract(req: LinkedInExtractRequest):
    """HTML → markdown (crawl4ai) → DeepSeek extract posts."""
    import os as _os
    from src.linkedin_post_extractor import LinkedInPostExtractor

    api_key = _os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return {"ok": False, "post": "", "error": "DEEPSEEK_API_KEY not set"}
    if not req.text or len(req.text.strip()) < 200:
        return {"ok": False, "post": "", "error": "Content too short"}

    # HTML → markdown sạch qua crawl4ai converter
    loop = asyncio.get_event_loop()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor() as pool:
        markdown = await loop.run_in_executor(pool, _html_to_markdown, req.text)

    print(f"[linkedin-extract] {req.name}: {len(req.text)} chars HTML → {len(markdown)} chars markdown")

    if len(markdown.strip()) < 100:
        return {"ok": False, "post": "", "error": "Markdown too short after conversion"}

    extractor = LinkedInPostExtractor(api_key=api_key)
    result = extractor.extract(markdown)
    post = result.get("post", "")
    print(f"[linkedin-extract] {req.name}: post={'yes' if post else 'empty'}")
    return {"ok": True, "post": post}


@app.post("/linkedin-write")
async def linkedin_write(req: LinkedInWriteRequest):
    """Ghi kết quả posts vào Google Sheet.
    Chỉ ghi các row vừa crawl — KHÔNG đụng vào rows đã có (tránh ghi đè thành empty).
    """
    from src.sheets_writer import _get_client, _build_text_format_runs
    import gspread as _gspread

    results_by_index = {r["index"]: r for r in req.results}
    if not results_by_index:
        return {"ok": True, "url": ""}

    try:
        client = _get_client()
        spreadsheet = client.open_by_key(req.spreadsheet_id)
        if req.gid is not None:
            sheet = spreadsheet.get_worksheet_by_id(req.gid)
        else:
            sheet = spreadsheet.worksheet(req.sheet_name or "Sheet1")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # ── Tìm / tạo cột "Bài Viết" và "Đã Crawl" ──────────────────────────────
    headers = sheet.row_values(1)

    def _col_idx(header: str) -> int:
        if header in headers:
            return headers.index(header) + 1
        idx = len([h for h in headers if h]) + 1
        sheet.update_cell(1, idx, header)
        headers.append(header)
        return idx

    post_col_idx  = _col_idx("Bài Viết")
    crawl_col_idx = _col_idx("Đã Crawl")

    max_col = max(post_col_idx, crawl_col_idx)
    if max_col > sheet.col_count:
        sheet.resize(cols=max_col + 5)

    # ── Chỉ ghi những row vừa crawl ──────────────────────────────────────────
    post_requests  = []
    checkbox_cells = []

    for row_idx, r in results_by_index.items():
        sheet_row = row_idx + 2   # +1 header, +1 vì 1-based
        post_text = r.get("post", "")
        crawled   = bool(r.get("crawled", False))

        # Post cell — với hyperlink formatting nếu có URL
        runs      = _build_text_format_runs(post_text)
        cell_data: dict = {"userEnteredValue": {"stringValue": post_text}}
        if runs:
            cell_data["textFormatRuns"] = runs

        post_requests.append({
            "updateCells": {
                "rows": [{"values": [cell_data]}],
                "fields": "userEnteredValue,textFormatRuns",
                "range": {
                    "sheetId": sheet.id,
                    "startRowIndex": sheet_row - 1,
                    "endRowIndex": sheet_row,
                    "startColumnIndex": post_col_idx  - 1,
                    "endColumnIndex":   post_col_idx,
                },
            }
        })

        # Checkbox cell
        checkbox_cells.append(_gspread.Cell(sheet_row, crawl_col_idx, crawled))

    try:
        if post_requests:
            spreadsheet.batch_update({"requests": post_requests})

        if checkbox_cells:
            sheet.update_cells(checkbox_cells, value_input_option="RAW")
            # Áp dụng BOOLEAN validation (checkbox UI)
            row_indices = [c.row for c in checkbox_cells]
            spreadsheet.batch_update({"requests": [{
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet.id,
                        "startRowIndex": min(row_indices) - 1,
                        "endRowIndex":   max(row_indices),
                        "startColumnIndex": crawl_col_idx - 1,
                        "endColumnIndex":   crawl_col_idx,
                    },
                    "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True},
                }
            }]})

        url = f"https://docs.google.com/spreadsheets/d/{req.spreadsheet_id}/edit#gid={sheet.id}"
        print(f"[linkedin-write] wrote {len(results_by_index)} new row(s) → {url}")
        return {"ok": True, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/linkedin-sheet")
async def linkedin_sheet(req: LinkedInSheetRequest):
    """
    Chạy from_sheet_linkedin.py — crawl LinkedIn posts từ sheet.
    Body: { spreadsheet_id, gid, limit, col_linkedin, col_name, cookies? }
    cookies: list of {name, value, domain, path} từ Chrome extension
    """
    import json as _json
    script = os.path.join(_HERE, "from_sheet_linkedin.py")
    cmd = [sys.executable, "-u", script, "--spreadsheet-id", req.spreadsheet_id]
    if req.gid is not None:    cmd += ["--gid", str(req.gid)]
    if req.sheet_name:         cmd += ["--sheet-name", req.sheet_name]
    if req.limit:              cmd += ["--limit", str(req.limit)]
    if req.col_linkedin:       cmd += ["--col-linkedin", req.col_linkedin]
    if req.col_name:           cmd += ["--col-name", req.col_name]
    # Truyền cookies qua env var để subprocess inject vào Playwright
    extra_env = {}
    if req.cookies:
        extra_env["LINKEDIN_COOKIES_JSON"] = _json.dumps(req.cookies)
        print(f"[linkedin-sheet] Passing {len(req.cookies)} LinkedIn cookies to subprocess")
    return _make_streaming_response(cmd, "linkedin-sheet", extra_env=extra_env)
