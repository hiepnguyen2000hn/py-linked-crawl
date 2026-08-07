#!/usr/bin/env python3
"""
Test script để debug post extraction logic.
Usage: python test_extract_posts.py <html_file_path>
"""
import sys
from src.linkedin_post_extractor import extract_posts_with_metadata
from bs4 import BeautifulSoup

def analyze_html(html_path: str):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    print(f"📄 HTML file: {html_path}")
    print(f"📏 Size: {len(html):,} chars\n")

    soup = BeautifulSoup(html, 'lxml')

    # 1. Check for auth wall
    if "authwall" in html.lower() or "sign in" in html.lower()[:500]:
        print("⚠️  DETECTED: LinkedIn auth wall / login redirect")
        print("   → Need authenticated cookies to crawl\n")
        return

    # 2. Find data-urn elements
    urns = soup.find_all(attrs={"data-urn": True})
    print(f"🔍 Found {len(urns)} elements with data-urn attribute")

    activity_urns = [u for u in urns if "urn:li:activity:" in u.get("data-urn", "")]
    print(f"   - {len(activity_urns)} with urn:li:activity: (posts)")

    if activity_urns:
        print("\n📋 Sample URNs:")
        for urn_elem in activity_urns[:5]:
            urn = urn_elem.get("data-urn")
            print(f"   • {urn}")

    # 3. Find activity IDs in text
    import re
    activity_ids = re.findall(r'\b7\d{18}\b', html)
    unique_ids = list(dict.fromkeys(activity_ids))
    print(f"\n🔢 Found {len(unique_ids)} unique activity IDs (pattern: 7 + 18 digits)")
    if unique_ids:
        print(f"   Sample: {unique_ids[:3]}")

    # 4. Find common LinkedIn class names
    print(f"\n🎨 Common LinkedIn classes found:")
    class_patterns = [
        "feed-shared",
        "update-components",
        "commentary",
        "feed-shared-inline-show-more-text",
        "feed-shared-actor",
        "visually-hidden",
    ]
    for pattern in class_patterns:
        elems = soup.find_all(class_=re.compile(pattern))
        if elems:
            print(f"   ✓ {pattern}: {len(elems)} elements")

    # 5. Run extraction
    print(f"\n🚀 Running extract_posts_with_metadata()...\n")
    posts = extract_posts_with_metadata(html)

    print(f"\n✅ RESULT: Extracted {len(posts)} posts\n")
    for i, p in enumerate(posts, 1):
        print(f"  Post {i}:")
        print(f"    Type: {p['type']}")
        print(f"    ActivityId: {p['activityId']}")
        print(f"    URL: {p['url'][:80]}...")
        print(f"    Has content: {p['has_content']}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_extract_posts.py <html_file_path>")
        print("\nExample:")
        print("  python test_extract_posts.py /tmp/linkedin_sample.html")
        sys.exit(1)

    analyze_html(sys.argv[1])
