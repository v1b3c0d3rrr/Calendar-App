"""
Scrape Twitter/X follower counts using Playwright.
Opens profile pages headlessly and extracts follower count from the page.
"""
import asyncio
import json
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "twitter_followers.json"
HANDLES_FILE = BASE_DIR / "twitter_handles.json"
SOCIAL_FILE = BASE_DIR / "social_progress.json"


def parse_count(text: str) -> int | None:
    """Parse follower count text like '12.5K', '1.2M', '345'."""
    if not text:
        return None
    text = text.strip().replace(",", "")
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if text.upper().endswith(suffix):
            try:
                return int(float(text[:-1]) * mult)
            except ValueError:
                return None
    try:
        return int(text)
    except ValueError:
        return None


async def scrape_profile(page, handle: str, retries: int = 2) -> dict:
    """Scrape a single Twitter profile for follower/following counts."""
    url = f"https://x.com/{handle}"
    for attempt in range(retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # Wait for content to load
            await page.wait_for_timeout(3000)

            # Method 1: Look for follower link (e.g. /username/followers)
            followers_text = None
            following_text = None

            # Try finding the followers link
            followers_el = await page.query_selector(f'a[href="/{handle}/verified_followers"] span span, a[href="/{handle}/followers"] span span')
            if followers_el:
                followers_text = await followers_el.inner_text()

            following_el = await page.query_selector(f'a[href="/{handle}/following"] span span')
            if following_el:
                following_text = await following_el.inner_text()

            # Method 2: If method 1 failed, try regex on page content
            if not followers_text:
                content = await page.content()
                # Look for patterns like "1,234 Followers"
                m = re.search(r'([\d,\.]+[KMB]?)\s*Follower', content, re.I)
                if m:
                    followers_text = m.group(1)
                m2 = re.search(r'([\d,\.]+[KMB]?)\s*Following', content, re.I)
                if m2:
                    following_text = m2.group(1)

            # Method 3: aria-label on links
            if not followers_text:
                links = await page.query_selector_all('a[role="link"]')
                for link in links:
                    aria = await link.get_attribute("aria-label") or ""
                    if "follower" in aria.lower():
                        m = re.search(r'([\d,]+)', aria)
                        if m:
                            followers_text = m.group(1)
                    if "following" in aria.lower():
                        m = re.search(r'([\d,]+)', aria)
                        if m:
                            following_text = m.group(1)

            followers = parse_count(followers_text) if followers_text else None
            following = parse_count(following_text) if following_text else None

            # Check if account exists (look for "This account doesn't exist")
            page_text = await page.inner_text("body")
            if "doesn't exist" in page_text or "Account suspended" in page_text:
                return {"handle": handle, "error": "not_found_or_suspended"}

            if followers is not None:
                return {
                    "handle": handle,
                    "followers": followers,
                    "following": following,
                    "followers_raw": followers_text,
                    "following_raw": following_text,
                }

            if attempt < retries:
                await page.wait_for_timeout(2000)
                continue

            return {
                "handle": handle,
                "error": "parse_failed",
                "followers_text": followers_text,
                "following_text": following_text,
            }

        except Exception as e:
            if attempt < retries:
                await page.wait_for_timeout(2000)
                continue
            return {"handle": handle, "error": str(e)[:200]}

    return {"handle": handle, "error": "all_retries_failed"}


async def main():
    # Load handles
    with open(HANDLES_FILE) as f:
        handles_data = json.load(f)

    # Load cluster info
    with open(SOCIAL_FILE) as f:
        social_data = json.load(f)

    # Resume from progress
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            results = json.load(f)
    else:
        results = {}

    # Build task list
    tasks = []
    for coin_id, hdata in handles_data.items():
        handle = hdata.get("twitter_handle", "")
        if not handle or handle in results:
            continue
        symbol = hdata.get("symbol", "?")
        cluster = social_data.get(coin_id, {}).get("cluster", "unknown")
        tasks.append((coin_id, handle, symbol, cluster))

    print(f"Already scraped: {len(results)}, remaining: {len(tasks)}")
    if not tasks:
        print("Nothing to scrape!")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = await context.new_page()

        for i, (coin_id, handle, symbol, cluster) in enumerate(tasks):
            result = await scrape_profile(page, handle)
            result["coin_id"] = coin_id
            result["symbol"] = symbol
            result["cluster"] = cluster
            results[handle] = result

            status = f"✓ {result['followers']}" if result.get("followers") else f"✗ {result.get('error','?')}"
            print(f"  [{i+1}/{len(tasks)}] @{handle} ({symbol}): {status}")

            # Save progress every 5
            if (i + 1) % 5 == 0:
                with open(PROGRESS_FILE, "w") as f:
                    json.dump(results, f, indent=2)

            # Rate limit: 2-3 sec between requests
            await asyncio.sleep(2.5)

        await browser.close()

    # Final save
    with open(PROGRESS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    success = sum(1 for v in results.values() if v.get("followers"))
    errors = sum(1 for v in results.values() if v.get("error"))
    print(f"\nDone: {success} successful, {errors} errors out of {len(results)} total")


if __name__ == "__main__":
    asyncio.run(main())
