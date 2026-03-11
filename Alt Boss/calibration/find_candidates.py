"""
Скрипт для поиска кандидатов калибровочного исследования.

Цель: найти токены, которые:
- Имели MC <$30M на момент T-0 (начало роста)
- Выросли минимум 2x за ≤30 дней
- Торговались минимум 30 дней до T-0 (не post-listing pump)
- Период: последние 6 месяцев

Также ищем LOSERS:
- MC был $10-30M → упал на -50%+ за ≤30 дней

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import sys
import os
import requests
import time
import json
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

# CoinGecko Demo API — читаем из .env или env variable
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
API_KEY = os.environ.get("CG_API_KEY", "")
BASE_URL = "https://api.coingecko.com/api/v3"
RATE_LIMIT_DELAY = 2.5  # 30 req/min с ключом → 2с безопасно

# Параметры поиска
MAX_MC_BEFORE_GROWTH = 30_000_000   # $30M
MIN_GROWTH_MULTIPLIER = 2.0         # минимум 2x
MIN_LOSS_PERCENT = -50              # для losers: -50%+
LOOKBACK_DAYS = 180                 # 6 месяцев
MIN_AGE_DAYS = 30                   # исключаем post-listing pump

ATTRIBUTION = "Data provided by CoinGecko (https://www.coingecko.com/en/api/)"


def safe_get(url, params=None, max_retries=3):
    """GET с API ключом и retry при rate limit."""
    if params is None:
        params = {}
    if API_KEY:
        params["x_cg_demo_api_key"] = API_KEY

    for attempt in range(max_retries):
        resp = requests.get(url, params=params)
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise Exception(f"Rate limited {max_retries} times for {url}")


def get_all_coins(per_page=250, pages=6):
    """Получить список всех токенов (top 1500 по MC)."""
    all_coins = []
    for page in range(1, pages + 1):
        print(f"  Fetching page {page}/{pages}...")
        resp = safe_get(f"{BASE_URL}/coins/markets", params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
        })
        all_coins.extend(resp.json())
        time.sleep(RATE_LIMIT_DELAY)
    return all_coins


def get_market_chart(coin_id, days=180):
    """Получить историю цены и MC за N дней."""
    resp = safe_get(f"{BASE_URL}/coins/{coin_id}/market_chart", params={
        "vs_currency": "usd",
        "days": days,
    })
    return resp.json()


def analyze_coin(chart_data):
    """
    Анализ: искать паттерн роста из <$30M MC или падения из $10-30M MC.
    Исключает post-listing pump (первые MIN_AGE_DAYS).
    """
    market_caps = chart_data.get("market_caps", [])
    if not market_caps:
        return None

    first_trade_ts = market_caps[0][0]
    min_age_ms = MIN_AGE_DAYS * 86400 * 1000

    results = {"winners": [], "losers": []}

    for i, (ts, mc) in enumerate(market_caps):
        if mc is None or mc <= 0:
            continue
        # Пропускаем первые 30 дней (post-listing)
        if (ts - first_trade_ts) < min_age_ms:
            continue

        # --- WINNERS: MC <$30M → 2x+ за 30 дней ---
        if mc < MAX_MC_BEFORE_GROWTH and not results["winners"]:
            target_ts = ts + 30 * 86400 * 1000
            peak_mc, peak_ts = mc, ts

            for j in range(i + 1, len(market_caps)):
                fts, fmc = market_caps[j]
                if fts > target_ts:
                    break
                if fmc and fmc > peak_mc:
                    peak_mc, peak_ts = fmc, fts

            mult = peak_mc / mc
            if mult >= MIN_GROWTH_MULTIPLIER:
                results["winners"].append({
                    "start_date": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
                    "start_mc": round(mc),
                    "peak_mc": round(peak_mc),
                    "peak_date": datetime.fromtimestamp(peak_ts / 1000).strftime("%Y-%m-%d"),
                    "multiplier": round(mult, 1),
                })

        # --- LOSERS: MC $10-30M → -50%+ за 30 дней ---
        if 10_000_000 < mc < MAX_MC_BEFORE_GROWTH and not results["losers"]:
            if (ts - first_trade_ts) < min_age_ms:
                continue
            target_ts = ts + 30 * 86400 * 1000
            bottom_mc, bottom_ts = mc, ts

            for j in range(i + 1, len(market_caps)):
                fts, fmc = market_caps[j]
                if fts > target_ts:
                    break
                if fmc and 0 < fmc < bottom_mc:
                    bottom_mc, bottom_ts = fmc, fts

            loss = ((bottom_mc - mc) / mc) * 100
            if loss <= MIN_LOSS_PERCENT:
                results["losers"].append({
                    "start_date": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
                    "start_mc": round(mc),
                    "bottom_mc": round(bottom_mc),
                    "bottom_date": datetime.fromtimestamp(bottom_ts / 1000).strftime("%Y-%m-%d"),
                    "loss_pct": round(loss, 1),
                })

        # Нашли оба — выходим
        if results["winners"] and results["losers"]:
            break

    if results["winners"] or results["losers"]:
        return results
    return None


def main():
    output_dir = Path(__file__).parent
    output_dir.mkdir(exist_ok=True)

    if not API_KEY:
        print("ERROR: Установите CG_API_KEY. Пример:")
        print("  export CG_API_KEY=CG-xxxxx")
        sys.exit(1)

    print("=" * 60)
    print("Калибровочное исследование: поиск кандидатов")
    print(f"Фильтр: MC <${MAX_MC_BEFORE_GROWTH / 1e6:.0f}M → {MIN_GROWTH_MULTIPLIER}x+ (winners)")
    print(f"         MC $10-30M → {MIN_LOSS_PERCENT}%+ loss (losers)")
    print(f"Период: {LOOKBACK_DAYS} дней | Мин. возраст: {MIN_AGE_DAYS} дней")
    print(f"API Key: ...{API_KEY[-6:]}")
    print(ATTRIBUTION)
    print("=" * 60)

    # Шаг 1: Загрузка списка
    print("\n[1/3] Загружаем список токенов (top 1500)...")
    all_coins = get_all_coins(per_page=250, pages=6)
    print(f"  Получено: {len(all_coins)} токенов")

    # Фильтр: MC <$2B, не стейблы/wrapped
    exclude_ids = {
        "tether", "usd-coin", "dai", "first-digital-usd", "ethena-usde",
        "frax", "true-usd", "paxos-standard", "tether-gold", "pax-gold",
        "wrapped-bitcoin", "wrapped-ether", "wrapped-steth", "weth",
        "staked-ether", "rocket-pool-eth", "coinbase-wrapped-staked-eth",
        "bitcoin", "ethereum",  # слишком крупные, никогда не были <$30M
    }
    candidates = [c for c in all_coins
                  if c.get("market_cap") and c["market_cap"] < 2_000_000_000
                  and c["id"] not in exclude_ids]
    print(f"  После фильтра: {len(candidates)} кандидатов")

    # Шаг 2: Resume
    progress_path = output_dir / "progress.json"
    winners, losers, errors = [], [], []
    processed_ids = set()

    if progress_path.exists():
        with open(progress_path) as f:
            p = json.load(f)
            winners = p.get("winners", [])
            losers = p.get("losers", [])
            processed_ids = set(p.get("processed_ids", []))
        print(f"  Resume: {len(processed_ids)} обработано, {len(winners)}W / {len(losers)}L")

    remaining = [c for c in candidates if c["id"] not in processed_ids]
    est_min = len(remaining) * RATE_LIMIT_DELAY / 60

    print(f"\n[2/3] Анализ {len(remaining)} токенов (~{est_min:.0f} мин)...")

    for idx, coin in enumerate(remaining):
        coin_id = coin["id"]
        symbol = coin["symbol"].upper()
        name = coin["name"]

        if idx % 50 == 0 and idx > 0:
            print(f"  [{idx}/{len(remaining)}] {len(winners)}W / {len(losers)}L найдено")
            with open(progress_path, "w") as f:
                json.dump({"winners": winners, "losers": losers,
                           "processed_ids": list(processed_ids)}, f)

        try:
            chart = get_market_chart(coin_id, days=LOOKBACK_DAYS)
            result = analyze_coin(chart)

            if result:
                if result["winners"]:
                    entry = {"coin_id": coin_id, "symbol": symbol, "name": name,
                             "current_mc": coin.get("market_cap"), **result["winners"][0]}
                    winners.append(entry)
                    print(f"  ✅ {symbol} ({name}): ${entry['start_mc']/1e6:.1f}M → ${entry['peak_mc']/1e6:.1f}M = {entry['multiplier']}x")

                if result["losers"]:
                    entry = {"coin_id": coin_id, "symbol": symbol, "name": name,
                             "current_mc": coin.get("market_cap"), **result["losers"][0]}
                    losers.append(entry)
                    print(f"  ❌ {symbol} ({name}): ${entry['start_mc']/1e6:.1f}M → ${entry['bottom_mc']/1e6:.1f}M = {entry['loss_pct']}%")

        except Exception as e:
            errors.append({"coin_id": coin_id, "error": str(e)})

        processed_ids.add(coin_id)
        time.sleep(RATE_LIMIT_DELAY)

    # Финальное сохранение
    with open(progress_path, "w") as f:
        json.dump({"winners": winners, "losers": losers,
                   "processed_ids": list(processed_ids)}, f)

    # Шаг 3: Результаты
    winners.sort(key=lambda x: x["multiplier"], reverse=True)
    losers.sort(key=lambda x: x["loss_pct"])

    print("\n" + "=" * 60)
    print(f"[3/3] РЕЗУЛЬТАТЫ: {len(winners)} winners, {len(losers)} losers")
    print("=" * 60)

    print(f"\nTOP WINNERS (MC <$30M → 2x+):")
    for i, w in enumerate(winners[:30], 1):
        print(f"  {i}. {w['symbol']} ({w['name']}): ${w['start_mc']/1e6:.1f}M → ${w['peak_mc']/1e6:.1f}M = {w['multiplier']}x | {w['start_date']} → {w['peak_date']}")

    print(f"\nTOP LOSERS (MC $10-30M → -50%+):")
    for i, l in enumerate(losers[:15], 1):
        print(f"  {i}. {l['symbol']} ({l['name']}): ${l['start_mc']/1e6:.1f}M → ${l['bottom_mc']/1e6:.1f}M = {l['loss_pct']}% | {l['start_date']} → {l['bottom_date']}")

    # JSON
    output = {
        "generated": datetime.now().isoformat(),
        "attribution": ATTRIBUTION,
        "params": {
            "max_mc_before_growth": MAX_MC_BEFORE_GROWTH,
            "min_growth_multiplier": MIN_GROWTH_MULTIPLIER,
            "min_loss_percent": MIN_LOSS_PERCENT,
            "lookback_days": LOOKBACK_DAYS,
            "min_age_days": MIN_AGE_DAYS,
        },
        "winners": winners,
        "losers": losers,
        "errors_count": len(errors),
    }
    out_path = output_dir / "candidates.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nСохранено: {out_path}")
    print(ATTRIBUTION)

    if errors:
        print(f"Ошибки: {len(errors)} токенов пропущено")


if __name__ == "__main__":
    main()
