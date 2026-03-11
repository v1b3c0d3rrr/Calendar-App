"""
Phase 5 v2: Improved backtest with scoring approach and multi-timeframe.

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import json
from pathlib import Path

data = json.load(open(Path(__file__).parent / "metrics_full.json"))
tokens = data["tokens"]


def score_token(t):
    """Score a token 0-100 based on calibrated thresholds. Uses best signal across timeframes."""
    score = 0
    details = t.get("details", {})
    derived = t.get("derived", {})

    # 1. Vol/MC ratio (25 pts) — best across any timeframe
    best_vol_mc = 0
    for tf in ["T-30", "T-14", "T-7", "T-1"]:
        vm = (t.get("timeframes", {}).get(tf, {}) or {}).get("volume_mc_ratio")
        if vm and vm > best_vol_mc:
            best_vol_mc = vm

    if best_vol_mc > 0.10:
        score += 25
    elif best_vol_mc > 0.05:
        score += 20
    elif best_vol_mc > 0.03:
        score += 15
    elif best_vol_mc > 0.01:
        score += 8
    elif best_vol_mc > 0.005:
        score += 3
    # < 0.005 = 0 pts

    # 2. MC/FDV ratio (20 pts)
    mc_fdv = derived.get("mc_fdv_ratio")
    if mc_fdv is not None:
        if mc_fdv < 0.10:
            score += 20
        elif mc_fdv < 0.20:
            score += 16
        elif mc_fdv < 0.30:
            score += 12
        elif mc_fdv < 0.50:
            score += 6
        elif mc_fdv < 0.70:
            score += 2
        # > 0.7 = 0 pts

    # 3. Supply ratio (15 pts)
    supply = derived.get("supply_ratio")
    if supply is not None:
        if supply < 0.25:
            score += 15
        elif supply < 0.40:
            score += 12
        elif supply < 0.60:
            score += 8
        elif supply < 0.80:
            score += 4
        # > 0.8 = 0 pts

    # 4. Price momentum at T-7 (15 pts)
    pr7 = (t.get("timeframes", {}).get("T-7", {}) or {}).get("price_change_7d_pct")
    if pr7 is not None:
        if pr7 > 20:
            score += 15
        elif pr7 > 10:
            score += 12
        elif pr7 > 5:
            score += 10
        elif pr7 > 0:
            score += 6
        elif pr7 > -10:
            score += 2
        # < -10 = 0 pts

    # 5. Absolute volume (10 pts) — best across timeframes
    best_vol = 0
    for tf in ["T-30", "T-14", "T-7", "T-1"]:
        v = (t.get("timeframes", {}).get(tf, {}) or {}).get("avg_volume_7d")
        if v and v > best_vol:
            best_vol = v

    if best_vol > 2_000_000:
        score += 10
    elif best_vol > 500_000:
        score += 7
    elif best_vol > 100_000:
        score += 4
    elif best_vol > 50_000:
        score += 1
    # < $50K = 0 pts

    # 6. Volatility at T-7 (10 pts) — active market
    vol14 = (t.get("timeframes", {}).get("T-7", {}) or {}).get("volatility_14d_pct")
    if vol14 is not None:
        if 5 <= vol14 <= 20:
            score += 10  # sweet spot
        elif 3 <= vol14 < 5 or 20 < vol14 <= 30:
            score += 5
        elif vol14 < 2:
            score += 0   # dead
        else:
            score += 2   # too volatile

    # 7. Dev activity (5 pts)
    commits = details.get("github_commit_count_4_weeks")
    if commits and commits > 20:
        score += 5
    elif commits and commits > 5:
        score += 3
    elif details.get("has_github"):
        score += 1

    return score, best_vol_mc, mc_fdv, pr7, best_vol


# Test different thresholds
for buy_threshold in [40, 45, 50, 55]:
    print(f"\n{'='*90}")
    print(f"THRESHOLD: BUY if score >= {buy_threshold}")
    print("=" * 90)

    w_buy, w_total = 0, 0
    c_buy, c_total = 0, 0
    l_buy, l_total = 0, 0

    for cid, t in tokens.items():
        if "error" in t:
            continue
        group = t["group"]
        score, vm, mf, pr, vol = score_token(t)
        signal = "BUY" if score >= buy_threshold else "SKIP"

        if group == "winner":
            w_total += 1
            if signal == "BUY":
                w_buy += 1
        elif group == "control":
            c_total += 1
            if signal == "BUY":
                c_buy += 1
        elif group == "loser":
            l_total += 1
            if signal == "BUY":
                l_buy += 1

    hit_rate = w_buy / w_total * 100 if w_total else 0
    fp_rate = l_buy / l_total * 100 if l_total else 0
    print(f"  Hit rate:        {w_buy}/{w_total} = {hit_rate:.0f}%  {'✓' if hit_rate >= 70 else '✗'}")
    print(f"  Control BUY:     {c_buy}/{c_total}")
    print(f"  FP rate:         {l_buy}/{l_total} = {fp_rate:.0f}%  {'✓' if fp_rate <= 30 else '✗'}")
    print(f"  Catastrophic FP: {l_buy}  {'✓' if l_buy == 0 else '✗'}")

# Detailed output at best threshold
print(f"\n\n{'='*90}")
print(f"DETAILED RESULTS (threshold = 45)")
print("=" * 90)

all_scored = []
for cid, t in tokens.items():
    if "error" in t:
        continue
    score, vm, mf, pr, vol = score_token(t)
    all_scored.append((t["group"], t["symbol"], score, vm, mf, pr, vol, t.get("outcome", {})))

all_scored.sort(key=lambda x: x[2], reverse=True)

print(f"{'Group':8} {'Symbol':10} {'Score':>5} {'Signal':6} {'BestVol/MC':>10} {'MC/FDV':>8} {'Pr7d':>8} {'BestVol':>10} {'Outcome':>10}")
print("-" * 85)
for group, sym, score, vm, mf, pr, vol, outcome in all_scored:
    signal = "BUY" if score >= 45 else "SKIP"
    mult = outcome.get("multiplier")
    loss = outcome.get("loss_pct")
    out = f"{mult}x" if mult else f"{loss}%" if loss else "flat"

    marker = ""
    if group == "winner" and signal == "SKIP":
        marker = " ← MISS"
    elif group == "loser" and signal == "BUY":
        marker = " ← FP!"

    print(f"{group:8} {sym:10} {score:>5} {signal:6} "
          f"{str(round(vm,3)) if vm else 'N/A':>10} "
          f"{str(round(mf,3)) if mf else 'N/A':>8} "
          f"{str(round(pr,1)) if pr is not None else 'N/A':>8} "
          f"{'$'+str(round(vol/1e6,1))+'M' if vol else 'N/A':>10} "
          f"{out:>10}{marker}")

print(f"\nData provided by CoinGecko (https://www.coingecko.com/en/api/)")
