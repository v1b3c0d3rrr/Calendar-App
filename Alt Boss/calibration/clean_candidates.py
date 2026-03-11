"""
Очистка результатов find_candidates.py от шума.
Убираем стейблкоины, tokenized stocks, vault products, wrapped tokens.

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import json
from pathlib import Path

data = json.load(open(Path(__file__).parent / "candidates.json"))

# Категории для исключения (по coin_id или symbol)
EXCLUDE_IDS = {
    # Stablecoins / pegged to fiat
    "re-protocol-reusd", "brz", "rupiah-token", "precious-metals-usd",
    "etherfuse-ustry", "dialectic-usd-vault", "usdu", "crclon",
    "first-digital-usd", "usdd", "gemini-dollar", "trueusd",
    "paxos-standard", "frax", "fei-usd", "reserve-rights-token",
    "rai", "alchemix-usd", "ageur", "celo-dollar", "celo-euro",
    "dola-usd", "origin-dollar", "bean", "float-protocol", "gyen",
    "bidr", "jpyc", "tryb", "xsgd", "eurs", "stasis-eurs",
    "sperax-usd", "husd",

    # Tokenized stocks / real world assets (non-crypto)
    "occidental-petroleum-ondo-tokenized",
    "private-aviation-finance-token",

    # Vault / yield products (price = NAV, not market)
    "nest-blackopal-liquidstone-ii-vault",
    "dialectic-usd-vault",
    "midas-mmev",

    # Wrapped / liquid staking derivatives
    "wrapped-bitcoin", "wrapped-ether", "weth",
    "staked-ether", "rocket-pool-eth", "coinbase-wrapped-staked-eth",

    # Gold-backed
    "tether-gold", "pax-gold",
}

EXCLUDE_SYMBOLS = {
    "REUSD", "BRZ", "IDRT", "PMUSD", "USTRY", "DUSD", "USDU",
    "OXYON", "NOPAL", "MMEV", "CINO",
}

# Also exclude if name contains these keywords (case-insensitive)
EXCLUDE_NAME_KEYWORDS = [
    "tokenized", "vault", "wrapped", "staked",
    "usd vault", "liquidstone",
]


def should_exclude(entry):
    if entry["coin_id"] in EXCLUDE_IDS:
        return True
    if entry["symbol"] in EXCLUDE_SYMBOLS:
        return True
    name_lower = entry["name"].lower()
    for kw in EXCLUDE_NAME_KEYWORDS:
        if kw in name_lower:
            return True
    return False


# Clean winners
clean_winners = [w for w in data["winners"] if not should_exclude(w)]
clean_losers = [l for l in data["losers"] if not should_exclude(l)]

# Find coins that appear in BOTH winners and losers (pump & dump)
winner_ids = {w["coin_id"] for w in clean_winners}
loser_ids = {l["coin_id"] for l in clean_losers}
both = winner_ids & loser_ids

print(f"=== CLEANING RESULTS ===")
print(f"Raw: {len(data['winners'])} winners, {len(data['losers'])} losers")
print(f"After exclude: {len(clean_winners)} winners, {len(clean_losers)} losers")
print(f"Appear in BOTH lists: {len(both)} tokens")
if both:
    for cid in sorted(both):
        w = next(x for x in clean_winners if x["coin_id"] == cid)
        l = next(x for x in clean_losers if x["coin_id"] == cid)
        print(f"  {w['symbol']:10} W: {w['multiplier']}x ({w['start_date']})  L: {l['loss_pct']}% ({l['start_date']})")

# For winners: remove those that also appear as losers (pump & dump pattern)
pure_winners = [w for w in clean_winners if w["coin_id"] not in both]
# For losers: keep all (including pump&dump — they DID lose 50%+)
pure_losers = clean_losers

# Sort
pure_winners.sort(key=lambda x: x["multiplier"], reverse=True)
pure_losers.sort(key=lambda x: x["loss_pct"])

print(f"\nFinal: {len(pure_winners)} pure winners, {len(pure_losers)} losers")

# Display top winners
print(f"\n{'='*80}")
print(f"TOP 40 PURE WINNERS (MC <$30M → 2x+, no stables/vaults/pump&dump)")
print(f"{'='*80}")
for i, w in enumerate(pure_winners[:40], 1):
    print(f"{i:2}. {w['symbol']:10} {w['name'][:35]:35} "
          f"${w['start_mc']/1e6:6.1f}M → ${w['peak_mc']/1e6:7.1f}M = {w['multiplier']:5.1f}x  "
          f"({w['start_date']} → {w['peak_date']})")

print(f"\n{'='*80}")
print(f"TOP 20 LOSERS (MC $10-30M → -50%+)")
print(f"{'='*80}")
for i, l in enumerate(pure_losers[:20], 1):
    print(f"{i:2}. {l['symbol']:10} {l['name'][:35]:35} "
          f"${l['start_mc']/1e6:6.1f}M → ${l['bottom_mc']/1e6:7.1f}M = {l['loss_pct']:6.1f}%  "
          f"({l['start_date']} → {l['bottom_date']})")

# Save cleaned results
output = {
    "generated": data["generated"],
    "attribution": data["attribution"],
    "params": data["params"],
    "pure_winners": pure_winners,
    "pump_and_dump": [w for w in clean_winners if w["coin_id"] in both],
    "losers": pure_losers,
    "excluded_count": len(data["winners"]) - len(clean_winners) + len(data["losers"]) - len(clean_losers),
}

out_path = Path(__file__).parent / "candidates_clean.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nСохранено: {out_path}")
print("Data provided by CoinGecko (https://www.coingecko.com/en/api/)")
