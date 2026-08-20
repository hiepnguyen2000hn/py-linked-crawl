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
from fastapi import FastAPI, Depends, HTTPException, Header
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


# ── Supabase JWT Auth ─────────────────────────────────────────────────────────

_JWT_SECRET   = os.getenv("SUPABASE_JWT_SECRET", "")
_REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "true").lower() == "true"


_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0

def _get_jwks() -> dict:
    """Fetch JWKS từ Supabase (cache 10 phút)."""
    import time, requests as _req
    global _jwks_cache, _jwks_fetched_at
    if _jwks_cache and (time.time() - _jwks_fetched_at) < 600:
        return _jwks_cache
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        return {}
    try:
        r = _req.get(f"{supabase_url}/auth/v1/.well-known/jwks.json", timeout=5)
        _jwks_cache = r.json()
        _jwks_fetched_at = time.time()
        return _jwks_cache
    except Exception:
        return {}


def _verify_jwt(token: str) -> dict:
    """
    Verify Supabase JWT — hỗ trợ cả 2 key types:
      - ECC P-256 (ES256)  ← current key mới
      - HS256 shared secret ← legacy key cũ
    """
    from jose import jwt as _jwt, JWTError

    # 1. Thử JWKS (ES256 / ECC P-256) — current key
    jwks = _get_jwks()
    if jwks.get("keys"):
        try:
            return _jwt.decode(token, jwks, algorithms=["ES256", "RS256"],
                               audience="authenticated")
        except Exception:
            pass  # fallback xuống HS256

    # 2. Fallback: Legacy HS256 shared secret
    if _JWT_SECRET:
        try:
            return _jwt.decode(token, _JWT_SECRET, algorithms=["HS256"],
                               audience="authenticated")
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    raise HTTPException(status_code=401, detail="Cannot verify token: no JWT secret or JWKS configured")


async def require_auth(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency — trả về JWT payload hoặc raise 401."""
    if not _REQUIRE_AUTH:
        return {}  # dev mode: bỏ qua auth
    if not _JWT_SECRET:
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    return _verify_jwt(authorization[7:])


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

class ProviderConfig(BaseModel):
    """Config block gửi kèm từ extension (override .env)."""
    # Email
    email_providers:    list[str] = ["hunter", "apollo", "snov", "pattern"]
    hunter_api_key:     str = ""
    apollo_api_key:     str = ""
    snov_client_id:     str = ""
    snov_client_secret: str = ""
    # AI
    ai_providers:       list[str] = ["deepseek", "openai", "claude", "gemini"]
    deepseek_api_key:   str = ""
    openai_api_key:     str = ""
    claude_api_key:     str = ""
    gemini_api_key:     str = ""
    openrouter_api_key: str = ""
    openai_model:       str = ""
    claude_model:       str = ""
    openrouter_model:   str = ""  # e.g. "deepseek/deepseek-chat", "openai/gpt-4o", "anthropic/claude-opus-4"
    # CRM
    crm_providers:       list[str] = []
    hubspot_api_key:     str = ""
    notion_token:        str = ""
    notion_database_id:  str = ""


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
async def crawl_website(req: CrawlRequest, _user: dict = Depends(require_auth)):
    """
    Crawl 1 URL → crawl4ai markdown → DeepSeek extract company profile.
    Body:     { "url": "https://example.com" }
    Response: { "ok": true, "url": "...", "markdown": "...",
                "tuyen_dung": "...", "blog": "...", "linh_vuc": "...",
                "du_an_gan_nhat": "...", "doi_tac": "..." }
    """
    result = await _crawl_url(req.url)
    if not result["ok"] or not result.get("markdown"):
        result.update({"tuyen_dung": "", "blog": "", "linh_vuc": "", "du_an_gan_nhat": "", "doi_tac": ""})
        return result

    from src.company_profile_extractor import CompanyProfileExtractor
    extractor = CompanyProfileExtractor()
    profile = extractor.extract(result["markdown"])
    result.update(profile)
    return result


@app.post("/crawl-sheet")
async def crawl_from_sheet(req: CrawlSheetRequest, _user: dict = Depends(require_auth)):
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
async def enrich_sheet(req: EnrichSheetRequest, _user: dict = Depends(require_auth)):
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


class GenConnectMsgRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None
    regen: bool = False


@app.post("/gen-connect-message")
async def gen_connect_message(req: GenConnectMsgRequest, _user: dict = Depends(require_auth)):
    """
    Đọc leads từ Google Sheet → DeepSeek sinh LinkedIn connection message → ghi cột Connect_Message.
    Body:     { "spreadsheet_id": "...", "gid": 123, "limit": 20 }
    Response: text/event-stream — stream stdout, dòng cuối __EXIT__:<code>
    """
    script = os.path.join(_HERE, "gen_connect_message.py")
    cmd = [sys.executable, "-u", script, "--spreadsheet-id", req.spreadsheet_id]
    if req.gid is not None: cmd += ["--gid", str(req.gid)]
    if req.sheet_name:      cmd += ["--sheet-name", req.sheet_name]
    if req.limit:           cmd += ["--limit", str(req.limit)]
    if req.regen:           cmd += ["--regen"]
    return _make_streaming_response(cmd, "gen-connect-message")


class GenPostCommentRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    post_col: str = "Bài Viết"
    limit: int | None = None
    regen: bool = False
    provider_config: ProviderConfig = ProviderConfig()


@app.post("/gen-post-comment")
async def gen_post_comment(req: GenPostCommentRequest, _user: dict = Depends(require_auth)):
    """
    Đọc cột "Bài Viết" từ Google Sheet → AI sinh comment để thả dưới bài viết
    → ghi cột Post_Comment.
    Body:     { "spreadsheet_id": "...", "gid": 123, "limit": 20,
                "provider_config": { "openrouter_api_key": "...", "openrouter_model": "google/gemma-4-31b-it:free" } }
    Response: text/event-stream — stream stdout, dòng cuối __EXIT__:<code>
    """
    script = os.path.join(_HERE, "gen_post_comment.py")
    cmd = [sys.executable, "-u", script, "--spreadsheet-id", req.spreadsheet_id]
    if req.gid is not None: cmd += ["--gid", str(req.gid)]
    if req.sheet_name:      cmd += ["--sheet-name", req.sheet_name]
    if req.post_col:        cmd += ["--post-col", req.post_col]
    if req.limit:           cmd += ["--limit", str(req.limit)]
    if req.regen:           cmd += ["--regen"]
    extra_env = {}
    cfg = req.provider_config
    if cfg.openrouter_api_key:
        extra_env["OPENROUTER_API_KEY"]  = cfg.openrouter_api_key
        extra_env["OPENROUTER_MODEL"]    = cfg.openrouter_model or "poolside/laguna-s-2.1:free"
    return _make_streaming_response(cmd, "gen-post-comment", extra_env=extra_env)


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
        loop = asyncio.get_event_loop()
        last_data = loop.time()
        KEEPALIVE_INTERVAL = 20  # giây — đủ ngắn để AWS ALB (60s idle) không cắt
        while True:
            try:
                item = line_queue.get_nowait()
            except queue.Empty:
                if loop.time() - last_data >= KEEPALIVE_INTERVAL:
                    yield ": keepalive\n\n"
                    last_data = loop.time()
                await asyncio.sleep(0.05)
                continue
            last_data = loop.time()
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
    col_message: str | None = None

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
async def linkedin_rows(req: LinkedInRowsRequest, _user: dict = Depends(require_auth)):
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
        result.append({
            "index": i,
            "name": name,
            "url": url,
            "already_crawled": already,
            "entityUrn": (row.get("entityUrn", "") or "").strip(),
            "connectStatus": (row.get("connectStatus", "") or "").strip(),
            "firstName": (row.get("firstName", "") or "").strip(),
            "message": (row.get(req.col_message, "") or "").strip() if req.col_message else "",
        })
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
            input_html=html,
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
async def linkedin_extract(req: LinkedInExtractRequest, _user: dict = Depends(require_auth)):
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
    # Debug: print first 500 chars of markdown để biết content có đúng không
    preview = markdown[:500].replace('\n', ' ')
    print(f"[linkedin-extract] markdown preview: {preview}")

    if len(markdown.strip()) < 100:
        return {"ok": False, "post": "", "error": "Markdown too short after conversion"}

    # Debug: save HTML + markdown ra /tmp khi cần inspect
    try:
        safe_name = (req.name or "unknown").replace(" ", "_").replace("/", "_")[:30]
        with open(f"/tmp/linkedin_debug_{safe_name}.html", "w", encoding="utf-8") as f:
            f.write(req.text)
        with open(f"/tmp/linkedin_debug_{safe_name}.md", "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"[linkedin-extract] saved debug files: /tmp/linkedin_debug_{safe_name}.*")
    except Exception:
        pass

    extractor = LinkedInPostExtractor(api_key=api_key)
    result = extractor.extract(markdown, html=req.text)
    post = result.get("post", "")
    print(f"[linkedin-extract] {req.name}: post={'yes' if post else 'empty'}")
    return {"ok": True, "post": post}


@app.post("/linkedin-write")
async def linkedin_write(req: LinkedInWriteRequest, _user: dict = Depends(require_auth)):
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


class AutoWriteResult(BaseModel):
    index: int
    col_header: str   # e.g. "Connect_Status" or "Message_Sent"
    col_value: str    # e.g. "pending" or "TRUE"

class AutoWriteRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    results: list[AutoWriteResult]

@app.post("/auto-write")
async def auto_write(req: AutoWriteRequest, _user: dict = Depends(require_auth)):
    """Ghi cột Connect_Status hoặc Message_Sent về sheet sau auto connect/message."""
    from src.sheets_writer import _get_client
    import gspread as _gspread

    if not req.results:
        return {"ok": True}

    try:
        client = _get_client()
        spreadsheet = client.open_by_key(req.spreadsheet_id)
        if req.gid is not None:
            sheet = spreadsheet.get_worksheet_by_id(req.gid)
        else:
            sheet = spreadsheet.worksheet(req.sheet_name or "Sheet1")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    headers = sheet.row_values(1)

    def _col_idx(header: str) -> int:
        if header in headers:
            return headers.index(header) + 1
        idx = len([h for h in headers if h]) + 1
        sheet.update_cell(1, idx, header)
        headers.append(header)
        return idx

    # Group by col_header to batch updates
    from collections import defaultdict
    by_col: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in req.results:
        by_col[r.col_header].append((r.index, r.col_value))

    try:
        for col_header, entries in by_col.items():
            col_idx = _col_idx(col_header)
            cells = [_gspread.Cell(idx + 2, col_idx, val) for idx, val in entries]
            sheet.update_cells(cells, value_input_option="RAW")

        url = f"https://docs.google.com/spreadsheets/d/{req.spreadsheet_id}/edit#gid={sheet.id}"
        print(f"[auto-write] wrote {len(req.results)} cell(s) → {url}")
        return {"ok": True, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/linkedin-sheet")
async def linkedin_sheet(req: LinkedInSheetRequest, _user: dict = Depends(require_auth)):
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


# ══════════════════════════════════════════════════════════════════════════════
# SALES INTELLIGENCE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ── Shared sheet helper ───────────────────────────────────────────────────────

def _open_sheet(spreadsheet_id: str, gid: int | None, sheet_name: str | None):
    """Mở worksheet, trả về (spreadsheet, sheet)."""
    from src.sheets_writer import _get_client
    import gspread as _gspread
    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    if gid is not None:
        sheet = spreadsheet.get_worksheet_by_id(gid)
    else:
        sheet = spreadsheet.worksheet(sheet_name or "Sheet1")
    return spreadsheet, sheet


def _ensure_col(sheet, headers: list[str], header: str) -> int:
    """Trả về index cột (1-based), tạo mới nếu chưa có."""
    if header in headers:
        return headers.index(header) + 1
    idx = len([h for h in headers if h]) + 1
    sheet.update_cell(1, idx, header)
    headers.append(header)
    return idx


# ── /find-email ───────────────────────────────────────────────────────────────

class FindEmailRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None
    col_name: str = "fullName"
    col_domain: str = "domain"          # cột chứa domain website công ty


@app.post("/find-email")
async def find_email_endpoint(req: FindEmailRequest, _user: dict = Depends(require_auth)):
    """
    Đọc sheet → tìm email từng lead → ghi cột Email_Found + Email_Confidence.
    Streaming SSE: mỗi dòng là 1 log, kết thúc bằng __EXIT__:0.
    """
    async def _generate():
        from src.sheets_writer import read_from_sheet
        from src.email_finder import find_emails_batch
        import gspread as _gs

        def _emit(text: str):
            return f"data: {text}\n\n"

        try:
            rows = read_from_sheet(
                spreadsheet_id=req.spreadsheet_id,
                gid=req.gid,
                sheet_name=req.sheet_name,
            )
            if req.limit:
                rows = rows[:req.limit]

            yield _emit(f"Đọc sheet: {len(rows)} dòng")

            results = find_emails_batch(rows, name_col=req.col_name, domain_col=req.col_domain)

            # Ghi kết quả vào sheet
            _, sheet = _open_sheet(req.spreadsheet_id, req.gid, req.sheet_name)
            headers = sheet.row_values(1)
            email_col = _ensure_col(sheet, headers, "Email_Found")
            conf_col  = _ensure_col(sheet, headers, "Email_Confidence")

            cells = []
            for r in results:
                if r.get("email"):
                    row_idx = r["index"] + 2
                    cells.append(_gs.Cell(row_idx, email_col, r["email"]))
                    cells.append(_gs.Cell(row_idx, conf_col, r["confidence"]))
                    yield _emit(f"✓ {rows[r['index']].get(req.col_name, '?')} → {r['email']} ({r['confidence']}%)")
                else:
                    yield _emit(f"– {rows[r['index']].get(req.col_name, '?')} → không tìm thấy")

            if cells:
                sheet.update_cells(cells, value_input_option="RAW")

            found = sum(1 for r in results if r.get("email"))
            yield _emit(f"✓ Hoàn tất: {found}/{len(results)} emails tìm thấy")
            yield "data: __EXIT__:0\n\n"

        except Exception as e:
            yield _emit(f"✗ Lỗi: {e}")
            yield "data: __EXIT__:1\n\n"

    from fastapi.responses import StreamingResponse as SR
    return SR(_generate(), media_type="text/event-stream")


# ── /score-leads ──────────────────────────────────────────────────────────────

class ScoreLeadsRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None
    col_name: str = "fullName"
    col_title: str = "title"
    col_company: str = "company"
    col_industry: str = "industry"
    col_post: str = "Bài Viết"
    regen: bool = False
    provider_config: ProviderConfig = ProviderConfig()


@app.post("/score-leads")
async def score_leads_endpoint(req: ScoreLeadsRequest, _user: dict = Depends(require_auth)):
    """
    Đọc sheet → AI chấm ICP score từng lead → ghi ICP_Score, ICP_Tier, ICP_Priority, ICP_Reason.
    Streaming SSE.
    """
    async def _generate():
        from src.sheets_writer import read_from_sheet
        from src.icp_scorer import ICPScorer
        import gspread as _gs

        def _emit(text: str):
            return f"data: {text}\n\n"

        try:
            rows = read_from_sheet(
                spreadsheet_id=req.spreadsheet_id,
                gid=req.gid,
                sheet_name=req.sheet_name,
            )
            if req.limit:
                rows = rows[:req.limit]

            # Lọc bỏ rows đã có điểm (nếu không regen)
            to_score = []
            for i, row in enumerate(rows):
                if not req.regen and row.get("ICP_Score"):
                    continue
                to_score.append({
                    "index":        i,
                    "name":         row.get(req.col_name, ""),
                    "title":        row.get(req.col_title, ""),
                    "company":      row.get(req.col_company, ""),
                    "industry":     row.get(req.col_industry, ""),
                    "recent_post":  row.get(req.col_post, ""),
                    "about":        row.get("about", ""),
                    "company_size": row.get("companySize", ""),
                })

            yield _emit(f"Cần chấm: {len(to_score)}/{len(rows)} leads")

            if not to_score:
                yield _emit("✓ Tất cả đã có điểm. Dùng regen=true để chấm lại.")
                yield "data: __EXIT__:0\n\n"
                return

            ai_router = _build_ai_router(req.provider_config)
            scorer = ICPScorer(ai_router=ai_router)
            _, sheet = _open_sheet(req.spreadsheet_id, req.gid, req.sheet_name)
            headers = sheet.row_values(1)
            score_col    = _ensure_col(sheet, headers, "ICP_Score")
            tier_col     = _ensure_col(sheet, headers, "ICP_Tier")
            priority_col = _ensure_col(sheet, headers, "ICP_Priority")
            reason_col   = _ensure_col(sheet, headers, "ICP_Reason")
            approach_col = _ensure_col(sheet, headers, "ICP_Approach")

            for i, lead in enumerate(to_score):
                result = scorer.score_lead(lead)
                row_idx = lead["index"] + 2

                cells = [
                    _gs.Cell(row_idx, score_col,    result.get("icp_score", 0)),
                    _gs.Cell(row_idx, tier_col,     result.get("tier", "D")),
                    _gs.Cell(row_idx, priority_col, result.get("priority", "Low")),
                    _gs.Cell(row_idx, reason_col,   result.get("reasons", "")),
                    _gs.Cell(row_idx, approach_col, result.get("suggested_approach", "")),
                ]
                sheet.update_cells(cells, value_input_option="RAW")

                score = result.get("icp_score", 0)
                tier  = result.get("tier", "?")
                name  = lead.get("name", "?")
                yield _emit(f"[{i+1}/{len(to_score)}] {name} → {score}/100 Tier {tier} | {result.get('reasons', '')[:80]}")

            yield _emit(f"✓ Hoàn tất chấm điểm {len(to_score)} leads")
            yield "data: __EXIT__:0\n\n"

        except Exception as e:
            yield _emit(f"✗ Lỗi: {e}")
            yield "data: __EXIT__:1\n\n"

    from fastapi.responses import StreamingResponse as SR
    return SR(_generate(), media_type="text/event-stream")


# ── /lead-status ──────────────────────────────────────────────────────────────

VALID_STATUSES = ["cold", "contacted", "replied", "meeting", "proposal", "closed_won", "closed_lost", "nurturing"]

class LeadStatusRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None


class LeadStatusUpdateRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    updates: list[dict]   # [{ index, status, note? }]


@app.post("/lead-status")
async def get_lead_statuses(req: LeadStatusRequest, _user: dict = Depends(require_auth)):
    """Đọc tất cả lead và trạng thái hiện tại — trả về summary + list."""
    from src.sheets_writer import read_from_sheet
    from collections import Counter

    try:
        rows = read_from_sheet(
            spreadsheet_id=req.spreadsheet_id,
            gid=req.gid,
            sheet_name=req.sheet_name,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

    leads = []
    for i, row in enumerate(rows):
        leads.append({
            "index":     i,
            "name":      row.get("fullName", f"Row {i+1}"),
            "company":   row.get("company", ""),
            "title":     row.get("title", ""),
            "status":    row.get("Lead_Status", "cold"),
            "icp_score": row.get("ICP_Score", ""),
            "icp_tier":  row.get("ICP_Tier", ""),
            "note":      row.get("Lead_Note", ""),
            "email":     row.get("Email_Found", ""),
        })

    status_counts = Counter(l["status"] or "cold" for l in leads)
    return {
        "ok":     True,
        "total":  len(leads),
        "leads":  leads,
        "summary": dict(status_counts),
    }


@app.post("/lead-status/update")
async def update_lead_statuses(req: LeadStatusUpdateRequest, _user: dict = Depends(require_auth)):
    """Cập nhật Lead_Status (và Lead_Note) cho các row được chọn."""
    import gspread as _gs

    if not req.updates:
        return {"ok": True}

    try:
        _, sheet = _open_sheet(req.spreadsheet_id, req.gid, req.sheet_name)
        headers  = sheet.row_values(1)
        status_col = _ensure_col(sheet, headers, "Lead_Status")
        note_col   = _ensure_col(sheet, headers, "Lead_Note")

        cells = []
        for u in req.updates:
            row_idx = u["index"] + 2
            status  = u.get("status", "cold")
            note    = u.get("note", "")
            cells.append(_gs.Cell(row_idx, status_col, status))
            if note:
                cells.append(_gs.Cell(row_idx, note_col, note))

        sheet.update_cells(cells, value_input_option="RAW")
        return {"ok": True, "updated": len(req.updates)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-PROVIDER ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


def _build_email_enricher(cfg: ProviderConfig):
    from src.providers.email_providers import EmailEnricher
    return EmailEnricher.from_config({
        "providers":         cfg.email_providers,
        "hunter_api_key":    cfg.hunter_api_key,
        "apollo_api_key":    cfg.apollo_api_key,
        "snov_client_id":    cfg.snov_client_id,
        "snov_client_secret":cfg.snov_client_secret,
    })


def _build_ai_router(cfg: ProviderConfig):
    from src.providers.ai_providers import AIRouter
    return AIRouter.from_config({
        "providers":          cfg.ai_providers,
        "deepseek_api_key":   cfg.deepseek_api_key,
        "openai_api_key":     cfg.openai_api_key,
        "claude_api_key":     cfg.claude_api_key,
        "gemini_api_key":     cfg.gemini_api_key,
        "openrouter_api_key": cfg.openrouter_api_key,
        "openai_model":       cfg.openai_model,
        "claude_model":       cfg.claude_model,
        "openrouter_model":   cfg.openrouter_model,
    })


def _build_crm_syncer(cfg: ProviderConfig):
    from src.providers.crm_providers import CRMSyncer
    return CRMSyncer.from_config({
        "providers":          cfg.crm_providers,
        "hubspot_api_key":    cfg.hubspot_api_key,
        "notion_token":       cfg.notion_token,
        "notion_database_id": cfg.notion_database_id,
    })


# ── GET /providers/status ─────────────────────────────────────────────────────

@app.post("/providers/status")
async def providers_status(cfg: ProviderConfig, _user: dict = Depends(require_auth)):
    """Trả về trạng thái configured/not của từng provider."""
    email_enricher = _build_email_enricher(cfg)
    ai_router      = _build_ai_router(cfg)
    crm_syncer     = _build_crm_syncer(cfg)
    return {
        "ok":    True,
        "email": email_enricher.status(),
        "ai":    ai_router.status(),
        "crm":   crm_syncer.status(),
    }


# ── POST /providers/test ──────────────────────────────────────────────────────

class TestProviderRequest(BaseModel):
    provider: str   # e.g. "hunter", "openai", "hubspot"
    cfg: ProviderConfig = ProviderConfig()


@app.post("/providers/test")
async def test_provider(req: TestProviderRequest, _user: dict = Depends(require_auth)):
    """Test kết nối 1 provider cụ thể."""
    p = req.provider.lower()
    cfg = req.cfg
    try:
        if p == "hunter":
            from src.providers.email_providers import HunterProvider
            return HunterProvider(cfg.hunter_api_key).test_connection()
        if p == "apollo":
            from src.providers.email_providers import ApolloProvider
            return ApolloProvider(cfg.apollo_api_key).test_connection()
        if p == "snov":
            from src.providers.email_providers import SnovProvider
            return SnovProvider(cfg.snov_client_id, cfg.snov_client_secret).test_connection()
        if p == "pattern":
            from src.providers.email_providers import PatternProvider
            return PatternProvider().test_connection()
        if p == "deepseek":
            from src.providers.ai_providers import DeepSeekProvider
            return DeepSeekProvider(cfg.deepseek_api_key).test_connection()
        if p == "openai":
            from src.providers.ai_providers import OpenAIProvider
            return OpenAIProvider(cfg.openai_api_key, cfg.openai_model).test_connection()
        if p == "claude":
            from src.providers.ai_providers import ClaudeProvider
            return ClaudeProvider(cfg.claude_api_key, cfg.claude_model).test_connection()
        if p == "gemini":
            from src.providers.ai_providers import GeminiProvider
            return GeminiProvider(cfg.gemini_api_key).test_connection()
        if p == "openrouter":
            from src.providers.ai_providers import OpenRouterProvider
            return OpenRouterProvider(cfg.openrouter_api_key, cfg.openrouter_model).test_connection()
        if p == "hubspot":
            from src.providers.crm_providers import HubSpotProvider
            return HubSpotProvider(cfg.hubspot_api_key).test_connection()
        if p == "notion":
            from src.providers.crm_providers import NotionProvider
            return NotionProvider(cfg.notion_token, cfg.notion_database_id).test_connection()
        return {"ok": False, "message": f"Unknown provider: {p}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── POST /crm/sync ────────────────────────────────────────────────────────────

class CRMSyncRequest(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None
    provider_config: ProviderConfig = ProviderConfig()


@app.post("/crm/sync")
async def crm_sync(req: CRMSyncRequest, _user: dict = Depends(require_auth)):
    """
    Đọc sheet → map sang CRMContact → push tới các CRM providers.
    Streaming SSE.
    """
    async def _generate():
        from src.sheets_writer import read_from_sheet
        from src.providers.crm_providers import CRMContact

        def emit(text: str): return f"data: {text}\n\n"

        try:
            rows = read_from_sheet(
                spreadsheet_id=req.spreadsheet_id,
                gid=req.gid, sheet_name=req.sheet_name,
            )
            if req.limit: rows = rows[:req.limit]
            yield emit(f"Đọc sheet: {len(rows)} rows")

            crm = _build_crm_syncer(req.provider_config)
            if not crm.providers:
                yield emit("⚠ Không có CRM provider nào được cấu hình")
                yield "data: __EXIT__:1\n\n"; return

            contacts = []
            for i, row in enumerate(rows):
                contacts.append(CRMContact(
                    name=row.get("fullName", ""),
                    email=row.get("Email_Found", "") or row.get("email", ""),
                    title=row.get("title", ""),
                    company=row.get("company", ""),
                    linkedin_url=row.get("linkedUrl", ""),
                    status=row.get("Lead_Status", "cold"),
                    icp_score=int(row.get("ICP_Score", 0) or 0),
                    icp_tier=row.get("ICP_Tier", ""),
                    notes=row.get("ICP_Reason", ""),
                    source_row=i,
                ))

            results = crm.sync(contacts)
            for r in results:
                yield emit(f"✓ {r.provider}: created={r.created} updated={r.updated} errors={len(r.errors)}")
                for err in r.errors[:5]:
                    yield emit(f"  ✗ {err}")

            yield emit(f"✓ CRM sync hoàn tất")
            yield "data: __EXIT__:0\n\n"
        except Exception as e:
            yield emit(f"✗ {e}")
            yield "data: __EXIT__:1\n\n"

    from fastapi.responses import StreamingResponse as SR
    return SR(_generate(), media_type="text/event-stream")


# ── POST /find-email với multi-provider ───────────────────────────────────────
# Override endpoint cũ để dùng EmailEnricher

class FindEmailV2Request(BaseModel):
    spreadsheet_id: str
    gid: int | None = None
    sheet_name: str | None = None
    limit: int | None = None
    col_name: str = "fullName"
    col_domain: str = "domain"
    provider_config: ProviderConfig = ProviderConfig()


@app.post("/find-email/v2")
async def find_email_v2(req: FindEmailV2Request, _user: dict = Depends(require_auth)):
    """Email finder dùng multi-provider waterfall."""
    async def _generate():
        from src.sheets_writer import read_from_sheet
        import gspread as _gs

        def emit(t): return f"data: {t}\n\n"
        try:
            rows = read_from_sheet(
                spreadsheet_id=req.spreadsheet_id,
                gid=req.gid, sheet_name=req.sheet_name,
            )
            if req.limit: rows = rows[:req.limit]
            yield emit(f"Đọc sheet: {len(rows)} dòng")

            enricher = _build_email_enricher(req.provider_config)
            active = [p["name"] for p in enricher.status() if p["configured"]]
            yield emit(f"Providers: {' → '.join(active)}")

            _, sheet = _open_sheet(req.spreadsheet_id, req.gid, req.sheet_name)
            headers   = sheet.row_values(1)
            email_col = _ensure_col(sheet, headers, "Email_Found")
            conf_col  = _ensure_col(sheet, headers, "Email_Confidence")
            src_col   = _ensure_col(sheet, headers, "Email_Source")

            cells = []; found = 0
            for i, row in enumerate(rows):
                name   = str(row.get(req.col_name, "") or "").strip()
                domain = str(row.get(req.col_domain, "") or "").strip()
                if not name or not domain:
                    yield emit(f"– [{i+1}] bỏ qua (thiếu name/domain)"); continue

                result = enricher.find(name, domain)
                row_idx = i + 2
                if result.email:
                    found += 1
                    cells += [
                        _gs.Cell(row_idx, email_col, result.email),
                        _gs.Cell(row_idx, conf_col,  result.confidence),
                        _gs.Cell(row_idx, src_col,   result.source),
                    ]
                    yield emit(f"✓ [{i+1}] {name} → {result.email} ({result.confidence}% via {result.source})")
                else:
                    yield emit(f"– [{i+1}] {name} @ {domain} → không tìm thấy")

            if cells: sheet.update_cells(cells, value_input_option="RAW")
            yield emit(f"✓ Hoàn tất: {found}/{len(rows)} emails")
            yield "data: __EXIT__:0\n\n"
        except Exception as e:
            yield emit(f"✗ {e}")
            yield "data: __EXIT__:1\n\n"

    from fastapi.responses import StreamingResponse as SR
    return SR(_generate(), media_type="text/event-stream")
