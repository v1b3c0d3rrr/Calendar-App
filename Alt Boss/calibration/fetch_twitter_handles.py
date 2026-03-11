"""
Fetch Twitter handles for 114 winners from CoinGecko API,
then scrape follower counts via Apify Tweet Scraper.
"""
import json
import os
import time
import requests
from pathlib import Path

CG_API_KEY = os.getenv("CG_API_KEY", "")
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
BASE_DIR = Path(__file__).parent


def load_twitter_tokens():
    """Load tokens that have Twitter from social_progress.json."""
    with open(BASE_DIR / "social_progress.json") as f:
        data = json.load(f)
    return {
        k: v for k, v in data.items()
        if v.get("coingecko", {}).get("has_twitter")
    }


def fetch_twitter_handles(tokens: dict) -> dict:
    """Fetch Twitter screen names from CoinGecko API for each token."""
    progress_file = BASE_DIR / "twitter_handles.json"

    # Resume from progress
    if progress_file.exists():
        with open(progress_file) as f:
            handles = json.load(f)
    else:
        handles = {}

    session = requests.Session()
    session.headers.update({
        "x-cg-demo-api-key": CG_API_KEY,
        "accept": "application/json"
    })

    remaining = [cid for cid in tokens if cid not in handles]
    total = len(remaining)
    print(f"Fetching Twitter handles: {len(handles)} done, {total} remaining")

    for i, coin_id in enumerate(remaining):
        try:
            resp = session.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false"
                },
                timeout=15
            )

            if resp.status_code == 429:
                print(f"  Rate limited at {coin_id}, waiting 60s...")
                time.sleep(60)
                resp = session.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                    params={
                        "localization": "false",
                        "tickers": "false",
                        "market_data": "false",
                        "community_data": "false",
                        "developer_data": "false",
                        "sparkline": "false"
                    },
                    timeout=15
                )

            if resp.status_code != 200:
                print(f"  [{i+1}/{total}] {coin_id}: HTTP {resp.status_code}")
                handles[coin_id] = {"error": resp.status_code}
                continue

            data = resp.json()
            links = data.get("links", {})
            twitter_handle = links.get("twitter_screen_name", "")
            symbol = tokens[coin_id].get("symbol", "?")

            handles[coin_id] = {
                "symbol": symbol,
                "twitter_handle": twitter_handle,
                "name": data.get("name", ""),
            }
            print(f"  [{i+1}/{total}] {symbol}: @{twitter_handle}")

        except Exception as e:
            print(f"  [{i+1}/{total}] {coin_id}: ERROR {e}")
            handles[coin_id] = {"error": str(e)}

        # Save progress every 10 tokens
        if (i + 1) % 10 == 0:
            with open(progress_file, "w") as f:
                json.dump(handles, f, indent=2)

        # CoinGecko demo: ~30 req/min
        time.sleep(2.5)

    # Final save
    with open(progress_file, "w") as f:
        json.dump(handles, f, indent=2)

    valid = sum(1 for v in handles.values() if v.get("twitter_handle"))
    print(f"\nDone: {valid} handles found out of {len(handles)} tokens")
    return handles


if __name__ == "__main__":
    tokens = load_twitter_tokens()
    print(f"Tokens with Twitter: {len(tokens)}")
    handles = fetch_twitter_handles(tokens)
