# LinkedIn Crawl Logic Update

## 📋 Tổng quan thay đổi

### ✅ Đã cập nhật:

1. **Luôn dùng Crawl4AI để convert HTML → Markdown** (tối ưu context cho DeepSeek)
2. **Phân loại 3 loại bài viết LinkedIn:**
   - `post`: Bài viết gốc của user
   - `repost`: Reshare thuần túy (không có comment)
   - `repost_with_thought`: Reshare có kèm suy nghĩ/bình luận
3. **Extract đúng URL và activityId** từ HTML
4. **Format output mới** với đầy đủ metadata

---

## 🔄 Luồng xử lý mới

```
┌─────────────────────────────────────────────────────────────┐
│  1. URL từ Sheet → Playwright (authenticated) → Raw HTML    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ├─ Raw HTML retained (for metadata extraction)
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│  2. Crawl4AI Markdown Generator: HTML → Clean Markdown      │
│     • PruningContentFilter: remove noise                    │
│     • Optimize context for DeepSeek                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ↓                             ↓
┌──────────────────┐        ┌─────────────────────┐
│  3a. Extract     │        │  3b. DeepSeek:      │
│  Post Metadata   │        │  Extract Content    │
│  from HTML       │        │  from Markdown      │
│                  │        │                     │
│  • type          │        │  • type             │
│  • activityId    │        │  • date             │
│  • url           │        │  • content          │
└────────┬─────────┘        └──────────┬──────────┘
         │                             │
         └──────────────┬──────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  4. Merge: HTML metadata + DeepSeek content                 │
│     → Full post info with type, activityId, URL, content    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Output Format Mới

### **API Response** (`/linkedin-extract`):

```json
{
  "ok": true,
  "posts": [
    {
      "type": "post",
      "activityId": "7123456789012345678",
      "url": "https://www.linkedin.com/feed/update/urn:li:activity:7123456789012345678",
      "date": "3mo",
      "content": "When it comes to writing - of all kinds (including textbooks!) people know what they like to read. It isn't AI generated."
    },
    {
      "type": "repost_with_thought",
      "activityId": "7098765432109876543",
      "url": "https://www.linkedin.com/feed/update/urn:li:activity:7098765432109876543",
      "date": "6mo",
      "content": "This is exactly what we've been working on! Great insights from the team."
    },
    {
      "type": "repost",
      "activityId": "7111111111111111111",
      "url": "https://www.linkedin.com/feed/update/urn:li:activity:7111111111111111111",
      "date": "1yr",
      "content": ""
    }
  ]
}
```

### **Google Sheet Format** (cột "Bài Viết"):

```
• [POST] 3mo: When it comes to writing - of all kinds (including textbooks!) people know what they like to read. It isn't AI generated.
  [linkPost: https://www.linkedin.com/feed/update/urn:li:activity:7123456789012345678]
  [activityId: 7123456789012345678]

• [REPOST+] 6mo: This is exactly what we've been working on! Great insights from the team.
  [linkPost: https://www.linkedin.com/feed/update/urn:li:activity:7098765432109876543]
  [activityId: 7098765432109876543]

• [REPOST] 1yr: 
  [linkPost: https://www.linkedin.com/feed/update/urn:li:activity:7111111111111111111]
  [activityId: 7111111111111111111]
```

---

## 🔧 Chi tiết kỹ thuật

### **1. HTML → Markdown Conversion** (luôn dùng Crawl4AI)

**File:** `from_sheet_linkedin.py:_crawl_linkedin()`

```python
# Step 1: Playwright crawl → raw HTML
raw_text, raw_html = _crawl_with_playwright_cookies(url, cookies)

# Step 2: Crawl4AI convert HTML → Markdown
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

generator = DefaultMarkdownGenerator(
    content_filter=PruningContentFilter(),
    options={"ignore_links": False, "ignore_images": False},
)
result = generator.generate_markdown(
    cleaned_html=raw_html,
    base_url="https://www.linkedin.com",
)
markdown = result.fit_markdown or result.raw_markdown
```

**Lợi ích:**
- ✅ Loại bỏ noise HTML (ads, tracking, navigation)
- ✅ Tối ưu context cho DeepSeek (compact hơn raw HTML)
- ✅ Giữ nguyên structure quan trọng (posts, comments, reshares)

---

### **2. Phân loại Post Type** 

**File:** `src/linkedin_post_extractor.py:extract_posts_with_metadata()`

**Logic phân loại:**

```python
# Tìm commentary (text do user viết)
commentary_elem = elem.find(class_=re.compile(r"feed-shared-update-v2__commentary"))

# Tìm reshare indicator (X reposted this)
reshare_elem = elem.find(class_=re.compile(r"feed-shared-actor__description"))
is_reshare = "reposted" in reshare_elem.get_text().lower()

# Phân loại
if commentary_elem and has_content:
    if is_reshare:
        post_type = "repost_with_thought"  # có comment + là reshare
    else:
        post_type = "post"                 # có content + không reshare
elif shared_content_elem:
    post_type = "repost"                   # không có comment → pure repost
```

**Class selectors LinkedIn:**
- `feed-shared-update-v2__commentary`: Text user viết (original post hoặc repost comment)
- `feed-shared-actor__description`: "X reposted this" indicator
- `feed-shared-update-v2__description`: Nội dung bài gốc được reshare

---

### **3. Extract activityId**

```python
urn = elem.get("data-urn", "")  # e.g. "urn:li:activity:7123456789012345678"
activity_id = urn.replace("urn:li:activity:", "")  # → "7123456789012345678"
url = f"https://www.linkedin.com/feed/update/{urn}"
```

**Fallback:** Nếu không có `data-urn`, extract từ href:

```python
match = re.search(r"urn:li:activity:(\d+)", href)
if match:
    activity_id = match.group(1)
```

---

### **4. DeepSeek Prompt Update**

**File:** `src/linkedin_post_extractor.py:_USER_TEMPLATE`

```python
"""
Extract the 3 most recent posts with their type classification.

Return ONLY a JSON array:
[
  {
    "type": "post" | "repost" | "repost_with_thought",
    "date": "date string if available",
    "content": "full original post content"
  },
  ...
]

Type definitions:
- "post": Original content written by the user
- "repost": Pure reshare (no added comment)
- "repost_with_thought": Reshare with user's added commentary
"""
```

**Output:** JSON array thay vì object với key `"post"` (dễ parse hơn)

---

### **5. Merge Metadata + Content**

**File:** `src/linkedin_post_extractor.py:_merge_with_metadata()`

```python
# DeepSeek trả về: [{"type": "post", "date": "3mo", "content": "..."}]
# HTML metadata:   [{"type": "post", "activityId": "123", "url": "..."}]

merged_post = {
    "type": metadata.get("type", ds_post["type"]),  # ưu tiên HTML type (accurate hơn)
    "activityId": metadata.get("activityId", ""),
    "url": metadata.get("url", ""),
    "date": ds_post.get("date", ""),                # từ DeepSeek
    "content": ds_post.get("content", ""),          # từ DeepSeek
}
```

**Rationale:** 
- HTML type classification dựa trên DOM structure → **accurate hơn** text analysis
- DeepSeek extract date + content → **rich context** từ markdown

---

## 🧪 Testing

### **Test case 1: Original post**

HTML:
```html
<div data-urn="urn:li:activity:7123456789">
  <div class="feed-shared-update-v2__commentary">
    When it comes to writing...
  </div>
</div>
```

Expected output:
```json
{
  "type": "post",
  "activityId": "7123456789",
  "url": "https://www.linkedin.com/feed/update/urn:li:activity:7123456789",
  "content": "When it comes to writing..."
}
```

---

### **Test case 2: Pure repost**

HTML:
```html
<div data-urn="urn:li:activity:7111111111">
  <div class="feed-shared-actor__description">John reposted this</div>
  <div class="feed-shared-update-v2__description">
    Great article about AI...
  </div>
</div>
```

Expected output:
```json
{
  "type": "repost",
  "activityId": "7111111111",
  "url": "https://www.linkedin.com/feed/update/urn:li:activity:7111111111",
  "content": ""
}
```

---

### **Test case 3: Repost with thought**

HTML:
```html
<div data-urn="urn:li:activity:7098765432">
  <div class="feed-shared-actor__description">John reposted this</div>
  <div class="feed-shared-update-v2__commentary">
    This is exactly what we've been working on!
  </div>
  <div class="feed-shared-update-v2__description">
    Great article about AI...
  </div>
</div>
```

Expected output:
```json
{
  "type": "repost_with_thought",
  "activityId": "7098765432",
  "url": "https://www.linkedin.com/feed/update/urn:li:activity:7098765432",
  "content": "This is exactly what we've been working on!"
}
```

---

## 🚀 Migration Guide

### **Cho client code đang dùng API cũ:**

**Before:**
```typescript
const result = await fetch('/linkedin-extract', {
  body: JSON.stringify({ text: html, name: "John Doe" })
});
// result = { ok: true, post: "• 3mo: content\n  [linkPost: url]\n• ..." }
```

**After:**
```typescript
const result = await fetch('/linkedin-extract', {
  body: JSON.stringify({ text: html, html: html, name: "John Doe" })
});
// result = { ok: true, posts: [
//   { type: "post", activityId: "123", url: "...", date: "3mo", content: "..." },
//   ...
// ]}
```

**Backward compatibility:** Server vẫn hỗ trợ ghi cả 2 format (string hoặc array) vào Sheet.

---

## 📝 Files Changed

1. ✅ `src/linkedin_post_extractor.py`
   - `extract_post_urls_from_html()` → `extract_posts_with_metadata()` (phân loại type + extract activityId)
   - `_USER_TEMPLATE`: update prompt để extract JSON array với type
   - `extract()`: merge HTML metadata + DeepSeek content
   - `_parse()`: parse JSON array thay vì object

2. ✅ `from_sheet_linkedin.py`
   - `_crawl_linkedin()`: luôn dùng Crawl4AI convert HTML → markdown
   - Format output với `[POST]`, `[REPOST]`, `[REPOST+]` labels

3. ✅ `server.py`
   - `/linkedin-extract`: trả về `posts` array thay vì `post` string
   - `/linkedin-write`: hỗ trợ cả format cũ (string) và mới (array)

---

## ⚠️ Breaking Changes

### **API Response Format:**

**Old:**
```json
{ "ok": true, "post": "• 3mo: content\n  [linkPost: url]\n• ..." }
```

**New:**
```json
{
  "ok": true,
  "posts": [
    { "type": "post", "activityId": "123", "url": "...", "date": "3mo", "content": "..." }
  ]
}
```

### **Migration:**

Client code cần update để đọc `posts` array thay vì `post` string.

**Example:**
```typescript
// Old
const postText = result.post;

// New
const posts = result.posts;
posts.forEach(p => {
  console.log(`[${p.type}] ${p.content}`);
  console.log(`Link: ${p.url}`);
});
```

---

## 🎯 Next Steps

- [ ] Test với LinkedIn profiles có nhiều reposts
- [ ] Verify activityId extraction với các format URL khác nhau
- [ ] Monitor DeepSeek type classification accuracy
- [ ] Update frontend để display post type badges

---

**Updated:** 2026-07-07
**Version:** 2.0.0
