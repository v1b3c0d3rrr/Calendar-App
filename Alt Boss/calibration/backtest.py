"""
Phase 5: Backtest — проверка калиброванных порогов на собранных данных.

Применяем 3 ключевых правила к каждому токену и проверяем:
- Hit rate >= 70% (winners правильно идентифицированы как BUY)
- False positive <= 30% (losers НЕ получают BUY)
- Catastrophic FP = 0% (losers НИКОГДА не получают BUY)

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import json
from pathlib import Path

data = json.load(open(Path(__file__).parent / "metrics_full.json"))
tokens = data["tokens"]

# Thresholds from calibration
VOL_MC_THRESHOLD = 0.03       # Vol/MC > 3%
MC_FDV_THRESHOLD = 0.30       # MC/FDV < 30%
PRICE_7D_THRESHOLD = 0.0      # Price 7d > 0%
MIN_RULES_FOR_BUY = 2         # At least 2 out of 3

print("=" * 90)
print("BACKTEST: Calibrated thresholds validation")
print(f"Rules: Vol/MC > {VOL_MC_THRESHOLD}, MC/FDV < {MC_FDV_THRESHOLD}, Price7d > {PRICE_7D_THRESHOLD}%")
print(f"BUY signal: at least {MIN_RULES_FOR_BUY} out of 3 rules pass")
print("=" * 90)

results = {"winner": [], "control": [], "loser": []}

for cid, t in tokens.items():
    if "error" in t:
        continue

    group = t["group"]
    symbol = t["symbol"]
    tf7 = t.get("timeframes", {}).get("T-7", {})

    vol_mc = tf7.get("volume_mc_ratio")
    price_chg = tf7.get("price_change_7d_pct")
    mc_fdv = t.get("derived", {}).get("mc_fdv_ratio")

    # Apply rules
    rule1 = vol_mc is not None and vol_mc > VOL_MC_THRESHOLD
    rule2 = mc_fdv is not None and mc_fdv < MC_FDV_THRESHOLD
    rule3 = price_chg is not None and price_chg > PRICE_7D_THRESHOLD

    rules_passed = sum([rule1, rule2, rule3])
    signal = "BUY" if rules_passed >= MIN_RULES_FOR_BUY else "SKIP"

    outcome = t.get("outcome", {})
    mult = outcome.get("multiplier")
    loss = outcome.get("loss_pct")

    results[group].append({
        "symbol": symbol,
        "signal": signal,
        "rules_passed": rules_passed,
        "rule1_vol_mc": rule1,
        "rule2_mc_fdv": rule2,
        "rule3_price": rule3,
        "vol_mc": vol_mc,
        "mc_fdv": mc_fdv,
        "price_7d": price_chg,
        "multiplier": mult,
        "loss_pct": loss,
    })

# Print detailed results
for group_name in ["winner", "control", "loser"]:
    group_results = results[group_name]
    buys = [r for r in group_results if r["signal"] == "BUY"]

    print(f"\n--- {group_name.upper()}S ({len(group_results)} tokens) ---")
    print(f"{'Symbol':10} {'Signal':6} {'Rules':5} {'Vol/MC':>8} {'MC/FDV':>8} {'Pr7d%':>8} {'Outcome':>10}")
    print("-" * 65)
    for r in group_results:
        outcome = f"{r['multiplier']}x" if r['multiplier'] else f"{r['loss_pct']}%"
        print(f"{r['symbol']:10} {r['signal']:6} {r['rules_passed']}/3   "
              f"{str(round(r['vol_mc'],3)) if r['vol_mc'] else 'N/A':>8} "
              f"{str(round(r['mc_fdv'],3)) if r['mc_fdv'] else 'N/A':>8} "
              f"{str(round(r['price_7d'],1)) if r['price_7d'] is not None else 'N/A':>8} "
              f"{outcome:>10}")

    buy_rate = len(buys) / len(group_results) * 100 if group_results else 0
    print(f"  → BUY signals: {len(buys)}/{len(group_results)} ({buy_rate:.0f}%)")

# Summary
print(f"\n{'='*90}")
print("SUMMARY")
print("=" * 90)

w_total = len(results["winner"])
w_buy = len([r for r in results["winner"] if r["signal"] == "BUY"])
c_total = len(results["control"])
c_buy = len([r for r in results["control"] if r["signal"] == "BUY"])
l_total = len(results["loser"])
l_buy = len([r for r in results["loser"] if r["signal"] == "BUY"])

hit_rate = w_buy / w_total * 100 if w_total else 0
fp_rate = l_buy / l_total * 100 if l_total else 0

print(f"  Hit rate (winners → BUY):        {w_buy}/{w_total} = {hit_rate:.0f}%  {'✓' if hit_rate >= 70 else '✗'} (target ≥70%)")
print(f"  Control (flat → BUY):             {c_buy}/{c_total} = {c_buy/c_total*100 if c_total else 0:.0f}%")
print(f"  False positive (losers → BUY):    {l_buy}/{l_total} = {fp_rate:.0f}%  {'✓' if fp_rate <= 30 else '✗'} (target ≤30%)")
print(f"  Catastrophic FP (losers → BUY):   {l_buy}           {'✓' if l_buy == 0 else '✗ FAIL'} (target = 0)")

print(f"\n  Overall accuracy: {(w_buy + (l_total - l_buy)) / (w_total + l_total) * 100:.0f}%")

# Per-rule breakdown
print(f"\n--- Per-rule hit rates ---")
for rule_name, rule_key in [("Vol/MC > 3%", "rule1_vol_mc"), ("MC/FDV < 30%", "rule2_mc_fdv"), ("Price 7d > 0%", "rule3_price")]:
    w_hits = sum(1 for r in results["winner"] if r[rule_key])
    l_hits = sum(1 for r in results["loser"] if r[rule_key])
    print(f"  {rule_name:20} Winners: {w_hits}/{w_total} ({w_hits/w_total*100:.0f}%)  Losers: {l_hits}/{l_total} ({l_hits/l_total*100:.0f}%)")

print(f"\nData provided by CoinGecko (https://www.coingecko.com/en/api/)")
