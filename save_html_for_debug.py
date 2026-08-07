#!/usr/bin/env python3
"""
Crawl Johnny Pronk và lưu HTML để debug.
Cần có LINKEDIN_COOKIES_JSON env var.
"""
import sys
sys.path.insert(0, '/home/hiepnv/code/py-linked-crawl')

from from_sheet_linkedin import _crawl_linkedin

url = "https://www.linkedin.com/in/johnny-pronk/"
print(f"Crawling: {url}")

markdown, html = _crawl_linkedin(url)

print(f"\n✓ Got {len(html)} chars HTML")
print(f"✓ Got {len(markdown)} chars markdown")

if html:
    # Save HTML
    with open("/tmp/johnny_pronk.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Saved HTML to /tmp/johnny_pronk.html")
    
    # Save markdown
    with open("/tmp/johnny_pronk.md", "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"✓ Saved markdown to /tmp/johnny_pronk.md")
    
    # Test extract
    from src.linkedin_post_extractor import extract_posts_with_metadata
    posts = extract_posts_with_metadata(html)
    print(f"\n✓ Extracted {len(posts)} posts")
    for p in posts:
        print(f"  - {p['type']}: {p['activityId'][:20]}...")
else:
    print("❌ No HTML - check if cookies are set!")
