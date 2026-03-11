"""
Поиск контрольной группы: токены MC <$30M которые НЕ показали
значимого роста или падения за 6 месяцев (flat, ±30%).

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import sys
import os
import json
import time
import requests
from datetime import datetime
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

# Load progress to know which coins were processed
progress = json.load(open(Path(__file__).parent / "progress.json"))
winner_ids = {w["coin_id"] for w in progress["winners"]}
loser_ids = {l["coin_id"] for l in progress["losers"]}

# Coins that were processed but are neither winners nor losers = potential control
neutral_ids = set(progress["processed_ids"]) - winner_ids - loser_ids
print(f"Neutral coins (no winner/loser pattern): {len(neutral_ids)}")

# We need to find among them those with MC <$30M that stayed flat
# Fetch current market data for a sample
resp = requests.get(f"{BASE_URL}/coins/markets", params={
    "vs_currency": "usd",
    "order": "market_cap_desc",
    "per_page": 250,
    "page": 1,
    "x_cg_demo_api_key": API_KEY,
})
all_coins = resp.json()
time.sleep(2.5)

# Get more pages to find our neutral coins
for page in range(2, 7):
    resp = requests.get(f"{BASE_URL}/coins/markets", params={
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": page,
        "x_cg_demo_api_key": API_KEY,
    })
    all_coins.extend(resp.json())
    time.sleep(2.5)

# Filter: neutral, current MC $5-30M
coin_map = {c["id"]: c for c in all_coins}
control_candidates = []
for cid in neutral_ids:
    if cid in coin_map:
        mc = coin_map[cid].get("market_cap", 0)
        if mc and 5_000_000 < mc < 30_000_000:
            control_candidates.append(coin_map[cid])

control_candidates.sort(key=lambda x: x.get("market_cap", 0), reverse=True)
print(f"Control candidates (MC $5-30M, neutral): {len(control_candidates)}")

# Verify are actually flat by checking their chart
verified = []
for coin in control_candidates[:60]:
    cid = coin["id"]
    try:
        resp = requests.get(f"{BASE_URL}/coins/{cid}/market_chart", params={
            "vs_currency": "usd",
            "days": 180,
            "x_cg_demo_api_key": API_KEY,
        })
        chart = resp.json()
        mcs = [mc for _, mc in chart.get("market_caps", []) if mc and mc > 0]
        if len(mcs) < 30:
            continue

        min_mc = min(mcs)
        max_mc = max(mcs)
        avg_mc = sum(mcs) / len(mcs)
        volatility = (max_mc - min_mc) / avg_mc

        # "Flat" = max/min ratio < 2.5 (no big movement in either direction)
        ratio = max_mc / min_mc if min_mc > 0 else 999
        if ratio < 2.5:
            verified.append({
                "coin_id": cid,
                "symbol": coin["symbol"].upper(),
                "name": coin["name"],
                "current_mc": coin.get("market_cap"),
                "min_mc_6m": round(min_mc),
                "max_mc_6m": round(max_mc),
                "avg_mc_6m": round(avg_mc),
                "max_min_ratio": round(ratio, 2),
                "volatility": round(volatility, 2),
            })
            print(f"  ✓ {coin['symbol'].upper()} ({coin['name']}): MC ${min_mc/1e6:.1f}-{max_mc/1e6:.1f}M, ratio {ratio:.2f}")
        else:
            print(f"  ✗ {coin['symbol'].upper()} ({coin['name']}): too volatile, ratio {ratio:.2f}")

        time.sleep(2.5)
    except Exception as e:
        print(f"  ! {cid}: {e}")
        time.sleep(2.5)

print(f"\nVerified flat control tokens: {len(verified)}")
for i, c in enumerate(verified[:10], 1):
    print(f"  {i}. {c['symbol']:10} {c['name'][:30]:30} MC ${c['avg_mc_6m']/1e6:.1f}M  ratio {c['max_min_ratio']}")

# Save
out = {
    "generated": datetime.now().isoformat(),
    "attribution": "Data provided by CoinGecko (https://www.coingecko.com/en/api/)",
    "control_tokens": verified,
}
out_path = Path(__file__).parent / "control_group.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nСохранено: {out_path}")
print("Data provided by CoinGecko (https://www.coingecko.com/en/api/)")
