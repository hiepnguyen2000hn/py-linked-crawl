# Company Crawler — Hướng dẫn sử dụng

Công cụ crawl thông tin công ty theo địa điểm và ngành nghề, hỗ trợ nhiều nguồn dữ liệu, trích xuất lãnh đạo bằng AI, và xuất kết quả ra file hoặc Google Sheets.

---

## Yêu cầu môi trường

Tạo file `.env` ở thư mục gốc:

```env
GOOGLE_PLACES_API_KEY=...       # Dùng khi --source google (mặc định)
SERPAPI_KEY=...                  # Dùng khi --source serpapi hoặc --enrich-linkedin
DEEPSEEK_API_KEY=...             # Dùng khi --extractor deepseek

# Google Sheets (chọn 1 trong 2)
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service_account.json
GOOGLE_OAUTH_CLIENT_SECRET=client_secret.json   # mặc định nếu không có SA
```

---

## Cú pháp chung

```bash
python main.py [--url URL] [--location LOC] [--industry IND] [OPTIONS]
```

`--location` và `--industry` bắt buộc trừ khi dùng `--url`.

---

## Các lệnh thường dùng

### 1. Tìm & crawl công ty theo địa điểm + ngành (Google Places)

```bash
python main.py --location "Ho Chi Minh" --industry "ecommerce"
```

Kết quả: file `companies_ho_chi_minh_ecommerce_<timestamp>.json`

---

### 2. Dùng SerpAPI thay Google Places

```bash
python main.py --location "Vietnam" --industry "fintech" --source serpapi
```

---

### 3. Nhiều trang kết quả (mỗi trang ~20 công ty)

```bash
python main.py --location "Hanoi" --industry "logistics" --source serpapi --pages 3
```

Lấy ~60 công ty (trang 1–3).

```bash
python main.py --location "Hanoi" --industry "logistics" --source serpapi --pages 2 --start-page 3
```

Bỏ qua 40 kết quả đầu, lấy trang 3–4.

---

### 4. Xuất markdown (dùng crawl4ai để crawl nội dung website)

```bash
python main.py --location "Ho Chi Minh" --industry "mining" --source serpapi --format markdown
```

Kết quả: thư mục `companies_ho_chi_minh_mining_<timestamp>/` chứa file `.md` cho từng công ty.

---

### 5. Chỉ lấy danh sách, không crawl website

```bash
python main.py --location "Da Nang" --industry "tourism" --no-crawl
```

---

### 6. Trích xuất lãnh đạo bằng DeepSeek AI

```bash
python main.py --location "Ho Chi Minh" --industry "tech" --source serpapi \
  --format markdown --extract --extractor deepseek
```

Yêu cầu `DEEPSEEK_API_KEY` trong `.env`.

---

### 7. Trích xuất lãnh đạo bằng model local (Qwen/IE)

```bash
python main.py --location "Ho Chi Minh" --industry "tech" --source serpapi \
  --format markdown --extract --extractor qwen
```

---

### 8. Tự động bổ sung LinkedIn cá nhân cho lãnh đạo

```bash
python main.py --location "Ho Chi Minh" --industry "tech" --source serpapi \
  --format markdown --extract --extractor deepseek --enrich-linkedin
```

Yêu cầu cả `DEEPSEEK_API_KEY` và `SERPAPI_KEY`.

---

### 9. Lưu kết quả lên Google Sheets

```bash
python main.py --location "Ho Chi Minh" --industry "ecommerce" --sheets
```

Ghi vào tab `Sheet1` mặc định trong spreadsheet được cấu hình.

```bash
python main.py --location "Ho Chi Minh" --industry "ecommerce" --sheets --sheet-name "HCM_Ecommerce"
```

Ghi vào tab tên `HCM_Ecommerce` (tạo mới nếu chưa có).

---

### 10. Crawl 1 URL cụ thể (không cần SerpAPI / Places)

```bash
python main.py --url https://example.com
```

Tự động khám phá các trang about/team/leadership và lưu file markdown.

```bash
python main.py --url https://example.com --extract --extractor deepseek
```

Crawl + trích xuất lãnh đạo bằng DeepSeek.

---

### 11. Chỉ định thư mục output

```bash
python main.py --location "Hanoi" --industry "edu" --output-dir ./results
```

---

## Script bổ sung

### Enrich LinkedIn cho file JSON có sẵn

```bash
python enrich_linkedin.py companies_hanoi_edu_20260101_120000.json
```

```bash
python enrich_linkedin.py companies_hanoi_edu_20260101_120000.json --sheets --sheet-name "Edu_Hanoi"
```

---

### Đọc từ Google Sheet → crawl website → DeepSeek extract 5 trường công ty

```bash
python from_sheet.py --spreadsheet-id SHEET_ID --sheet-name "Sheet1" \
  --col-website "Website" --output-sheet "Enriched"
```

> Đọc danh sách công ty từ sheet, crawl website, chạy DeepSeek, ghi 5 cột mới (Tuyển Dụng, Blog, Lĩnh Vực, Dự Án Gần Nhất, Đối Tác) vào tab nguồn.

---

### Crawl LinkedIn profile → DeepSeek extract 3 bài viết gần nhất

```bash
python from_sheet_linkedin.py --spreadsheet-id SHEET_ID --gid 0
```

Lệnh đầy đủ với sheet cụ thể:

```bash
python from_sheet_linkedin.py --spreadsheet-id 1nmyj76On7Sc33N9OSf3l6u9gNJMPBWAWjQIS8P3iSt8 --gid 0
```

Test thử 3 hàng đầu:

```bash
python from_sheet_linkedin.py --spreadsheet-id 1nmyj76On7Sc33N9OSf3l6u9gNJMPBWAWjQIS8P3iSt8 --gid 0 --limit 3
```

| Flag | Mặc định | Mô tả |
|------|----------|-------|
| `--spreadsheet-id` | bắt buộc | ID của Google Spreadsheet |
| `--gid` | — | GID số của tab (từ URL `#gid=...`) |
| `--sheet-name` | — | Tên tab (thay thế cho `--gid`) |
| `--col-linkedin` | `linkedUrl` | Tên cột chứa LinkedIn URL |
| `--col-name` | `fullName` | Tên cột chứa tên người dùng |
| `--limit` | `0` (tất cả) | Chỉ xử lý N hàng đầu |
| `--delay` | `2.0` | Giây nghỉ giữa các request |

> Ghi 2 cột mới vào tab nguồn:
> - **Bài Viết** — tóm tắt 3 bài viết gần nhất, URL trong ô thành hyperlink xanh
> - **Đã Crawl** — checkbox TRUE/FALSE; hàng đã TRUE sẽ được skip ở lần chạy tiếp theo

---

### Full enrich: LinkedIn jobs + website crawl (2 luồng, 1 lệnh)

```bash
python from_sheet_full_enrich.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147
```

Test 3 hàng:

```bash
python from_sheet_full_enrich.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147 --limit 3
```

> Ghi **6 cột mới** vào tab nguồn:
> - **tuyển d** — job titles từ LinkedIn `/jobs/`
> - **Blog** — bài viết/news từ website
> - **Lĩnh Vực** — ngành hoạt động
> - **Dự Án Gần Nhất** — sản phẩm/dự án mới nhất
> - **Đối Tác** — đối tác/khách hàng nổi bật
> - **Đã Enrich** — checkbox TRUE/FALSE, hàng TRUE sẽ skip ở lần chạy tiếp

---

### Crawl LinkedIn company jobs → extract tất cả job đang tuyển

```bash
python from_sheet_linkedin_jobs.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147
```

Test thử 3 hàng đầu:

```bash
python from_sheet_linkedin_jobs.py --spreadsheet-id 1G0AHHUay-LDr4wW5z3zI10T2-7wFmDMvq4m0WV-6S3s --gid 1694881147 --limit 3
```

| Flag | Mặc định | Mô tả |
|------|----------|-------|
| `--col-linkedin` | `linkedin_url` | Tên cột chứa LinkedIn company URL |
| `--col-jobs` | `tuyển d` | Tên cột ghi kết quả jobs |
| `--limit` | `0` (tất cả) | Chỉ xử lý N hàng đầu |
| `--delay` | `2.0` | Giây nghỉ giữa các request |

> Flow: crawl4ai → markdown → DeepSeek extract job titles → ghi cột **tuyển d**
> Cột **Đã Crawl Jobs** (checkbox) tự động tick TRUE sau khi crawl xong.

---

## Tổng hợp flags

| Flag | Mặc định | Mô tả |
|------|----------|-------|
| `--url` | — | Crawl 1 URL trực tiếp, bỏ qua search |
| `--location` | bắt buộc | Địa điểm tìm kiếm |
| `--industry` | bắt buộc | Ngành nghề |
| `--source` | `google` | Nguồn: `google` hoặc `serpapi` |
| `--format` | `json` | Output: `json` hoặc `markdown` |
| `--output-dir` | `.` | Thư mục lưu kết quả |
| `--no-crawl` | false | Bỏ qua bước crawl website |
| `--pages` | `1` | Số trang SerpAPI (~20 kết quả/trang) |
| `--start-page` | `1` | Trang bắt đầu (bỏ qua kết quả trước đó) |
| `--extract` | false | Bật trích xuất lãnh đạo bằng AI |
| `--extractor` | `qwen` | Model: `qwen` (local) hoặc `deepseek` (API) |
| `--enrich-linkedin` | false | Tìm LinkedIn cá nhân qua SerpAPI |
| `--sheets` | false | Ghi kết quả lên Google Sheets |
| `--sheet-name` | `Sheet1` | Tên tab trong Google Sheet |
