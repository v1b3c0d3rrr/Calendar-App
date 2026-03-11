"""
Парсинг social metrics с LunarCrush и CoinGecko для 121 winners.

Собираем:
- Galaxy Score, AltRank (LunarCrush)
- Twitter followers, Reddit subscribers (CoinGecko)
- Social engagement metrics

Исторические данные через LunarCrush недоступны (платная подписка),
поэтому собираем текущие snapshot-ы и коррелируем с кластерами.

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
Social data powered by LunarCrush (https://lunarcrush.com/)
"""

import sys
import os
import json
import time
import re
import requests
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

CG_KEY = os.getenv("CG_API_KEY", "")
CG_BASE = "https://api.coingecko.com/api/v3"
CG_DELAY = 2.5  # 30 req/min on demo

OUTPUT_DIR = Path(__file__).parent


def cg_get(endpoint, params=None, max_retries=3):
    if params is None:
        params = {}
    params["x_cg_demo_api_key"] = CG_KEY
    url = f"{CG_BASE}/{endpoint}"

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code >= 400:
                print(f"  HTTP {resp.status_code}")
                return None
            return resp.json()
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(5)
    return None


def scrape_lunarcrush_page(symbol):
    """Scrape LunarCrush coin page for Galaxy Score and AltRank."""
    # Try multiple URL formats
    urls = [
        f"https://lunarcrush.com/coins/{symbol.lower()}",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue

            text = resp.text

            result = {}

            # Galaxy Score — look for patterns in page content
            gs_match = re.search(r'"galaxy_score"\s*:\s*(\d+\.?\d*)', text)
            if gs_match:
                result["galaxy_score"] = float(gs_match.group(1))

            gs_match2 = re.search(r'"galaxyScore"\s*:\s*(\d+\.?\d*)', text)
            if gs_match2:
                result["galaxy_score"] = float(gs_match2.group(1))

            # AltRank
            ar_match = re.search(r'"alt_rank"\s*:\s*(\d+)', text)
            if ar_match:
                result["alt_rank"] = int(ar_match.group(1))

            ar_match2 = re.search(r'"altRank"\s*:\s*(\d+)', text)
            if ar_match2:
                result["alt_rank"] = int(ar_match2.group(1))

            # Social volume
            sv_match = re.search(r'"social_volume"\s*:\s*(\d+)', text)
            if sv_match:
                result["social_volume"] = int(sv_match.group(1))

            # Social contributors
            sc_match = re.search(r'"social_contributors"\s*:\s*(\d+)', text)
            if sc_match:
                result["social_contributors"] = int(sc_match.group(1))

            # Sentiment
            sent_match = re.search(r'"sentiment"\s*:\s*(\d+\.?\d*)', text)
            if sent_match:
                result["sentiment"] = float(sent_match.group(1))

            # Social score
            ss_match = re.search(r'"social_score"\s*:\s*(\d+)', text)
            if ss_match:
                result["social_score"] = int(ss_match.group(1))

            # Categories / interactions
            int_match = re.search(r'"interactions_24h"\s*:\s*(\d+)', text)
            if int_match:
                result["interactions_24h"] = int(int_match.group(1))

            if result:
                return result

        except Exception as e:
            pass

    return None


def get_cg_community(coin_id):
    """Get community data from CoinGecko coin detail endpoint."""
    data = cg_get(f"coins/{coin_id}", params={
        "localization": "false",
        "tickers": "false",
        "market_data": "false",
        "community_data": "true",
        "developer_data": "true",
        "sparkline": "false",
    })

    if not data:
        return None

    result = {}

    # Community data
    cd = data.get("community_data", {})
    if cd:
        result["twitter_followers"] = cd.get("twitter_followers")
        result["reddit_subscribers"] = cd.get("reddit_subscribers")
        result["reddit_avg_posts_48h"] = cd.get("reddit_average_posts_48h")
        result["reddit_avg_comments_48h"] = cd.get("reddit_average_comments_48h")
        result["telegram_channel_user_count"] = cd.get("telegram_channel_user_count")

    # Developer data
    dd = data.get("developer_data", {})
    if dd:
        result["github_forks"] = dd.get("forks")
        result["github_stars"] = dd.get("stars")
        result["github_subscribers"] = dd.get("subscribers")
        result["github_total_issues"] = dd.get("total_issues")
        result["github_closed_issues"] = dd.get("closed_issues")
        result["github_pull_requests_merged"] = dd.get("pull_requests_merged")
        result["github_pull_request_contributors"] = dd.get("pull_request_contributors")
        result["commit_count_4_weeks"] = dd.get("commit_count_4_weeks")

        # Code additions/deletions
        code = dd.get("code_additions_deletions_4_weeks", {})
        if code:
            result["code_additions_4w"] = code.get("additions")
            result["code_deletions_4w"] = code.get("deletions")

    # Sentiment / watchlist
    result["sentiment_votes_up_pct"] = data.get("sentiment_votes_up_percentage")
    result["sentiment_votes_down_pct"] = data.get("sentiment_votes_down_percentage")
    result["watchlist_portfolio_users"] = data.get("watchlist_portfolio_users")
    result["public_interest_score"] = data.get("public_interest_score")

    # Links for context
    links = data.get("links", {})
    if links:
        hp = links.get("homepage", [])
        result["has_website"] = bool(hp and hp[0])
        result["has_twitter"] = bool(links.get("twitter_screen_name"))
        result["has_telegram"] = bool(links.get("telegram_channel_identifier"))
        result["subreddit"] = links.get("subreddit_url")

    return result


def main():
    # Load clustered winners
    cluster_metrics = json.load(open(OUTPUT_DIR / "cluster_metrics_progress.json"))
    valid_tokens = {k: v for k, v in cluster_metrics.items() if "error" not in v}

    print(f"Collecting social data for {len(valid_tokens)} tokens")
    print(f"Strategy: CoinGecko community API + LunarCrush page scraping\n")

    # Resume support
    progress_path = OUTPUT_DIR / "social_progress.json"
    collected = {}
    if progress_path.exists():
        collected = json.load(open(progress_path))
        # Only keep entries with actual data (not from failed LC API attempts)
        collected = {k: v for k, v in collected.items()
                     if v.get("coingecko") or v.get("lunarcrush")}
        print(f"Resume: {len(collected)} already collected\n")

    remaining = [(cid, t) for cid, t in valid_tokens.items() if cid not in collected]
    print(f"Need to collect: {len(remaining)} tokens\n")

    for idx, (cid, t) in enumerate(remaining):
        symbol = t["symbol"]
        cluster = t["cluster"]

        print(f"[{idx+1}/{len(remaining)}] {symbol} ({cluster})...", end=" ")

        # 1. CoinGecko community data
        cg_data = get_cg_community(cid)
        time.sleep(CG_DELAY)

        cg_summary = ""
        if cg_data:
            tw = cg_data.get("twitter_followers")
            wl = cg_data.get("watchlist_portfolio_users")
            cg_summary = f"TW:{tw or '-'} WL:{wl or '-'}"
        else:
            cg_summary = "CG:none"

        # 2. LunarCrush scraping
        lc_data = scrape_lunarcrush_page(symbol)
        time.sleep(1)

        lc_summary = ""
        if lc_data:
            gs = lc_data.get("galaxy_score", "-")
            ar = lc_data.get("alt_rank", "-")
            lc_summary = f"GS:{gs} AR:{ar}"
        else:
            lc_summary = "LC:none"

        print(f"{cg_summary} | {lc_summary}")

        collected[cid] = {
            "symbol": symbol,
            "cluster": cluster,
            "coingecko": cg_data,
            "lunarcrush": lc_data,
        }

        if (idx + 1) % 10 == 0:
            with open(progress_path, "w") as f:
                json.dump(collected, f, indent=2, ensure_ascii=False)
            print(f"  [Saved: {len(collected)}]")

    # Final save
    with open(progress_path, "w") as f:
        json.dump(collected, f, indent=2, ensure_ascii=False)

    # Summary
    has_twitter = sum(1 for v in collected.values()
                      if v.get("coingecko", {}) and v["coingecko"].get("twitter_followers"))
    has_watchlist = sum(1 for v in collected.values()
                       if v.get("coingecko", {}) and v["coingecko"].get("watchlist_portfolio_users"))
    has_lc = sum(1 for v in collected.values() if v.get("lunarcrush"))
    has_sentiment = sum(1 for v in collected.values()
                        if v.get("coingecko", {}) and v["coingecko"].get("sentiment_votes_up_pct"))

    print(f"\n{'='*60}")
    print(f"DONE: {len(collected)} tokens")
    print(f"  Twitter followers: {has_twitter}")
    print(f"  Watchlist users: {has_watchlist}")
    print(f"  Sentiment data: {has_sentiment}")
    print(f"  LunarCrush data: {has_lc}")
    print(f"Saved: {progress_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
