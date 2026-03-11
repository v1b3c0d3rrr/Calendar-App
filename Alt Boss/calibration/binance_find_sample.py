#!/usr/bin/env python3
"""
Phase 0: Build Binance Winners/Losers/Control sample from CoinGecko historical data.

Scans 373 Binance spot+futures tokens for:
- Winners: 2x+ pump in any 30-day window (first occurrence)
- Losers: -50%+ drop in any 30-day window (worst occurrence)
- Control: max/min < 1.5x over any 6-month window, stable MC
"""

import json
import os
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Config ---
CALIBRATION_DIR = Path(__file__).parent

# Load .env manually
env_path = CALIBRATION_DIR / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

CG_API_KEY = os.getenv("CG_API_KEY")
BASE_URL = "https://api.coingecko.com/api/v3"
HEADERS = {"x-cg-demo-api-key": CG_API_KEY}

PROGRESS_FILE = CALIBRATION_DIR / "binance_sample_progress.json"
OUTPUT_FILE = CALIBRATION_DIR / "binance_sample.json"
INPUT_FILE = CALIBRATION_DIR / "binance_futures_scan.json"

REQUEST_DELAY = 0.35  # seconds between requests
MAX_RETRIES = 5

# Stablecoins and wrapped tokens to exclude from control group
EXCLUDE_SYMBOLS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP",
    "WBTC", "WETH", "WBNB", "STETH", "CBETH", "RETH",
    "BBTC", "BETH",
}


def load_progress():
    """Load progress from disk."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed": {}, "winners": [], "losers": [], "control": []}


def save_progress(progress):
    """Save progress to disk."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def fetch_market_chart(cg_id: str) -> dict | None:
    """Fetch 365-day market chart from CoinGecko with retry logic."""
    url = f"{BASE_URL}/coins/{cg_id}/market_chart"
    params = {"vs_currency": "usd", "days": 365}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=30)

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = min(2 ** (attempt + 1), 60)
                print(f"  Rate limited on {cg_id}, waiting {wait}s...")
                time.sleep(wait)
                continue
            elif resp.status_code == 404:
                print(f"  {cg_id}: 404 not found, skipping")
                return None
            else:
                print(f"  {cg_id}: HTTP {resp.status_code}, retry {attempt+1}")
                time.sleep(2 ** attempt)
                continue
        except requests.exceptions.RequestException as e:
            print(f"  {cg_id}: request error {e}, retry {attempt+1}")
            time.sleep(2 ** attempt)
            continue

    print(f"  {cg_id}: all retries exhausted")
    return None


def to_daily(data_points: list) -> list[tuple[str, float]]:
    """Convert CoinGecko timestamp/value pairs to daily (date_str, value).
    CoinGecko returns ~hourly for 365d, so we take the first point per day.
    """
    daily = {}
    for ts_ms, value in data_points:
        date_str = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if date_str not in daily:
            daily[date_str] = value
    # Sort by date
    return sorted(daily.items())


def find_pump(daily_prices: list[tuple[str, float]], min_multiplier: float = 2.0):
    """Find first 30-day window with min_multiplier increase.
    Uses sliding window: for each day, look at max price in next 30 days.
    """
    n = len(daily_prices)
    if n < 30:
        return None

    best = None
    for i in range(n - 1):
        start_date, start_price = daily_prices[i]
        if start_price <= 0:
            continue

        # Look at all days within 30-day window
        window_end = min(i + 30, n)
        for j in range(i + 1, window_end):
            peak_date, peak_price = daily_prices[j]
            mult = peak_price / start_price

            if mult >= min_multiplier:
                # Found a pump - return first occurrence
                return {
                    "pump_start_date": start_date,
                    "pump_peak_date": peak_date,
                    "start_price": round(start_price, 8),
                    "peak_price": round(peak_price, 8),
                    "multiplier": round(mult, 2),
                }

    return None


def find_worst_drop(daily_prices: list[tuple[str, float]], max_drop: float = -0.5):
    """Find worst 30-day drop (most negative). Returns worst drop per token."""
    n = len(daily_prices)
    if n < 30:
        return None

    worst = None
    worst_drop_pct = 0

    for i in range(n - 1):
        start_date, start_price = daily_prices[i]
        if start_price <= 0:
            continue

        window_end = min(i + 30, n)
        for j in range(i + 1, window_end):
            end_date, end_price = daily_prices[j]
            drop_pct = (end_price - start_price) / start_price

            if drop_pct <= max_drop and drop_pct < worst_drop_pct:
                worst_drop_pct = drop_pct
                worst = {
                    "drop_start_date": start_date,
                    "drop_bottom_date": end_date,
                    "start_price": round(start_price, 8),
                    "bottom_price": round(end_price, 8),
                    "drop_pct": round(drop_pct * 100, 1),
                }

    return worst


def check_control(daily_prices: list[tuple[str, float]], daily_mcs: list[tuple[str, float]],
                   symbol: str) -> dict | None:
    """Check if token qualifies as control:
    - Max/min price ratio < 1.5x over ANY 6-month (180-day) window
    - Market cap $50M-$500M at midpoint
    - Not a stablecoin/wrapped token
    """
    if symbol.upper() in EXCLUDE_SYMBOLS:
        return None

    n = len(daily_prices)
    if n < 180:
        return None

    # Check ALL 6-month windows - token must have max/min < 1.5 in at least one
    # Actually: "Max/min price ratio < 1.5x over ANY 6-month window" means
    # we need ALL 6-month windows to have ratio < 1.5
    # Re-reading: "< 1.5x over ANY 6-month window" — this means for every possible
    # 6-month window, the ratio must be < 1.5. That's the strict reading.
    # Let's check: does max/min ratio stay < 1.5 across ALL 6-month windows?

    for i in range(n - 179):
        window = [p for _, p in daily_prices[i:i+180] if p > 0]
        if not window:
            continue
        ratio = max(window) / min(window)
        if ratio >= 1.5:
            return None  # Found a volatile window, not control

    # Check MC at midpoint
    mid_idx = len(daily_mcs) // 2
    if mid_idx >= len(daily_mcs):
        return None
    _, mid_mc = daily_mcs[mid_idx]
    if mid_mc < 50_000_000 or mid_mc > 500_000_000:
        return None

    # Calculate overall stats
    prices = [p for _, p in daily_prices if p > 0]
    overall_ratio = max(prices) / min(prices) if prices else 0

    return {
        "midpoint_mc": round(mid_mc),
        "price_range_ratio": round(overall_ratio, 2),
        "midpoint_date": daily_mcs[mid_idx][0],
    }


def main():
    # Load input
    with open(INPUT_FILE) as f:
        scan_data = json.load(f)

    tokens = scan_data["tokens"]
    print(f"Loaded {len(tokens)} tokens from binance_futures_scan.json")

    # Load progress
    progress = load_progress()
    processed = progress["processed"]
    winners = progress["winners"]
    losers = progress["losers"]
    control = progress["control"]

    print(f"Already processed: {len(processed)} tokens")
    print(f"Current: {len(winners)} winners, {len(losers)} losers, {len(control)} control")

    # Filter tokens with valid cg_id
    tokens_to_process = [t for t in tokens if t.get("cg_id") and t["cg_id"] not in processed]
    print(f"Remaining to process: {len(tokens_to_process)}")

    for idx, token in enumerate(tokens_to_process):
        cg_id = token["cg_id"]
        symbol = token["symbol"]
        name = token.get("name", symbol)

        # Fetch data
        data = fetch_market_chart(cg_id)
        time.sleep(REQUEST_DELAY)

        if data is None:
            processed[cg_id] = {"status": "error", "symbol": symbol}
            save_progress(progress)
            continue

        # Convert to daily
        daily_prices = to_daily(data.get("prices", []))
        daily_mcs = to_daily(data.get("market_caps", []))

        if len(daily_prices) < 30:
            processed[cg_id] = {"status": "insufficient_data", "symbol": symbol}
            save_progress(progress)
            continue

        # --- Check for pump (winner) ---
        pump = find_pump(daily_prices)
        if pump:
            # Get start MC
            start_mc = None
            pump_start = pump["pump_start_date"]
            for date_str, mc in daily_mcs:
                if date_str == pump_start:
                    start_mc = mc
                    break

            # Filter: start_mc between $5M and $2B
            if start_mc and 5_000_000 <= start_mc <= 2_000_000_000:
                winner = {
                    "symbol": symbol,
                    "cg_id": cg_id,
                    "name": name,
                    "start_mc": round(start_mc),
                    **pump,
                }
                winners.append(winner)
                processed[cg_id] = {"status": "winner", "symbol": symbol}
            elif start_mc:
                processed[cg_id] = {"status": "pump_but_mc_out_of_range", "symbol": symbol,
                                     "start_mc": start_mc, "multiplier": pump["multiplier"]}
            else:
                # No MC data for that date, still record as winner with None MC
                winner = {
                    "symbol": symbol,
                    "cg_id": cg_id,
                    "name": name,
                    "start_mc": None,
                    **pump,
                }
                winners.append(winner)
                processed[cg_id] = {"status": "winner_no_mc", "symbol": symbol}
        else:
            processed[cg_id] = {"status": "no_pump", "symbol": symbol}

        # --- Check for drop (loser) --- (independent of winner check)
        if processed[cg_id]["status"] not in ("winner", "winner_no_mc"):
            drop = find_worst_drop(daily_prices)
            if drop:
                # Get start MC
                drop_start_mc = None
                drop_start = drop["drop_start_date"]
                for date_str, mc in daily_mcs:
                    if date_str == drop_start:
                        drop_start_mc = mc
                        break

                if drop_start_mc and drop_start_mc > 30_000_000:
                    loser = {
                        "symbol": symbol,
                        "cg_id": cg_id,
                        "name": name,
                        "start_mc": round(drop_start_mc),
                        **drop,
                    }
                    losers.append(loser)
                    processed[cg_id]["status"] = "loser"

        # --- Check for control --- (only if not winner or loser)
        if processed[cg_id]["status"] in ("no_pump",):
            ctrl = check_control(daily_prices, daily_mcs, symbol)
            if ctrl:
                control_entry = {
                    "symbol": symbol,
                    "cg_id": cg_id,
                    "name": name,
                    **ctrl,
                }
                control.append(control_entry)
                processed[cg_id]["status"] = "control"

        # Save progress after each token
        save_progress(progress)

        # Progress report
        total_done = len(processed)
        if (idx + 1) % 10 == 0 or idx == len(tokens_to_process) - 1:
            print(f"[{total_done}/{len(tokens)}] Processed {symbol} | "
                  f"W:{len(winners)} L:{len(losers)} C:{len(control)}")

    # --- Final output ---
    print(f"\n{'='*60}")
    print(f"FINAL RESULTS:")
    print(f"  Total scanned: {len(processed)}")
    print(f"  Winners (2x+ in 30d): {len(winners)}")
    print(f"  Losers (-50%+ in 30d): {len(losers)}")
    print(f"  Control (stable): {len(control)}")

    # Sort winners by multiplier descending
    winners.sort(key=lambda x: x["multiplier"], reverse=True)

    # Sort losers by drop_pct (most negative first)
    losers.sort(key=lambda x: x["drop_pct"])

    output = {
        "metadata": {
            "created": datetime.now(timezone.utc).isoformat(),
            "total_tokens_scanned": len(processed),
            "source": "binance_futures_scan.json (spot+futures tokens)",
            "criteria": {
                "winners": "2x+ pump in 30-day window, start MC $5M-$2B",
                "losers": "-50%+ drop in 30-day window, start MC >$30M",
                "control": "max/min <1.5x in all 6-month windows, MC $50M-$500M",
            }
        },
        "winners": winners,
        "losers": losers,
        "control": control,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved to {OUTPUT_FILE}")

    # Print top winners
    print(f"\nTop 10 Winners:")
    for w in winners[:10]:
        print(f"  {w['symbol']:>8} {w['multiplier']:>5.1f}x  MC: ${w.get('start_mc', 0) or 0:>13,.0f}  "
              f"{w['pump_start_date']} → {w['pump_peak_date']}")

    # Print top losers
    print(f"\nTop 10 Losers:")
    for l in losers[:10]:
        print(f"  {l['symbol']:>8} {l['drop_pct']:>6.1f}%  MC: ${l.get('start_mc', 0) or 0:>13,.0f}  "
              f"{l['drop_start_date']} → {l['drop_bottom_date']}")

    # Print control
    print(f"\nControl Group:")
    for c in control:
        print(f"  {c['symbol']:>8}  range: {c['price_range_ratio']:>4.2f}x  "
              f"MC: ${c.get('midpoint_mc', 0):>13,.0f}")


if __name__ == "__main__":
    main()
