#!/usr/bin/env python3
"""
Phases 1-4: Collect Binance spot klines, futures klines, funding rates,
and compute basis for every token in binance_sample.json.

Output: calibration/binance_derivatives_data.json
Resume: calibration/binance_data_progress.json
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# ---------- Paths ----------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(SCRIPT_DIR, "binance_sample.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "binance_derivatives_data.json")
PROGRESS_PATH = os.path.join(SCRIPT_DIR, "binance_data_progress.json")

# ---------- Load .env ----------

env_path = os.path.join(SCRIPT_DIR, "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ---------- Constants ----------

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"
REQUEST_DELAY = 0.2  # seconds between requests

# ---------- Rate-limited request ----------

last_call = 0.0


def api_get(base_url: str, endpoint: str, params: dict = None) -> list | dict | None:
    """Rate-limited GET. Returns parsed JSON or None on error."""
    global last_call
    elapsed = time.time() - last_call
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    url = f"{base_url}{endpoint}"
    last_call = time.time()
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 400:
            # Symbol not found / invalid
            return None
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"  [WARN] {endpoint} {params.get('symbol','')}: {e}")
        return None


# ---------- Date helpers ----------

def date_to_ms(date_str: str) -> int:
    """Convert 'YYYY-MM-DD' to milliseconds timestamp (UTC midnight)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def compute_event_date(token: dict) -> str:
    """Return the event start date (pump_start_date or drop_start_date)."""
    return token.get("pump_start_date") or token.get("drop_start_date")


def compute_time_window(event_date: str):
    """Return (start_ms, end_ms) for T-60 to T+5."""
    t = datetime.strptime(event_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = t - timedelta(days=60)
    end = t + timedelta(days=5)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


# ---------- Klines fetching ----------

def fetch_klines(base_url: str, endpoint: str, symbol: str, start_ms: int, end_ms: int):
    """Fetch all 1d klines in the window. Binance returns max 1500 per request."""
    pair = f"{symbol}USDT"
    all_klines = []
    current_start = start_ms
    while current_start < end_ms:
        data = api_get(base_url, endpoint, {
            "symbol": pair,
            "interval": "1d",
            "startTime": current_start,
            "endTime": end_ms,
            "limit": 1500,
        })
        if data is None or len(data) == 0:
            break
        all_klines.extend(data)
        # Move past the last candle
        last_open = data[-1][0]
        current_start = last_open + 86400000  # +1 day in ms
    return all_klines


def compute_kline_metrics(klines: list, event_date: str):
    """
    From daily klines, compute metrics at T-7, T-14, T-30.
    Each kline: [open_time, open, high, low, close, volume, close_time,
                 quote_volume, num_trades, taker_buy_base_vol, taker_buy_quote_vol, ...]
    """
    if not klines:
        return None

    t = datetime.strptime(event_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    t_ms = int(t.timestamp() * 1000)

    # Build dict: open_time_ms -> kline
    by_day = {}
    for k in klines:
        by_day[k[0]] = k

    result = {}
    for label, offset in [("t7", 7), ("t14", 14), ("t30", 30)]:
        # Collect 7 days of data ending at T-offset (inclusive)
        # i.e. days from T-(offset+6) to T-offset
        days_data = []
        for d in range(offset, offset + 7):
            day = t - timedelta(days=d)
            day_ms = int(day.replace(hour=0, minute=0, second=0).timestamp() * 1000)
            if day_ms in by_day:
                days_data.append(by_day[day_ms])

        if not days_data:
            result[f"vol_7d_avg_{label}"] = None
            result[f"taker_buy_ratio_{label}"] = None
            result[f"vol_growth_{label}"] = None
            result[f"close_{label}"] = None
            continue

        # quote_volume = idx 7, taker_buy_quote_volume = idx 10
        total_vol = sum(float(k[7]) for k in days_data)
        total_taker = sum(float(k[10]) for k in days_data)
        avg_vol = total_vol / len(days_data)

        result[f"vol_7d_avg_{label}"] = round(avg_vol, 2)
        result[f"taker_buy_ratio_{label}"] = round(total_taker / total_vol, 4) if total_vol > 0 else None

        # Close price at the offset day (most recent in the window)
        day_at_offset = t - timedelta(days=offset)
        day_at_offset_ms = int(day_at_offset.replace(hour=0, minute=0, second=0).timestamp() * 1000)
        if day_at_offset_ms in by_day:
            result[f"close_{label}"] = float(by_day[day_at_offset_ms][4])
        else:
            result[f"close_{label}"] = float(days_data[0][4])  # fallback to first available

    # vol_growth: vol_7d / vol_30d
    for label, offset in [("t7", 7), ("t14", 14), ("t30", 30)]:
        # Compute 30d avg volume for growth comparison
        days_30d = []
        for d in range(offset, offset + 30):
            day = t - timedelta(days=d)
            day_ms = int(day.replace(hour=0, minute=0, second=0).timestamp() * 1000)
            if day_ms in by_day:
                days_30d.append(by_day[day_ms])

        if days_30d:
            vol_30d_avg = sum(float(k[7]) for k in days_30d) / len(days_30d)
            vol_7d = result.get(f"vol_7d_avg_{label}")
            if vol_7d and vol_30d_avg > 0:
                result[f"vol_growth_{label}"] = round(vol_7d / vol_30d_avg, 4)
            else:
                result[f"vol_growth_{label}"] = None
        else:
            result[f"vol_growth_{label}"] = None

    return result


# ---------- Funding rate ----------

def fetch_funding(symbol: str, start_ms: int, end_ms: int):
    """Fetch funding rates. Binance returns max 1000 per request."""
    pair = f"{symbol}USDT"
    all_funding = []
    current_start = start_ms
    while current_start < end_ms:
        data = api_get(FUTURES_BASE, "/fapi/v1/fundingRate", {
            "symbol": pair,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": 1000,
        })
        if data is None or len(data) == 0:
            break
        all_funding.extend(data)
        # Move past the last entry
        current_start = data[-1]["fundingTime"] + 1
    return all_funding


def compute_funding_metrics(funding_data: list, event_date: str):
    """Compute funding metrics at various lookbacks before event date."""
    if not funding_data:
        return None

    t = datetime.strptime(event_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    t_ms = int(t.timestamp() * 1000)

    # Filter to entries before event date
    pre_event = [f for f in funding_data if f["fundingTime"] < t_ms]
    if not pre_event:
        return None

    result = {}
    for label, days in [("30d", 30), ("14d", 14), ("7d", 7)]:
        cutoff = t_ms - days * 86400000
        window = [f for f in pre_event if f["fundingTime"] >= cutoff]
        if not window:
            result[f"avg_{label}"] = None
            result[f"persistence_{label}"] = None if label == "30d" else None
            continue

        rates = [float(f["fundingRate"]) for f in window]
        avg_rate = sum(rates) / len(rates)
        result[f"avg_{label}"] = round(avg_rate, 8)

        if label == "30d":
            positive_count = sum(1 for r in rates if r > 0)
            result["persistence_30d"] = round(positive_count / len(rates), 4)
            result["max_30d"] = round(max(rates), 8)
            result["annualized_30d"] = round(avg_rate * 3 * 365, 4)

    return result


# ---------- Basis ----------

def compute_basis(spot_klines: list, futures_klines: list, event_date: str):
    """Compute basis (futures-spot spread) metrics."""
    if not spot_klines or not futures_klines:
        return None

    t = datetime.strptime(event_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    t_ms = int(t.timestamp() * 1000)

    # Build close price dicts by open_time
    spot_close = {k[0]: float(k[4]) for k in spot_klines}
    fut_close = {k[0]: float(k[4]) for k in futures_klines}

    # Compute daily basis for all overlapping days before event
    basis_days = []
    for open_time in sorted(spot_close.keys()):
        if open_time >= t_ms:
            continue
        if open_time in fut_close and spot_close[open_time] > 0:
            b = (fut_close[open_time] - spot_close[open_time]) / spot_close[open_time] * 100
            basis_days.append((open_time, b))

    if not basis_days:
        return None

    result = {}
    for label, days in [("7d", 7), ("30d", 30)]:
        cutoff = t_ms - days * 86400000
        window = [(ts, b) for ts, b in basis_days if ts >= cutoff]
        if window:
            avg_basis = sum(b for _, b in window) / len(window)
            result[f"avg_{label}"] = round(avg_basis, 6)
            if label == "30d":
                positive = sum(1 for _, b in window if b > 0)
                result["persistence_30d"] = round(positive / len(window), 4)
        else:
            result[f"avg_{label}"] = None
            if label == "30d":
                result["persistence_30d"] = None

    return result


# ---------- Main collection ----------

def load_progress():
    """Load progress or empty dict."""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    with open(PROGRESS_PATH, "w") as f:
        json.dump(progress, f, indent=2)


def process_token(symbol: str, event_date: str) -> dict:
    """Collect all data for one token."""
    start_ms, end_ms = compute_time_window(event_date)

    # 1. Spot klines
    spot_klines = fetch_klines(SPOT_BASE, "/api/v3/klines", symbol, start_ms, end_ms)
    spot_metrics = compute_kline_metrics(spot_klines, event_date)

    # 2. Futures klines
    futures_klines = fetch_klines(FUTURES_BASE, "/fapi/v1/klines", symbol, start_ms, end_ms)
    futures_metrics = compute_kline_metrics(futures_klines, event_date)

    # 3. Futures/spot volume ratio
    if futures_metrics and spot_metrics:
        for label in ["t7", "t14", "t30"]:
            fv = futures_metrics.get(f"vol_7d_avg_{label}")
            sv = spot_metrics.get(f"vol_7d_avg_{label}")
            if fv and sv and sv > 0:
                futures_metrics[f"futures_spot_ratio_{label}"] = round(fv / sv, 4)
            else:
                futures_metrics[f"futures_spot_ratio_{label}"] = None

    # 4. Funding rate
    funding_data = fetch_funding(symbol, start_ms, end_ms)
    funding_metrics = compute_funding_metrics(funding_data, event_date)

    # 5. Basis
    basis_metrics = compute_basis(spot_klines, futures_klines, event_date)

    return {
        "spot": spot_metrics,
        "futures": futures_metrics,
        "funding": funding_metrics,
        "basis": basis_metrics,
    }


def main():
    # Load sample
    with open(SAMPLE_PATH) as f:
        sample = json.load(f)

    # Build token list
    tokens = []
    for w in sample["winners"]:
        tokens.append({
            "symbol": w["symbol"],
            "group": "winner",
            "multiplier": w.get("multiplier"),
            "event_date": compute_event_date(w),
        })
    for l in sample["losers"]:
        tokens.append({
            "symbol": l["symbol"],
            "group": "loser",
            "drop_pct": l.get("drop_pct"),
            "event_date": compute_event_date(l),
        })

    print(f"Total tokens to process: {len(tokens)}")

    # Load progress
    progress = load_progress()
    total = len(tokens)
    done = 0
    skipped = 0

    for i, tok in enumerate(tokens):
        key = f"{tok['symbol']}_{tok['group']}"
        if key in progress:
            skipped += 1
            done += 1
            continue

        symbol = tok["symbol"]
        event_date = tok["event_date"]

        if not event_date:
            print(f"  [{i+1}/{total}] {symbol}: no event_date, skipping")
            progress[key] = {"symbol": symbol, "group": tok["group"], "error": "no_event_date"}
            save_progress(progress)
            done += 1
            continue

        data = process_token(symbol, event_date)

        entry = {
            "symbol": symbol,
            "group": tok["group"],
            "event_date": event_date,
            "spot": data["spot"],
            "futures": data["futures"],
            "funding": data["funding"],
            "basis": data["basis"],
        }
        if tok["group"] == "winner":
            entry["multiplier"] = tok.get("multiplier")
        else:
            entry["drop_pct"] = tok.get("drop_pct")

        progress[key] = entry
        save_progress(progress)
        done += 1

        if done % 10 == 0 or done == total:
            print(f"  [{done}/{total}] Last: {symbol} | "
                  f"spot={'YES' if data['spot'] else 'NO'} "
                  f"futures={'YES' if data['futures'] else 'NO'} "
                  f"funding={'YES' if data['funding'] else 'NO'} "
                  f"basis={'YES' if data['basis'] else 'NO'}")

    if skipped > 0:
        print(f"\nResumed: {skipped} tokens already done, processed {done - skipped} new")

    # Build final output
    output = {
        "metadata": {
            "created": datetime.now(timezone.utc).isoformat(),
            "winners": len(sample["winners"]),
            "losers": len(sample["losers"]),
            "total_processed": len(progress),
        },
        "tokens": {},
    }

    for key, entry in progress.items():
        sym = entry["symbol"]
        output["tokens"][sym] = entry

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    # Summary
    print(f"\n{'='*60}")
    print(f"COLLECTION COMPLETE")
    print(f"{'='*60}")

    has_spot = sum(1 for e in progress.values() if e.get("spot"))
    has_futures = sum(1 for e in progress.values() if e.get("futures"))
    has_funding = sum(1 for e in progress.values() if e.get("funding"))
    has_basis = sum(1 for e in progress.values() if e.get("basis"))

    print(f"Total tokens: {len(progress)}")
    print(f"  Spot data:    {has_spot}/{len(progress)}")
    print(f"  Futures data: {has_futures}/{len(progress)}")
    print(f"  Funding data: {has_funding}/{len(progress)}")
    print(f"  Basis data:   {has_basis}/{len(progress)}")

    # Breakdown by group
    for group in ["winner", "loser"]:
        group_entries = [e for e in progress.values() if e.get("group") == group]
        gs = sum(1 for e in group_entries if e.get("spot"))
        gf = sum(1 for e in group_entries if e.get("futures"))
        gfund = sum(1 for e in group_entries if e.get("funding"))
        gb = sum(1 for e in group_entries if e.get("basis"))
        print(f"\n  {group.upper()}S ({len(group_entries)}):")
        print(f"    Spot:    {gs}")
        print(f"    Futures: {gf}")
        print(f"    Funding: {gfund}")
        print(f"    Basis:   {gb}")

    print(f"\nOutput: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
