# from_sheet.py — Command Reference

Script đọc danh sách công ty từ Google Sheet, crawl website, trích xuất
5 trường thông tin bằng DeepSeek AI, rồi ghi kết quả vào tab "Enriched"
trong cùng spreadsheet.

## Yêu cầu môi trường (.env)

```env
DEEPSEEK_API_KEY=sk-...

# Google Sheets — chọn 1 trong 2:
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service_account.json
# hoặc OAuth2 (sẽ mở trình duyệt lần đầu):
GOOGLE_OAUTH_CLIENT_SECRET=client_secret.json
```

## Cột bắt buộc trong sheet nguồn

| Cột | Mô tả |
|-----|-------|
| `company_name` | Tên công ty (dùng để log) |
| `website` | URL website đầy đủ (https://...) |

Tên cột có thể tùy chỉnh bằng `--col-name` và `--col-website`.

## Các cột được thêm vào sheet Enriched

| Cột mới | Key DeepSeek | Mô tả |
|---------|-------------|-------|
| Tuyển Dụng | `tuyen_dung` | Vị trí đang tuyển, link careers |
| Blog | `blog` | Link trang blog / bài viết gần nhất |
| Lĩnh Vực | `linh_vuc` | Lĩnh vực hoạt động chính |
| Dự Án Gần Nhất | `du_an_gan_nhat` | Tên + mô tả ngắn dự án/sản phẩm gần nhất |
| Đối Tác | `doi_tac` | Danh sách đối tác / khách hàng nổi bật |

## Lệnh thường dùng

### Sheet thực tế — dùng GID (khuyến nghị)

```bash
# Spreadsheet ID: 19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E
# GID của tab nguồn: 1566842879 (lấy từ URL #gid=1566842879)

python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --gid 1566842879 \
  --output-sheet "Enriched"
```

### Test nhanh 3 hàng đầu

```bash
python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --gid 1566842879 \
  --limit 3
```

### Chỉ định tab theo tên (nếu biết tên tab)

```bash
python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --sheet-name "Sheet1" \
  --output-sheet "Enriched_Apr2026"
```

### Tên cột khác với mặc định

```bash
python from_sheet.py \
  --spreadsheet-id "19lz3Bhc0A9HwMIhlOEQ0ICcFljkxQyUE6BPf78HTl-E" \
  --gid 1566842879 \
  --col-website "website" \
  --col-name "company_name" \
  --delay 3.0
```

## Cách lấy Spreadsheet ID

Từ URL Google Sheet:
```
https://docs.google.com/spreadsheets/d/1PW5LnQyXjyl0h16ooufYNYjR1_eb8DgfnCEGLNjsf10/edit
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       đây là spreadsheet ID
```

## Tất cả flags

| Flag | Mặc định | Mô tả |
|------|----------|-------|
| `--spreadsheet-id` | bắt buộc | ID của Google Spreadsheet |
| `--gid` | — | GID số của tab (từ URL `#gid=<số>`) — ưu tiên hơn `--sheet-name` |
| `--sheet-name` | — | Tên tab nguồn (dùng nếu không có `--gid`) |
| `--col-website` | `website` | Tên cột chứa URL website |
| `--col-name` | `company_name` | Tên cột chứa tên công ty |
| `--output-sheet` | `Enriched` | Tab output trong cùng spreadsheet |
| `--delay` | `1.0` | Delay (giây) giữa các công ty |
| `--limit` | `0` (tất cả) | Chỉ xử lý N hàng đầu |
