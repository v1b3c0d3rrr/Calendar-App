"""
Phase 5.1 + 5.2: Collect 30-day OI snapshots from Binance Futures and compute metrics.

Fetches openInterestHist for all USDT-M perpetual futures symbols,
computes growth metrics and OI/MC ratios using CoinGecko market cap data.

Output:
  - calibration/oi_snapshots/oi_YYYYMMDD.json  (raw 30-day OI history per symbol)
  - calibration/oi_snapshots/oi_metrics_YYYYMMDD.json  (computed metrics + summary)
"""

import os
import sys
import time
import json
import requests
from datetime import datetime, timezone

# ---------- Config ----------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_DIR = os.path.join(SCRIPT_DIR, "oi_snapshots")
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

# Load .env
env_path = os.path.join(SCRIPT_DIR, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

CG_API_KEY = os.getenv("CG_API_KEY", "CG-eeDr2ysuZoJe631HW3b4JK3j")
CG_BASE = "https://api.coingecko.com/api/v3"
CG_HEADERS = {"x-cg-demo-api-key": CG_API_KEY}

BINANCE_FAPI = "https://fapi.binance.com"
REQUEST_DELAY = 0.2  # seconds between Binance API calls

TODAY = datetime.now(timezone.utc).strftime("%Y%m%d")

# ---------- Rate-limited requests ----------

last_binance_call = 0.0
last_cg_call = 0.0


def binance_get(endpoint: str, params: dict = None) -> dict:
    """Rate-limited GET to Binance Futures API."""
    global last_binance_call
    elapsed = time.time() - last_binance_call
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    url = f"{BINANCE_FAPI}{endpoint}"
    last_binance_call = time.time()
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def cg_get(endpoint: str, params: dict = None) -> dict:
    """Rate-limited GET to CoinGecko API."""
    global last_cg_call
    elapsed = time.time() - last_cg_call
    if elapsed < 0.25:
        time.sleep(0.25 - elapsed)
    url = f"{CG_BASE}{endpoint}"
    last_cg_call = time.time()
    r = requests.get(url, headers=CG_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------- Step 5.1: Collect OI snapshots ----------

def get_futures_symbols() -> list[str]:
    """Get all USDT-M perpetual futures symbols (e.g., 'BTCUSDT')."""
    print("Fetching Binance USDT-M futures exchange info...")
    data = binance_get("/fapi/v1/exchangeInfo")
    symbols = []
    for s in data["symbols"]:
        if (s["quoteAsset"] == "USDT"
                and s["contractType"] == "PERPETUAL"
                and s["status"] == "TRADING"):
            symbols.append(s["symbol"])  # e.g. "BTCUSDT"
    symbols.sort()
    print(f"  Found {len(symbols)} USDT-M perpetual symbols")
    return symbols


def collect_oi_history(symbols: list[str]) -> dict:
    """
    For each symbol, fetch 30 days of OI history.
    Returns dict: symbol -> list of {timestamp, sumOpenInterest, sumOpenInterestValue}
    """
    all_data = {}
    total = len(symbols)
    errors = []

    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0 or i == 0:
            print(f"  Collecting OI history: {i+1}/{total}...")

        try:
            data = binance_get("/futures/data/openInterestHist", params={
                "symbol": sym,
                "period": "1d",
                "limit": 30,
            })
            if data:
                all_data[sym] = data
        except requests.exceptions.HTTPError as e:
            # Some symbols may not have OI history (e.g., newly listed)
            status = e.response.status_code if e.response is not None else "?"
            if status != 400:  # 400 = no data, expected for some symbols
                errors.append(f"{sym}: HTTP {status}")
        except Exception as e:
            errors.append(f"{sym}: {e}")

    print(f"  Collected OI data for {len(all_data)}/{total} symbols")
    if errors:
        print(f"  Errors ({len(errors)}): {errors[:10]}{'...' if len(errors) > 10 else ''}")
    return all_data


def save_oi_snapshot(oi_data: dict, date_str: str) -> str:
    """Save raw OI snapshot to JSON."""
    path = os.path.join(SNAPSHOTS_DIR, f"oi_{date_str}.json")
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": date_str,
        "symbols_count": len(oi_data),
        "data": oi_data,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nRaw OI snapshot saved to {path}")
    return path


# ---------- Step 5.2: Compute OI metrics ----------

def load_futures_scan() -> dict:
    """Load binance_futures_scan.json and build symbol -> {cg_id, market_cap} map."""
    scan_path = os.path.join(SCRIPT_DIR, "binance_futures_scan.json")
    if not os.path.exists(scan_path):
        print(f"WARNING: {scan_path} not found. OI/MC ratios will not be computed.")
        return {}
    with open(scan_path) as f:
        scan = json.load(f)
    sym_map = {}
    for token in scan.get("tokens", []):
        sym_map[token["symbol"]] = {
            "cg_id": token.get("cg_id", ""),
            "market_cap": token.get("market_cap", 0),
            "name": token.get("name", ""),
        }
    return sym_map


def compute_metrics(oi_data: dict, sym_map: dict) -> list[dict]:
    """
    Compute OI metrics for each symbol with sufficient data.
    Returns list of metric dicts sorted by oi_current_usd descending.
    """
    metrics = []

    for sym_usdt, history in oi_data.items():
        if not history or len(history) < 2:
            continue

        # Sort by timestamp ascending
        history_sorted = sorted(history, key=lambda x: x["timestamp"])

        # Parse values
        latest = history_sorted[-1]
        oi_current = float(latest["sumOpenInterestValue"])
        oi_contracts = float(latest["sumOpenInterest"])
        current_ts = latest["timestamp"]

        # Find 7d ago (closest to -7 days)
        target_7d = current_ts - 7 * 86400 * 1000  # ms
        closest_7d = min(history_sorted, key=lambda x: abs(x["timestamp"] - target_7d))
        oi_7d_ago = float(closest_7d["sumOpenInterestValue"])

        # 30d ago = earliest available
        oi_30d_ago = float(history_sorted[0]["sumOpenInterestValue"])

        # Growth calculations
        oi_growth_7d = ((oi_current / oi_7d_ago) - 1) * 100 if oi_7d_ago > 0 else None
        oi_growth_30d = ((oi_current / oi_30d_ago) - 1) * 100 if oi_30d_ago > 0 else None

        # Strip USDT suffix for symbol lookup
        base_sym = sym_usdt.replace("USDT", "")
        mc_info = sym_map.get(base_sym, {})
        market_cap = mc_info.get("market_cap", 0)
        oi_mc_ratio = (oi_current / market_cap) if market_cap > 0 else None

        metrics.append({
            "symbol": sym_usdt,
            "base_symbol": base_sym,
            "name": mc_info.get("name", ""),
            "cg_id": mc_info.get("cg_id", ""),
            "oi_current_usd": round(oi_current, 2),
            "oi_current_contracts": round(oi_contracts, 2),
            "oi_7d_ago_usd": round(oi_7d_ago, 2),
            "oi_30d_ago_usd": round(oi_30d_ago, 2),
            "oi_growth_7d_pct": round(oi_growth_7d, 2) if oi_growth_7d is not None else None,
            "oi_growth_30d_pct": round(oi_growth_30d, 2) if oi_growth_30d is not None else None,
            "market_cap_usd": market_cap,
            "oi_mc_ratio": round(oi_mc_ratio, 4) if oi_mc_ratio is not None else None,
            "data_points": len(history_sorted),
            "latest_timestamp": current_ts,
        })

    metrics.sort(key=lambda x: x["oi_current_usd"], reverse=True)
    return metrics


def print_summary(metrics: list[dict]):
    """Print summary statistics."""
    if not metrics:
        print("No metrics to summarize.")
        return

    oi_values = [m["oi_current_usd"] for m in metrics]
    oi_values_sorted = sorted(oi_values)
    median_oi = oi_values_sorted[len(oi_values_sorted) // 2]

    print(f"\n{'='*70}")
    print(f"OI METRICS SUMMARY")
    print(f"{'='*70}")
    print(f"Total tokens with OI data: {len(metrics)}")
    print(f"Median OI (USDT):          ${median_oi:,.0f}")
    print(f"Total OI (all tokens):     ${sum(oi_values):,.0f}")

    # Top 20 by OI growth 7d
    with_growth_7d = [m for m in metrics if m["oi_growth_7d_pct"] is not None]
    top_growth_7d = sorted(with_growth_7d, key=lambda x: x["oi_growth_7d_pct"], reverse=True)[:20]

    print(f"\n--- TOP 20 BY OI GROWTH 7D ---")
    print(f"{'Symbol':12s} {'Name':20s} {'OI (USDT)':>15s} {'7d Growth':>10s} {'30d Growth':>11s} {'OI/MC':>8s}")
    for m in top_growth_7d:
        oi_str = f"${m['oi_current_usd']:,.0f}"
        g7 = f"{m['oi_growth_7d_pct']:+.1f}%"
        g30 = f"{m['oi_growth_30d_pct']:+.1f}%" if m['oi_growth_30d_pct'] is not None else "N/A"
        mc_r = f"{m['oi_mc_ratio']:.3f}" if m['oi_mc_ratio'] is not None else "N/A"
        print(f"{m['symbol']:12s} {m['name'][:20]:20s} {oi_str:>15s} {g7:>10s} {g30:>11s} {mc_r:>8s}")

    # Top 20 by OI/MC ratio
    with_mc_ratio = [m for m in metrics if m["oi_mc_ratio"] is not None and m["oi_mc_ratio"] > 0]
    top_mc_ratio = sorted(with_mc_ratio, key=lambda x: x["oi_mc_ratio"], reverse=True)[:20]

    print(f"\n--- TOP 20 BY OI/MC RATIO ---")
    print(f"{'Symbol':12s} {'Name':20s} {'OI (USDT)':>15s} {'MC (USDT)':>15s} {'OI/MC':>8s} {'7d Growth':>10s}")
    for m in top_mc_ratio:
        oi_str = f"${m['oi_current_usd']:,.0f}"
        mc_str = f"${m['market_cap_usd']:,.0f}" if m['market_cap_usd'] > 0 else "N/A"
        mc_r = f"{m['oi_mc_ratio']:.3f}"
        g7 = f"{m['oi_growth_7d_pct']:+.1f}%" if m['oi_growth_7d_pct'] is not None else "N/A"
        print(f"{m['symbol']:12s} {m['name'][:20]:20s} {oi_str:>15s} {mc_str:>15s} {mc_r:>8s} {g7:>10s}")


def save_metrics(metrics: list[dict], date_str: str) -> str:
    """Save computed metrics to JSON."""
    path = os.path.join(SNAPSHOTS_DIR, f"oi_metrics_{date_str}.json")
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": date_str,
        "total_symbols": len(metrics),
        "metrics": metrics,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nOI metrics saved to {path}")
    return path


# ---------- Main ----------

def main():
    print(f"=== OI Snapshot Collection — {TODAY} ===\n")

    # Step 5.1: Collect raw OI data
    symbols = get_futures_symbols()
    oi_data = collect_oi_history(symbols)
    save_oi_snapshot(oi_data, TODAY)

    # Step 5.2: Compute metrics
    sym_map = load_futures_scan()
    metrics = compute_metrics(oi_data, sym_map)
    print_summary(metrics)
    save_metrics(metrics, TODAY)

    print(f"\nDone. {len(metrics)} tokens processed.")


if __name__ == "__main__":
    main()
