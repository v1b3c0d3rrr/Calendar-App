"""
Анализ кластеров price action: сбор метрик и расчёт порогов для каждого типа.

Исключаем DEX-токены, стейблы, tokenized stocks.

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import sys
import os
import json
import time
import statistics
import requests
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
API_KEY = os.environ.get("CG_API_KEY", "")
BASE_URL = "https://api.coingecko.com/api/v3"
RATE_LIMIT_DELAY = 2.5
ATTRIBUTION = "Data provided by CoinGecko (https://www.coingecko.com/en/api/)"

# Exclusions
EXCLUDE_IDS = {
    # DEX tokens
    "balancer", "uniswap", "sushiswap", "pancakeswap-token",
    "curve-dao-token", "joe", "trader-joe", "smardex",
    "raydium", "orca", "jupiter-exchange-solana", "aerodrome-finance",
    "tokenlon", "melon",
    # Stablecoins / pegged
    "usd-coinvertible", "hydrated-dollar", "worldwide-usd",
    "tokenised-gbp", "usp-yield-optimized-stablecoin",
    "main-street-usd", "main-street-yield", "hermetica-usdh",
    "re-protocol-reusde", "balsa-mm-fund", "sierra-2",
    # Tokenized stocks
    "nasdaq-xstock", "nvidia-xstock", "gold-xstock",
    "alphabet-xstock", "coinbase-xstock", "circle-xstock",
    # Fan tokens (football)
    "portugal-national-team-fan-token", "croatian-ff-fan-token",
    "argentine-football-association-fan-token",
    # Index / basket
    "coinmarketcap-20-index-dtf",
}

EXCLUDE_NAME_KEYWORDS = [
    "xstock", "tokenized", "tokenised", "stablecoin",
    "vault", "fund", "index", "fan token", "dollar",
]


def safe_get(url, params=None, max_retries=3):
    if params is None:
        params = {}
    if API_KEY:
        params["x_cg_demo_api_key"] = API_KEY
    for attempt in range(max_retries):
        resp = requests.get(url, params=params)
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp
    raise Exception(f"Rate limited {max_retries} times")


def should_exclude(cid, name):
    if cid in EXCLUDE_IDS:
        return True
    name_lower = name.lower()
    return any(kw in name_lower for kw in EXCLUDE_NAME_KEYWORDS)


def find_closest(data_list, target_ts, max_delta_ms=2*86400*1000):
    if not data_list:
        return None
    closest = min(data_list, key=lambda x: abs(x[0] - target_ts))
    if abs(closest[0] - target_ts) > max_delta_ms:
        return None
    return closest[1]


def collect_token_metrics(chart_data, t0_ts, coin_details=None):
    """Collect metrics at T-30, T-14, T-7, T-1."""
    prices = chart_data.get("prices", [])
    mcs = chart_data.get("market_caps", [])
    vols = chart_data.get("total_volumes", [])

    metrics = {}
    for days in [30, 14, 7, 1]:
        target_ts = t0_ts - days * 86400 * 1000

        price = find_closest(prices, target_ts)
        mc = find_closest(mcs, target_ts)
        vol = find_closest(vols, target_ts)

        # Avg volume 7d
        w_start = target_ts - 3 * 86400 * 1000
        w_end = target_ts + 3 * 86400 * 1000
        window_vols = [v for ts, v in vols if w_start <= ts <= w_end and v]
        avg_vol = sum(window_vols) / len(window_vols) if window_vols else None

        # Vol/MC
        vol_mc = vol / mc if vol and mc and mc > 0 else None

        # Price change 7d
        prev_ts = target_ts - 7 * 86400 * 1000
        prev_price = find_closest(prices, prev_ts)
        price_chg_7d = ((price - prev_price) / prev_price * 100) if price and prev_price and prev_price > 0 else None

        # Volatility 14d
        vol_start = target_ts - 14 * 86400 * 1000
        vol_prices = [p for ts, p in prices if vol_start <= ts <= target_ts and p and p > 0]
        volatility = None
        if len(vol_prices) >= 5:
            mean_p = sum(vol_prices) / len(vol_prices)
            var = sum((p - mean_p) ** 2 for p in vol_prices) / len(vol_prices)
            volatility = (var ** 0.5) / mean_p * 100

        metrics[f"T-{days}"] = {
            "mc": mc, "vol_24h": vol, "avg_vol_7d": avg_vol,
            "vol_mc": round(vol_mc, 6) if vol_mc else None,
            "price_chg_7d": round(price_chg_7d, 2) if price_chg_7d is not None else None,
            "volatility_14d": round(volatility, 2) if volatility is not None else None,
        }

    # Volume trend
    v30 = (metrics.get("T-30", {}) or {}).get("avg_vol_7d")
    v1 = (metrics.get("T-1", {}) or {}).get("avg_vol_7d")
    metrics["vol_trend"] = round(v1 / v30, 2) if v1 and v30 and v30 > 0 else None

    return metrics


def safe_median(values):
    clean = [v for v in values if v is not None]
    return round(statistics.median(clean), 4) if clean else None


def safe_mean(values):
    clean = [v for v in values if v is not None]
    return round(statistics.mean(clean), 4) if clean else None


def percentile(values, pct):
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    idx = int(len(clean) * pct / 100)
    idx = min(idx, len(clean) - 1)
    return round(clean[idx], 4)


def main():
    output_dir = Path(__file__).parent
    clustered = json.load(open(output_dir / "clustered_winners.json"))
    tokens = clustered["tokens"]

    # Filter valid, non-excluded tokens
    valid = {}
    excluded_count = 0
    for cid, t in tokens.items():
        if "error" in t:
            continue
        if should_exclude(cid, t.get("name", "")):
            excluded_count += 1
            continue
        valid[cid] = t

    # Merge A_deep_recovery_accumulated into A_deep_recovery
    for cid, t in valid.items():
        if t["cluster"] == "A_deep_recovery_accumulated":
            t["cluster"] = "A_deep_recovery"
        elif t["cluster"] == "A_deep_recovery_quick":
            t["cluster"] = "A_deep_recovery"

    # Count by cluster
    from collections import Counter
    cluster_counts = Counter(t["cluster"] for t in valid.values())
    print(f"Valid tokens: {len(valid)} (excluded: {excluded_count})")
    print(f"\nCluster distribution:")
    for cl, cnt in cluster_counts.most_common():
        print(f"  {cl}: {cnt}")

    # Now collect detailed metrics for each token
    progress_path = output_dir / "cluster_metrics_progress.json"
    collected = {}
    if progress_path.exists():
        collected = json.load(open(progress_path))
        print(f"\nResume: {len(collected)} already collected")

    remaining = [(cid, t) for cid, t in valid.items() if cid not in collected]
    print(f"Need to collect metrics for {len(remaining)} tokens\n")

    for idx, (cid, t) in enumerate(remaining):
        symbol = t["symbol"]
        t0_date = t["start_date"]
        t0_ts = int(datetime.strptime(t0_date, "%Y-%m-%d").timestamp() * 1000)

        print(f"[{idx+1}/{len(remaining)}] {symbol}...", end=" ")

        resp = safe_get(f"{BASE_URL}/coins/{cid}/market_chart", params={
            "vs_currency": "usd", "days": 180,
        })
        time.sleep(RATE_LIMIT_DELAY)

        if not resp:
            print("✗")
            collected[cid] = {"error": "not_found"}
            continue

        chart = resp.json()
        metrics = collect_token_metrics(chart, t0_ts)

        # Also get coin details for MC/FDV
        resp2 = safe_get(f"{BASE_URL}/coins/{cid}", params={
            "localization": "false", "tickers": "false",
            "market_data": "true", "community_data": "false",
            "developer_data": "true",
        })
        time.sleep(RATE_LIMIT_DELAY)

        details = {}
        if resp2:
            d = resp2.json()
            md = d.get("market_data", {})
            dev = d.get("developer_data", {})
            cs = md.get("circulating_supply")
            ts_supply = md.get("total_supply") or md.get("max_supply")
            fdv = md.get("fully_diluted_valuation", {}).get("usd")
            mc_t1 = (metrics.get("T-1", {}) or {}).get("mc")

            details = {
                "mc_fdv": round(mc_t1 / fdv, 4) if mc_t1 and fdv and fdv > 0 else None,
                "supply_ratio": round(cs / ts_supply, 4) if cs and ts_supply and ts_supply > 0 else None,
                "categories": d.get("categories", []),
                "has_github": bool(d.get("links", {}).get("repos_url", {}).get("github")),
                "commits_4w": dev.get("commit_count_4_weeks"),
                "telegram_users": (d.get("community_data") or {}).get("telegram_channel_user_count"),
            }

        collected[cid] = {
            "symbol": symbol,
            "cluster": t["cluster"],
            "multiplier": t["multiplier"],
            "features": t["features"],
            "metrics": metrics,
            "details": details,
        }
        print(f"✓ {t['cluster']}")

        if (idx + 1) % 15 == 0:
            with open(progress_path, "w") as f:
                json.dump(collected, f, indent=2, ensure_ascii=False)
            print(f"  [Saved: {len(collected)}]")

    # Final save
    with open(progress_path, "w") as f:
        json.dump(collected, f, indent=2, ensure_ascii=False)

    # ===== ANALYSIS BY CLUSTER =====
    valid_collected = {k: v for k, v in collected.items() if "error" not in v}

    # Group by cluster
    clusters = {}
    for cid, t in valid_collected.items():
        cl = t["cluster"]
        if cl not in clusters:
            clusters[cl] = []
        clusters[cl].append(t)

    print(f"\n\n{'='*100}")
    print(f"CLUSTER ANALYSIS — Thresholds per price action type")
    print(f"{'='*100}")

    cluster_thresholds = {}

    for cl_name in ["A_deep_recovery", "B_gradual_accumulation", "C_breakout_sideways",
                     "D_momentum_continuation", "E_v_reversal"]:
        group = clusters.get(cl_name, [])
        if not group:
            continue

        print(f"\n{'='*100}")
        print(f"CLUSTER {cl_name} ({len(group)} tokens)")
        print(f"{'='*100}")

        # Features summary
        multipliers = [t["multiplier"] for t in group]
        ath_dds = [t["features"]["ath_drawdown_pct"] for t in group]
        acc_days = [t["features"]["accumulation_days"] for t in group]
        trend30s = [t["features"].get("pre_trend_30d_pct") for t in group]
        mcs_t0 = [t["features"].get("mc_at_t0") for t in group if t["features"].get("mc_at_t0")]
        pump_days = [t["features"]["pump_days"] for t in group]

        print(f"\nProfile:")
        print(f"  Multiplier: median {safe_median(multipliers)}, range {min(multipliers)}-{max(multipliers)}")
        print(f"  ATH drawdown: median {safe_median(ath_dds)}%")
        print(f"  Accumulation days: median {safe_median(acc_days)}")
        print(f"  Pre-trend 30d: median {safe_median(trend30s)}%")
        print(f"  MC at T-0: median ${safe_median(mcs_t0)/1e6:.1f}M" if safe_median(mcs_t0) else "  MC at T-0: N/A")
        print(f"  Pump duration: median {safe_median(pump_days)} days")

        # Metrics by timeframe
        for tf in ["T-7", "T-1"]:
            vol_mcs = [t["metrics"].get(tf, {}).get("vol_mc") for t in group]
            price_chgs = [t["metrics"].get(tf, {}).get("price_chg_7d") for t in group]
            volatilities = [t["metrics"].get(tf, {}).get("volatility_14d") for t in group]
            volumes = [t["metrics"].get(tf, {}).get("avg_vol_7d") for t in group]

            print(f"\n  {tf}:")
            print(f"    Vol/MC:      median={safe_median(vol_mcs)}, p25={percentile(vol_mcs,25)}, p75={percentile(vol_mcs,75)}")
            print(f"    Price 7d%:   median={safe_median(price_chgs)}, p25={percentile(price_chgs,25)}, p75={percentile(price_chgs,75)}")
            print(f"    Volatility:  median={safe_median(volatilities)}, p25={percentile(volatilities,25)}, p75={percentile(volatilities,75)}")
            print(f"    Avg Vol 7d:  median=${safe_median(volumes)/1e3:.0f}K" if safe_median(volumes) else "    Avg Vol 7d:  N/A")

        # Details
        mc_fdvs = [t["details"].get("mc_fdv") for t in group]
        supply_ratios = [t["details"].get("supply_ratio") for t in group]
        vol_trends = [t["metrics"].get("vol_trend") for t in group]

        print(f"\n  Fundamentals:")
        print(f"    MC/FDV:      median={safe_median(mc_fdvs)}, p25={percentile(mc_fdvs,25)}")
        print(f"    Supply ratio: median={safe_median(supply_ratios)}, p25={percentile(supply_ratios,25)}")
        print(f"    Vol trend T-30→T-1: median={safe_median(vol_trends)}")

        # Top performers
        top = sorted(group, key=lambda x: x["multiplier"], reverse=True)[:5]
        print(f"\n  Top 5:")
        for t in top:
            print(f"    {t['symbol']:10} {t['multiplier']:5.1f}x  dd={t['features']['ath_drawdown_pct']}% acc={t['features']['accumulation_days']}d")

        # Save thresholds
        cluster_thresholds[cl_name] = {
            "count": len(group),
            "multiplier_median": safe_median(multipliers),
            "profile": {
                "ath_drawdown_median": safe_median(ath_dds),
                "accumulation_days_median": safe_median(acc_days),
                "pre_trend_30d_median": safe_median(trend30s),
                "pump_days_median": safe_median(pump_days),
            },
            "thresholds_T7": {
                "vol_mc_median": safe_median([t["metrics"].get("T-7", {}).get("vol_mc") for t in group]),
                "vol_mc_p25": percentile([t["metrics"].get("T-7", {}).get("vol_mc") for t in group], 25),
                "price_chg_7d_median": safe_median([t["metrics"].get("T-7", {}).get("price_chg_7d") for t in group]),
                "volatility_median": safe_median([t["metrics"].get("T-7", {}).get("volatility_14d") for t in group]),
            },
            "thresholds_fundamentals": {
                "mc_fdv_median": safe_median(mc_fdvs),
                "supply_ratio_median": safe_median(supply_ratios),
                "vol_trend_median": safe_median(vol_trends),
            },
        }

    # Save final analysis
    output = {
        "generated": datetime.now().isoformat(),
        "attribution": ATTRIBUTION,
        "clusters": cluster_thresholds,
        "tokens_per_cluster": {cl: [t["symbol"] for t in group] for cl, group in clusters.items()},
    }
    out_path = output_dir / "cluster_analysis.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n\nSaved: {out_path}")
    print(ATTRIBUTION)


if __name__ == "__main__":
    main()
