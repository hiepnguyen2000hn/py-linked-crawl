# 🔑 LinkedIn Cookies Setup Guide

## ⚠️ Tại sao cần cookies?

LinkedIn **chặn tất cả anonymous crawling** → redirect về login page.

Để crawl LinkedIn profiles/posts, bạn **BẮT BUỘC** phải cung cấp authenticated cookies từ một session đã đăng nhập.

---

## 📋 Cách lấy LinkedIn Cookies

### **Method 1: Chrome Extension (Recommended)**

1. Install extension: [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/) hoặc [Cookie-Editor](https://cookie-editor.com/)

2. Đăng nhập LinkedIn trên Chrome

3. Mở extension → Export cookies → format JSON

4. Copy cookies và pass vào API request:

```bash
curl -X POST http://localhost:3006/linkedin-sheet \
  -H "Content-Type: application/json" \
  -d '{
    "spreadsheet_id": "YOUR_SHEET_ID",
    "gid": 0,
    "limit": 5,
    "cookies": [
      {"name": "li_at", "value": "YOUR_LI_AT_COOKIE", "domain": ".linkedin.com"},
      {"name": "JSESSIONID", "value": "ajax:...", "domain": ".linkedin.com"}
    ]
  }'
```

---

### **Method 2: Chrome DevTools (Manual)**

1. Đăng nhập LinkedIn

2. Mở DevTools (F12) → tab **Application** → **Cookies** → https://www.linkedin.com

3. Copy các cookies quan trọng:
   - `li_at` (authentication token) ← **REQUIRED**
   - `JSESSIONID` (session ID)
   - `li_a` (additional auth)

4. Format thành JSON:

```json
[
  {
    "name": "li_at",
    "value": "AQEDATk...ABC123",
    "domain": ".linkedin.com",
    "path": "/",
    "secure": true,
    "httpOnly": true,
    "sameSite": "None"
  },
  {
    "name": "JSESSIONID",
    "value": "ajax:1234567890",
    "domain": ".www.linkedin.com",
    "path": "/",
    "secure": true,
    "sameSite": "Lax"
  }
]
```

---

### **Method 3: Python Script (Auto Extract)**

```python
# get_linkedin_cookies.py
from playwright.sync_api import sync_playwright

# 1. Login manually
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    
    # Open LinkedIn login
    page.goto("https://www.linkedin.com/login")
    
    # WAIT for you to login manually
    input("⏸️  Please login to LinkedIn, then press ENTER...")
    
    # Extract cookies
    cookies = context.cookies()
    
    # Filter LinkedIn cookies
    linkedin_cookies = [
        c for c in cookies 
        if "linkedin.com" in c["domain"]
    ]
    
    # Save to file
    import json
    with open("linkedin_cookies.json", "w") as f:
        json.dump(linkedin_cookies, f, indent=2)
    
    print(f"✅ Saved {len(linkedin_cookies)} cookies to linkedin_cookies.json")
    browser.close()
```

Run:
```bash
python get_linkedin_cookies.py
# → login manually → cookies saved to linkedin_cookies.json
```

---

## 🚀 Usage

### **API Request (with cookies)**

```bash
curl -X POST http://localhost:3006/linkedin-sheet \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "spreadsheet_id": "1_xMd_SRtTGjI8lbZpMhnnC8qTPERvtMz7UVVVF18_jE",
  "gid": 220354328,
  "limit": 5,
  "cookies": $(cat linkedin_cookies.json)
}
EOF
```

---

### **CLI (with env var)**

```bash
# Set cookies via env var
export LINKEDIN_COOKIES_JSON=$(cat linkedin_cookies.json)

# Run crawl
python from_sheet_linkedin.py \
  --spreadsheet-id "1_xMd_SRtTGjI8lbZpMhnnC8qTPERvtMz7UVVVF18_jE" \
  --gid 220354328 \
  --limit 5
```

---

## 🔒 Security Notes

### **⚠️ IMPORTANT: Keep cookies private!**

- `li_at` cookie = full access to your LinkedIn account
- **DO NOT** commit cookies to git
- **DO NOT** share cookies publicly
- Add to `.gitignore`:
  ```
  linkedin_cookies.json
  *_cookies*.json
  ```

### **Cookie Lifespan**

- LinkedIn cookies expire after ~1 month
- When crawl fails → re-export fresh cookies

---

## 🧪 Testing

### **Test 1: Check if cookies work**

```bash
python3 << 'EOF'
import json, os
from from_sheet_linkedin import _crawl_with_playwright_cookies

# Load cookies
with open("linkedin_cookies.json") as f:
    cookies = json.load(f)

# Test crawl
url = "https://www.linkedin.com/in/johnny-pronk/recent-activity/all/"
content, html = _crawl_with_playwright_cookies(url, cookies)

print(f"✓ Crawled {len(html)} chars HTML")
print(f"✓ Extracted {len(content)} chars text")

# Check if got real content (not authwall)
if "authwall" in html.lower():
    print("❌ FAIL: Got auth wall → cookies invalid/expired")
else:
    print("✅ SUCCESS: Cookies working!")
EOF
```

---

### **Test 2: Extract posts**

```bash
python test_extract_posts.py /tmp/linkedin_crawled.html
```

Expected output:
```
📄 HTML file: /tmp/linkedin_crawled.html
📏 Size: 405,691 chars

🔍 Found 50 elements with data-urn attribute
   - 15 with urn:li:activity: (posts)

📋 Sample URNs:
   • urn:li:activity:7123456789012345678
   • urn:li:activity:7098765432109876543
   ...

🚀 Running extract_posts_with_metadata()...

✅ RESULT: Extracted 3 posts

  Post 1:
    Type: post
    ActivityId: 7123456789012345678
    URL: https://www.linkedin.com/feed/update/urn:li:activity:7123456789012345678
    Has content: True
```

---

## 🐛 Troubleshooting

### **Problem: "Empty content" / "Post: (empty)"**

**Cause:** No cookies or expired cookies

**Fix:**
1. Check cookies exist: `echo $LINKEDIN_COOKIES_JSON` or check API request body
2. Re-export fresh cookies from browser
3. Verify cookies include `li_at` token

---

### **Problem: "LinkedIn auth wall"**

**Cause:** Cookies not passed to Playwright context

**Fix:**
1. Check `_load_cookies_from_env()` returns non-empty list
2. Check `LINKEDIN_COOKIES_JSON` env var is set
3. For API: check `req.cookies` is passed in request body

---

### **Problem: "Extracted 0 posts"**

**Possible causes:**

1. **HTML structure changed** → update regex patterns in `extract_posts_with_metadata()`
   - Run `python test_extract_posts.py <html_file>` to debug

2. **User has no posts** → check LinkedIn profile manually

3. **Private profile** → cookies account needs to be connected with target user

---

## 📚 Related Files

- `from_sheet_linkedin.py` - Main crawl logic
- `src/linkedin_post_extractor.py` - Post extraction + classification
- `server.py` - API endpoints (`/linkedin-sheet`, `/linkedin-extract`)
- `test_extract_posts.py` - Debug tool for HTML analysis

---

**Last updated:** 2026-07-07
