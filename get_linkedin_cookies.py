#!/usr/bin/env python3
"""
Quick script to get LinkedIn cookies from browser.
Mở LinkedIn login page → login manually → extract cookies → save to file.
"""
from playwright.sync_api import sync_playwright
import json

print("🚀 Starting LinkedIn cookie extractor...")
print("📌 A browser window will open. Please:")
print("   1. Login to LinkedIn")
print("   2. Wait until you see your feed/homepage")
print("   3. Come back here and press ENTER\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # Open LinkedIn
    page.goto("https://www.linkedin.com/login")

    # Wait for user to login
    input("⏸️  Press ENTER after you've logged in to LinkedIn...")

    # Extract cookies
    cookies = context.cookies()

    # Filter LinkedIn cookies only
    linkedin_cookies = [
        c for c in cookies
        if "linkedin.com" in c.get("domain", "")
    ]

    # Save to file
    output_file = "linkedin_cookies.json"
    with open(output_file, "w") as f:
        json.dump(linkedin_cookies, f, indent=2)

    print(f"\n✅ Success! Saved {len(linkedin_cookies)} LinkedIn cookies to {output_file}")
    print(f"\n📋 Key cookies found:")
    for c in linkedin_cookies:
        if c["name"] in ["li_at", "JSESSIONID", "li_a"]:
            print(f"   ✓ {c['name']}: {c['value'][:20]}...")

    print(f"\n🧪 Test with:")
    print(f"   export LINKEDIN_COOKIES_JSON=$(cat {output_file})")
    print(f"   python from_sheet_linkedin.py --spreadsheet-id YOUR_ID --gid GID --limit 1")

    browser.close()
