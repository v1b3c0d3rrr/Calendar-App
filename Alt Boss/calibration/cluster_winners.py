"""
Кластеризация winners по типу price action до роста.

Для каждого winner скачиваем market_chart и классифицируем:
1. Тип pre-pump price action (ATH drawdown, accumulation duration, momentum)
2. Характеристики самого пампа (скорость, длительность)

Затем кластеризуем и для каждого кластера считаем свои пороги.

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import sys
import os
import json
import time
import math
import requests
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

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


def classify_price_action(market_caps, prices, t0_ts, peak_ts):
    """
    Классифицировать price action до T-0.

    Returns dict with features:
    - ath_drawdown_pct: насколько далеко от ATH на T-0
    - accumulation_days: сколько дней цена была в ±20% range до T-0
    - pre_trend_30d: тренд за 30 дней до T-0 (% change)
    - pre_trend_7d: тренд за 7 дней до T-0
    - pump_speed_days: за сколько дней достигнут пик
    - pump_magnitude: multiplier
    - mc_at_t0: MC на T-0
    - volatility_30d: волатильность за 30 дней до T-0
    - volume_pattern: avg vol/mc за 30 дней до T-0
    """
    if not prices or not market_caps:
        return None

    # Timestamps
    min_age_ms = 30 * 86400 * 1000

    # Find ATH before T-0
    prices_before_t0 = [(ts, p) for ts, p in prices if ts < t0_ts and p and p > 0]
    mcs_before_t0 = [(ts, mc) for ts, mc in market_caps if ts < t0_ts and mc and mc > 0]

    if len(prices_before_t0) < 30:
        return None

    # Price at T-0
    price_at_t0 = None
    for ts, p in sorted(prices, key=lambda x: abs(x[0] - t0_ts)):
        if p and p > 0:
            price_at_t0 = p
            break
    if not price_at_t0:
        return None

    # MC at T-0
    mc_at_t0 = None
    for ts, mc in sorted(market_caps, key=lambda x: abs(x[0] - t0_ts)):
        if mc and mc > 0:
            mc_at_t0 = mc
            break

    # ATH before T-0
    ath_price = max(p for _, p in prices_before_t0)
    ath_drawdown = ((price_at_t0 - ath_price) / ath_price) * 100

    # Pre-trend 30d
    t0_minus_30 = t0_ts - 30 * 86400 * 1000
    price_30d_ago = None
    for ts, p in sorted(prices_before_t0, key=lambda x: abs(x[0] - t0_minus_30)):
        if abs(ts - t0_minus_30) < 3 * 86400 * 1000:
            price_30d_ago = p
            break

    pre_trend_30d = None
    if price_30d_ago and price_30d_ago > 0:
        pre_trend_30d = ((price_at_t0 - price_30d_ago) / price_30d_ago) * 100

    # Pre-trend 7d
    t0_minus_7 = t0_ts - 7 * 86400 * 1000
    price_7d_ago = None
    for ts, p in sorted(prices_before_t0, key=lambda x: abs(x[0] - t0_minus_7)):
        if abs(ts - t0_minus_7) < 2 * 86400 * 1000:
            price_7d_ago = p
            break

    pre_trend_7d = None
    if price_7d_ago and price_7d_ago > 0:
        pre_trend_7d = ((price_at_t0 - price_7d_ago) / price_7d_ago) * 100

    # Accumulation: count days price stayed within ±20% of T-0 price before T-0
    acc_range_low = price_at_t0 * 0.80
    acc_range_high = price_at_t0 * 1.20
    acc_days = 0
    last_outside = t0_ts
    for ts, p in reversed(prices_before_t0):
        if acc_range_low <= p <= acc_range_high:
            acc_days += 1
        else:
            break
    acc_days = max(acc_days, 0)

    # Volatility 30d: std/mean of prices in 30d window before T-0
    prices_30d = [p for ts, p in prices_before_t0 if ts > t0_minus_30]
    volatility_30d = None
    if len(prices_30d) >= 5:
        mean_p = sum(prices_30d) / len(prices_30d)
        variance = sum((p - mean_p) ** 2 for p in prices_30d) / len(prices_30d)
        volatility_30d = (variance ** 0.5) / mean_p * 100

    # Pump speed: days from T-0 to peak
    pump_days = max(1, (peak_ts - t0_ts) / (86400 * 1000))

    # MC at peak
    mc_at_peak = None
    for ts, mc in sorted(market_caps, key=lambda x: abs(x[0] - peak_ts)):
        if mc and mc > 0:
            mc_at_peak = mc
            break

    multiplier = mc_at_peak / mc_at_t0 if mc_at_t0 and mc_at_peak else None

    return {
        "ath_drawdown_pct": round(ath_drawdown, 1),
        "pre_trend_30d_pct": round(pre_trend_30d, 1) if pre_trend_30d is not None else None,
        "pre_trend_7d_pct": round(pre_trend_7d, 1) if pre_trend_7d is not None else None,
        "accumulation_days": acc_days,
        "volatility_30d_pct": round(volatility_30d, 1) if volatility_30d is not None else None,
        "pump_days": round(pump_days, 1),
        "multiplier": round(multiplier, 1) if multiplier else None,
        "mc_at_t0": round(mc_at_t0) if mc_at_t0 else None,
    }


def assign_cluster(features):
    """
    Кластеризация по правилам (rule-based, не ML — прозрачнее).

    Кластеры:
    A: Deep Recovery — ATH drawdown > -70%, long accumulation
    B: Gradual Accumulation — drawdown -30% to -70%, stable range, slow build
    C: Breakout from Sideways — drawdown < -30%, trading range, sudden move
    D: Momentum Continuation — positive 30d trend, already rising
    E: V-Reversal — sharp drop then sharp recovery (high volatility)
    """
    dd = features.get("ath_drawdown_pct")
    trend_30 = features.get("pre_trend_30d_pct")
    trend_7 = features.get("pre_trend_7d_pct")
    acc_days = features.get("accumulation_days", 0)
    vol = features.get("volatility_30d_pct")
    pump_days = features.get("pump_days", 30)

    if dd is None:
        return "X_unknown"

    # A: Deep Recovery — was -70%+ from ATH
    if dd < -70:
        if acc_days >= 14:
            return "A_deep_recovery_accumulated"
        else:
            return "A_deep_recovery_quick"

    # B: Gradual Accumulation — moderate drawdown, long sideways
    if dd < -30 and acc_days >= 14:
        return "B_gradual_accumulation"

    # C: Breakout from Sideways — moderate drawdown, short accumulation
    if dd < -30 and acc_days < 14:
        if vol and vol > 10:
            return "E_v_reversal"
        return "C_breakout_sideways"

    # D: Momentum Continuation — near ATH, positive trend
    if dd >= -30:
        if trend_30 is not None and trend_30 > 10:
            return "D_momentum_continuation"
        if trend_7 is not None and trend_7 > 5:
            return "D_momentum_continuation"
        if acc_days >= 7:
            return "C_breakout_sideways"
        return "D_momentum_continuation"

    return "X_unknown"


def main():
    output_dir = Path(__file__).parent
    clean = json.load(open(output_dir / "candidates_clean.json"))
    winners = clean["pure_winners"]

    # Resume support
    progress_path = output_dir / "cluster_progress.json"
    analyzed = {}
    if progress_path.exists():
        analyzed = json.load(open(progress_path))
        print(f"Resume: {len(analyzed)} already analyzed")

    print(f"Analyzing {len(winners)} pure winners for price action clustering...")
    print(f"Need to fetch market_chart for {len(winners) - len(analyzed)} tokens\n")

    for idx, w in enumerate(winners):
        cid = w["coin_id"]
        if cid in analyzed:
            continue

        symbol = w["symbol"]
        t0_date = w["start_date"]
        peak_date = w["peak_date"]

        t0_ts = int(datetime.strptime(t0_date, "%Y-%m-%d").timestamp() * 1000)
        peak_ts = int(datetime.strptime(peak_date, "%Y-%m-%d").timestamp() * 1000)

        print(f"[{idx+1}/{len(winners)}] {symbol} ({cid})...", end=" ")

        resp = safe_get(f"{BASE_URL}/coins/{cid}/market_chart", params={
            "vs_currency": "usd", "days": 180,
        })
        time.sleep(RATE_LIMIT_DELAY)

        if not resp:
            print("✗ not found")
            analyzed[cid] = {"error": "not_found", "symbol": symbol}
            continue

        chart = resp.json()
        features = classify_price_action(
            chart.get("market_caps", []),
            chart.get("prices", []),
            t0_ts, peak_ts
        )

        if not features:
            print("✗ insufficient data")
            analyzed[cid] = {"error": "insufficient_data", "symbol": symbol}
            continue

        cluster = assign_cluster(features)
        analyzed[cid] = {
            "symbol": symbol,
            "name": w["name"],
            "start_date": t0_date,
            "peak_date": peak_date,
            "start_mc": w["start_mc"],
            "peak_mc": w["peak_mc"],
            "multiplier": w["multiplier"],
            "features": features,
            "cluster": cluster,
        }

        print(f"✓ {cluster} (dd={features['ath_drawdown_pct']}%, acc={features['accumulation_days']}d, "
              f"trend30={features.get('pre_trend_30d_pct')}%)")

        if (idx + 1) % 10 == 0:
            with open(progress_path, "w") as f:
                json.dump(analyzed, f, indent=2, ensure_ascii=False)
            print(f"  [Saved: {len(analyzed)}]")

    # Final save
    with open(progress_path, "w") as f:
        json.dump(analyzed, f, indent=2, ensure_ascii=False)

    # Now collect metrics for each by cluster
    valid = {k: v for k, v in analyzed.items() if "error" not in v}
    clusters = Counter(v["cluster"] for v in valid.values())

    print(f"\n{'='*80}")
    print(f"CLUSTER DISTRIBUTION ({len(valid)} valid tokens)")
    print(f"{'='*80}")
    for cl, cnt in clusters.most_common():
        print(f"  {cl}: {cnt} tokens")

    # Save
    output = {
        "generated": datetime.now().isoformat(),
        "attribution": ATTRIBUTION,
        "total_analyzed": len(valid),
        "clusters": dict(clusters),
        "tokens": analyzed,
    }
    out_path = output_dir / "clustered_winners.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")
    print(ATTRIBUTION)


if __name__ == "__main__":
    main()
