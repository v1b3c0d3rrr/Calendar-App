"""
Сбор social metrics из LunarCrush API для 121 winners по кластерам.

Для каждого токена собираем на T-30, T-14, T-7, T-1:
- Galaxy Score, AltRank
- Social volume (mentions), social engagement
- Sentiment
- Contributors count

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
Social data powered by LunarCrush (https://lunarcrush.com/)
"""

import sys
import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

LUNARCRUSH_KEY = os.getenv("LUNARCRUSH_KEY", "")
LC_BASE = "https://lunarcrush.com/api4/public"
LC_DELAY = 1.5  # be safe with rate limits

ATTRIBUTION = "Social data powered by LunarCrush (https://lunarcrush.com/)"


def lc_get(endpoint, params=None, max_retries=3):
    if params is None:
        params = {}
    headers = {"Authorization": f"Bearer {LUNARCRUSH_KEY}"}
    url = f"{LC_BASE}/{endpoint}"

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers)
            if resp.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code == 401:
                print(f"  ✗ Auth error (401)")
                return None
            if resp.status_code >= 400:
                print(f"  ✗ HTTP {resp.status_code}")
                return None
            return resp
        except Exception as e:
            print(f"  ✗ Error: {e}")
            time.sleep(5)
    return None


def get_coin_social_timeseries(symbol, days_back=90):
    """Get time series social data for a coin."""
    # Try coins/symbol/time-series/v2
    resp = lc_get(f"coins/{symbol.lower()}/time-series/v2", params={
        "bucket": "day",
        "interval": f"{days_back}d",
    })
    if resp:
        try:
            return resp.json()
        except Exception:
            pass

    # Fallback: try /coins/symbol/v1
    resp = lc_get(f"coins/{symbol.lower()}/v1")
    if resp:
        try:
            return resp.json()
        except Exception:
            pass

    return None


def get_coin_snapshot(symbol):
    """Get current snapshot of coin social data."""
    resp = lc_get(f"coins/{symbol.lower()}/v1")
    if resp:
        try:
            return resp.json()
        except Exception:
            pass
    return None


def extract_timeseries_at_date(ts_data, target_date_str):
    """Extract metrics closest to a target date from timeseries."""
    if not ts_data:
        return None

    target = datetime.strptime(target_date_str, "%Y-%m-%d")
    target_ts = int(target.timestamp())

    # Find data points - handle different response formats
    data_points = None
    if isinstance(ts_data, dict):
        data_points = ts_data.get("data") or ts_data.get("timeSeries") or ts_data.get("time_series")
        if isinstance(data_points, dict):
            data_points = data_points.get("data")
    if isinstance(ts_data, list):
        data_points = ts_data

    if not data_points or not isinstance(data_points, list):
        return None

    # Find closest point
    closest = None
    min_diff = float("inf")
    for point in data_points:
        if not isinstance(point, dict):
            continue
        ts = point.get("time") or point.get("timestamp") or point.get("t")
        if ts is None:
            continue
        diff = abs(ts - target_ts)
        if diff < min_diff:
            min_diff = diff
            closest = point

    # Allow ±3 days tolerance
    if closest and min_diff <= 3 * 86400:
        return {
            "galaxy_score": closest.get("galaxy_score") or closest.get("gs"),
            "alt_rank": closest.get("alt_rank") or closest.get("ar"),
            "social_volume": closest.get("social_volume") or closest.get("sv"),
            "social_score": closest.get("social_score") or closest.get("ss"),
            "social_contributors": closest.get("social_contributors") or closest.get("sc"),
            "social_engagement": closest.get("social_engagement") or closest.get("se"),
            "social_mentions": closest.get("social_mentions") or closest.get("sm"),
            "social_sentiment": closest.get("sentiment") or closest.get("average_sentiment"),
            "tweets": closest.get("tweets") or closest.get("tweet_count"),
            "tweets_engagement": closest.get("tweets_engagement"),
            "news": closest.get("news"),
        }
    return None


def main():
    output_dir = Path(__file__).parent

    # Load clustered winners (filtered, no DEX/stables)
    cluster_metrics = json.load(open(output_dir / "cluster_metrics_progress.json"))
    valid_tokens = {k: v for k, v in cluster_metrics.items() if "error" not in v}

    print(f"Collecting social data for {len(valid_tokens)} tokens")

    # First test API with a known coin
    print("\nTesting LunarCrush API...")
    test = lc_get("coins/list/v2")
    if test:
        print(f"  ✓ API works, status {test.status_code}")
        try:
            d = test.json()
            if isinstance(d, dict):
                print(f"  Keys: {list(d.keys())[:5]}")
            elif isinstance(d, list):
                print(f"  Got list of {len(d)} items")
        except Exception as e:
            print(f"  Response: {test.text[:200]}")
    else:
        print("  ✗ API test failed")
    time.sleep(LC_DELAY)

    # Test with BTC
    print("\nTesting with BTC...")
    test2 = get_coin_snapshot("btc")
    if test2:
        print(f"  ✓ BTC data: {json.dumps(test2, indent=2)[:500]}")
    else:
        print("  ✗ BTC test failed")
    time.sleep(LC_DELAY)

    # Test time series
    print("\nTesting time series with BTC...")
    test3 = get_coin_social_timeseries("btc", 30)
    if test3:
        if isinstance(test3, dict):
            print(f"  ✓ Keys: {list(test3.keys())[:10]}")
            data = test3.get("data") or test3.get("timeSeries")
            if isinstance(data, list) and data:
                print(f"  First point keys: {list(data[0].keys())[:15]}")
            elif isinstance(data, dict):
                print(f"  Data keys: {list(data.keys())[:10]}")
        elif isinstance(test3, list) and test3:
            print(f"  ✓ List of {len(test3)} points")
            print(f"  First point keys: {list(test3[0].keys())[:15]}")
    else:
        print("  ✗ Time series test failed")
    time.sleep(LC_DELAY)

    # Resume support
    progress_path = output_dir / "social_progress.json"
    collected = {}
    if progress_path.exists():
        collected = json.load(open(progress_path))
        print(f"\nResume: {len(collected)} already collected")

    remaining = [(cid, t) for cid, t in valid_tokens.items() if cid not in collected]
    print(f"Need to collect: {len(remaining)} tokens\n")

    for idx, (cid, t) in enumerate(remaining):
        symbol = t["symbol"]
        cluster = t["cluster"]
        t0_date = t.get("features", {}).get("start_date") or t.get("start_date", "")

        # Some tokens have start_date in features, some don't
        if not t0_date:
            # Get from clustered_winners
            cw = json.load(open(output_dir / "clustered_winners.json"))
            if cid in cw.get("tokens", {}):
                t0_date = cw["tokens"][cid].get("start_date", "")

        print(f"[{idx+1}/{len(remaining)}] {symbol} ({cluster}, T-0={t0_date})...", end=" ")

        # Get time series (180 days to cover all timeframes)
        ts_data = get_coin_social_timeseries(symbol, 180)
        time.sleep(LC_DELAY)

        if not ts_data and t0_date:
            # Try with coin_id instead of symbol
            ts_data = get_coin_social_timeseries(cid, 180)
            time.sleep(LC_DELAY)

        social_metrics = {}

        if ts_data and t0_date:
            t0 = datetime.strptime(t0_date, "%Y-%m-%d")
            for days_before in [30, 14, 7, 1]:
                target = (t0 - timedelta(days=days_before)).strftime("%Y-%m-%d")
                point = extract_timeseries_at_date(ts_data, target)
                social_metrics[f"T-{days_before}"] = point

            # Also get snapshot for current state
            snapshot = get_coin_snapshot(symbol)
            time.sleep(LC_DELAY)
            if snapshot:
                social_metrics["current_snapshot"] = snapshot if isinstance(snapshot, dict) else None

            has_data = any(v for v in social_metrics.values() if v is not None)
            print(f"✓ {'has data' if has_data else 'no historical data'}")
        else:
            print(f"✗ no timeseries")

        collected[cid] = {
            "symbol": symbol,
            "cluster": cluster,
            "t0_date": t0_date,
            "social": social_metrics,
        }

        if (idx + 1) % 10 == 0:
            with open(progress_path, "w") as f:
                json.dump(collected, f, indent=2, ensure_ascii=False)
            print(f"  [Saved: {len(collected)}]")

    # Final save
    with open(progress_path, "w") as f:
        json.dump(collected, f, indent=2, ensure_ascii=False)

    # Quick summary
    has_social = sum(1 for v in collected.values()
                     if any(v.get("social", {}).get(f"T-{d}") for d in [30, 14, 7, 1]))
    print(f"\n{'='*60}")
    print(f"DONE: {len(collected)} tokens processed, {has_social} with social data")
    print(f"Saved: {progress_path}")
    print(ATTRIBUTION)
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
