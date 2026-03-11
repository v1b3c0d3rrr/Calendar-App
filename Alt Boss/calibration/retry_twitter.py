"""Retry failed Twitter scrapes with longer waits and alternative parsing."""
import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).parent
PROGRESS_FILE = BASE_DIR / "twitter_followers.json"


def parse_count(text: str) -> int | None:
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


async def scrape_with_longer_wait(page, handle: str) -> dict:
    url = f"https://x.com/{handle}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(5000)

        # Try multiple selector strategies
        followers = None
        following = None

        # Strategy 1: verified_followers link
        for href_pattern in [f"/{handle}/verified_followers", f"/{handle}/followers"]:
            el = await page.query_selector(f'a[href="{href_pattern}"]')
            if el:
                text = await el.inner_text()
                m = re.search(r'([\d,\.]+[KMB]?)', text)
                if m:
                    followers = parse_count(m.group(1))
                break

        # Strategy 2: all links, check href
        if followers is None:
            links = await page.query_selector_all('a[href*="followers"]')
            for link in links:
                href = await link.get_attribute("href") or ""
                if handle.lower() in href.lower() and "follower" in href.lower():
                    text = await link.inner_text()
                    m = re.search(r'([\d,\.]+[KMB]?)', text)
                    if m:
                        followers = parse_count(m.group(1))
                    break

        # Strategy 3: page text regex
        if followers is None:
            body = await page.inner_text("body")
            # Pattern: "123 Followers" or "12.5K Followers"
            m = re.search(r'([\d,\.]+[KMB]?)\s*Follower', body)
            if m:
                followers = parse_count(m.group(1))
            m2 = re.search(r'([\d,\.]+[KMB]?)\s*Following', body)
            if m2:
                following = parse_count(m2.group(1))

        # Strategy 4: aria-label
        if followers is None:
            all_links = await page.query_selector_all('a')
            for link in all_links:
                aria = await link.get_attribute("aria-label") or ""
                if "follower" in aria.lower() and "following" not in aria.lower():
                    m = re.search(r'([\d,]+)', aria)
                    if m:
                        followers = parse_count(m.group(1))
                if "following" in aria.lower():
                    m = re.search(r'([\d,]+)', aria)
                    if m:
                        following = parse_count(m.group(1))

        if followers is not None:
            return {"followers": followers, "following": following}

        # Check for account issues
        body_text = await page.inner_text("body")
        if "doesn't exist" in body_text or "suspended" in body_text.lower():
            return {"error": "not_found_or_suspended"}

        return {"error": "parse_failed_retry"}

    except Exception as e:
        return {"error": str(e)[:200]}


async def main():
    with open(PROGRESS_FILE) as f:
        results = json.load(f)

    # Get failed handles
    failed = {k: v for k, v in results.items() if v.get("error") == "parse_failed"}
    print(f"Retrying {len(failed)} failed handles...")

    if not failed:
        print("Nothing to retry!")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = await context.new_page()

        fixed = 0
        for i, (handle, old_data) in enumerate(failed.items()):
            result = await scrape_with_longer_wait(page, handle)

            if result.get("followers") is not None:
                # Update with success, keep old metadata
                old_data.pop("error", None)
                old_data.update(result)
                results[handle] = old_data
                fixed += 1
                print(f"  [{i+1}/{len(failed)}] ✓ @{handle}: {result['followers']}")
            else:
                print(f"  [{i+1}/{len(failed)}] ✗ @{handle}: {result.get('error')}")

            await asyncio.sleep(3)

        await browser.close()

    with open(PROGRESS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nFixed {fixed} out of {len(failed)} failures")
    total_success = sum(1 for v in results.values() if v.get("followers"))
    print(f"Total success: {total_success}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
