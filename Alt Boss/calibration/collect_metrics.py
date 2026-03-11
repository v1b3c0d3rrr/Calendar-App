"""
Phase 2: Сбор детальных метрик для 30 отобранных токенов.

Для каждого токена собираем данные на 4 таймфрейма:
T-30, T-14, T-7, T-1 (дней до начала движения)

Источники: CoinGecko API (market_chart + coin details)

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import sys
import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

# Load env
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
TIMEFRAMES = [30, 14, 7, 1]  # дней до T-0


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
    raise Exception(f"Rate limited {max_retries} times for {url}")


def find_closest_datapoint(data_list, target_ts):
    """Найти ближайшую точку данных к target timestamp (ms)."""
    if not data_list:
        return None
    closest = min(data_list, key=lambda x: abs(x[0] - target_ts))
    # Допуск: ±2 дня
    if abs(closest[0] - target_ts) > 2 * 86400 * 1000:
        return None
    return closest


def extract_timeframe_metrics(chart_data, t0_date_str):
    """Извлечь метрики на T-30, T-14, T-7, T-1 от даты T-0."""
    t0 = datetime.strptime(t0_date_str, "%Y-%m-%d")
    prices = chart_data.get("prices", [])
    market_caps = chart_data.get("market_caps", [])
    volumes = chart_data.get("total_volumes", [])

    metrics = {}
    for days_before in TIMEFRAMES:
        target_date = t0 - timedelta(days=days_before)
        target_ts = int(target_date.timestamp() * 1000)

        price_point = find_closest_datapoint(prices, target_ts)
        mc_point = find_closest_datapoint(market_caps, target_ts)
        vol_point = find_closest_datapoint(volumes, target_ts)

        # Средний объём за 7 дней вокруг точки
        avg_vol_7d = None
        if volumes:
            window_start = target_ts - 3 * 86400 * 1000
            window_end = target_ts + 3 * 86400 * 1000
            window_vols = [v for ts, v in volumes if window_start <= ts <= window_end and v]
            if window_vols:
                avg_vol_7d = sum(window_vols) / len(window_vols)

        # Ценовой тренд: изменение за последние 7 дней от точки
        price_change_7d = None
        if prices:
            prev_ts = target_ts - 7 * 86400 * 1000
            prev_price = find_closest_datapoint(prices, prev_ts)
            curr_price = price_point
            if prev_price and curr_price and prev_price[1] and prev_price[1] > 0:
                price_change_7d = ((curr_price[1] - prev_price[1]) / prev_price[1]) * 100

        # Волатильность: std/mean цен за 14 дней
        volatility_14d = None
        if prices:
            vol_start = target_ts - 14 * 86400 * 1000
            vol_prices = [p for ts, p in prices if vol_start <= ts <= target_ts and p and p > 0]
            if len(vol_prices) >= 5:
                mean_p = sum(vol_prices) / len(vol_prices)
                variance = sum((p - mean_p) ** 2 for p in vol_prices) / len(vol_prices)
                volatility_14d = (variance ** 0.5) / mean_p * 100

        # Volume/MC ratio
        vol_mc_ratio = None
        if vol_point and mc_point and mc_point[1] and mc_point[1] > 0:
            vol_mc_ratio = vol_point[1] / mc_point[1]

        metrics[f"T-{days_before}"] = {
            "date": target_date.strftime("%Y-%m-%d"),
            "price": round(price_point[1], 8) if price_point and price_point[1] else None,
            "market_cap": round(mc_point[1]) if mc_point and mc_point[1] else None,
            "volume_24h": round(vol_point[1]) if vol_point and vol_point[1] else None,
            "avg_volume_7d": round(avg_vol_7d) if avg_vol_7d else None,
            "price_change_7d_pct": round(price_change_7d, 2) if price_change_7d is not None else None,
            "volatility_14d_pct": round(volatility_14d, 2) if volatility_14d is not None else None,
            "volume_mc_ratio": round(vol_mc_ratio, 4) if vol_mc_ratio is not None else None,
        }

    return metrics


def get_coin_details(coin_id):
    """Получить детали монеты: FDV, категории, ссылки, dev stats."""
    resp = safe_get(f"{BASE_URL}/coins/{coin_id}", params={
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "true",
        "developer_data": "true",
    })
    if not resp:
        return {}
    data = resp.json()

    market = data.get("market_data", {})
    community = data.get("community_data", {})
    developer = data.get("developer_data", {})

    return {
        "categories": data.get("categories", []),
        "genesis_date": data.get("genesis_date"),
        "platforms": list(data.get("platforms", {}).keys()),
        "fdv": market.get("fully_diluted_valuation", {}).get("usd"),
        "mc_fdv_ratio": None,  # вычислим позже
        "circulating_supply": market.get("circulating_supply"),
        "total_supply": market.get("total_supply"),
        "max_supply": market.get("max_supply"),
        "ath_change_pct": market.get("ath_change_percentage", {}).get("usd"),
        "atl_change_pct": market.get("atl_change_percentage", {}).get("usd"),
        # Community
        "twitter_followers": community.get("twitter_followers"),
        "reddit_subscribers": community.get("reddit_subscribers"),
        "reddit_avg_posts_48h": community.get("reddit_average_posts_48h"),
        "reddit_avg_comments_48h": community.get("reddit_average_comments_48h"),
        "telegram_channel_user_count": community.get("telegram_channel_user_count"),
        # Developer
        "github_forks": developer.get("forks"),
        "github_stars": developer.get("stars"),
        "github_subscribers": developer.get("subscribers"),
        "github_total_issues": developer.get("total_issues"),
        "github_closed_issues": developer.get("closed_issues"),
        "github_pull_requests_merged": developer.get("pull_requests_merged"),
        "github_commit_count_4_weeks": developer.get("commit_count_4_weeks"),
        "github_additions_4_weeks": (developer.get("code_additions_deletions_4_weeks") or {}).get("additions"),
        "github_deletions_4_weeks": (developer.get("code_additions_deletions_4_weeks") or {}).get("deletions"),
        # Links
        "homepage": (data.get("links", {}).get("homepage", [None]) or [None])[0],
        "github_repos": data.get("links", {}).get("repos_url", {}).get("github", []),
        "has_github": bool(data.get("links", {}).get("repos_url", {}).get("github")),
    }


def main():
    output_dir = Path(__file__).parent
    selection = json.load(open(output_dir / "final_selection.json"))

    # Все токены в единый список с группой
    all_tokens = []
    for w in selection["winners"]:
        all_tokens.append({**w, "group": "winner", "t0_date": w["start_date"]})
    for c in selection["control"]:
        # Для контроля берём середину периода как T-0
        all_tokens.append({**c, "group": "control", "t0_date": "2025-12-15"})
    for l in selection["losers"]:
        all_tokens.append({**l, "group": "loser", "t0_date": l["start_date"]})

    # Resume support
    progress_path = output_dir / "metrics_progress.json"
    collected = {}
    if progress_path.exists():
        collected = json.load(open(progress_path))
        print(f"Resume: {len(collected)} tokens already collected")

    print(f"\n{'='*60}")
    print(f"Phase 2: Collecting metrics for {len(all_tokens)} tokens")
    print(f"{'='*60}")

    for idx, token in enumerate(all_tokens):
        coin_id = token["coin_id"]
        if coin_id in collected:
            continue

        symbol = token.get("symbol", "?")
        group = token["group"]
        t0_date = token["t0_date"]
        print(f"\n[{idx+1}/{len(all_tokens)}] {symbol} ({coin_id}) — {group}")

        # 1. Market chart (need enough history before T-0)
        # Запрашиваем 180 дней для полноты
        print(f"  Fetching market chart...")
        chart_resp = safe_get(f"{BASE_URL}/coins/{coin_id}/market_chart", params={
            "vs_currency": "usd",
            "days": 180,
        })
        time.sleep(RATE_LIMIT_DELAY)

        if not chart_resp:
            print(f"  ✗ Chart data not available")
            collected[coin_id] = {"error": "chart_not_found", "symbol": symbol, "group": group}
            continue

        chart_data = chart_resp.json()

        # 2. Extract timeframe metrics
        print(f"  Extracting metrics at T-30, T-14, T-7, T-1 from {t0_date}...")
        tf_metrics = extract_timeframe_metrics(chart_data, t0_date)

        # 3. Coin details (FDV, community, dev)
        print(f"  Fetching coin details...")
        details = get_coin_details(coin_id)
        time.sleep(RATE_LIMIT_DELAY)

        # 4. Compute derived metrics
        # MC/FDV ratio at T-1
        t1_mc = (tf_metrics.get("T-1", {}) or {}).get("market_cap")
        fdv = details.get("fdv")
        if t1_mc and fdv and fdv > 0:
            details["mc_fdv_ratio"] = round(t1_mc / fdv, 4)

        # Supply ratio
        circ = details.get("circulating_supply")
        total = details.get("total_supply") or details.get("max_supply")
        details["supply_ratio"] = round(circ / total, 4) if circ and total and total > 0 else None

        # Volume trend: is volume increasing approaching T-0?
        vol_t30 = (tf_metrics.get("T-30", {}) or {}).get("avg_volume_7d")
        vol_t7 = (tf_metrics.get("T-7", {}) or {}).get("avg_volume_7d")
        vol_t1 = (tf_metrics.get("T-1", {}) or {}).get("avg_volume_7d")
        volume_trend = None
        if vol_t30 and vol_t1 and vol_t30 > 0:
            volume_trend = round(vol_t1 / vol_t30, 2)

        collected[coin_id] = {
            "symbol": symbol,
            "name": token.get("name", ""),
            "group": group,
            "t0_date": t0_date,
            "outcome": {
                "multiplier": token.get("multiplier"),
                "loss_pct": token.get("loss_pct"),
                "peak_mc": token.get("peak_mc"),
                "bottom_mc": token.get("bottom_mc"),
            },
            "timeframes": tf_metrics,
            "details": details,
            "derived": {
                "volume_trend_t30_to_t1": volume_trend,
                "mc_fdv_ratio": details.get("mc_fdv_ratio"),
                "supply_ratio": details.get("supply_ratio"),
            },
        }

        print(f"  ✓ Done: MC at T-1 = ${t1_mc/1e6:.1f}M" if t1_mc else "  ✓ Done (some data missing)")

        # Save progress every 5 tokens
        if (idx + 1) % 5 == 0:
            with open(progress_path, "w") as f:
                json.dump(collected, f, indent=2, ensure_ascii=False)
            print(f"  [Progress saved: {len(collected)}/{len(all_tokens)}]")

    # Final save
    with open(progress_path, "w") as f:
        json.dump(collected, f, indent=2, ensure_ascii=False)

    # Save final metrics file
    output = {
        "generated": datetime.now().isoformat(),
        "attribution": ATTRIBUTION,
        "token_count": len(collected),
        "tokens": collected,
    }
    out_path = output_dir / "metrics_full.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"DONE: Metrics collected for {len(collected)} tokens")
    print(f"Saved to: {out_path}")
    print(ATTRIBUTION)
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
