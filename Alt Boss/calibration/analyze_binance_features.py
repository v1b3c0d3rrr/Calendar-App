"""
Phase 6-9: Analyze Binance derivatives data — winners vs losers.
Compute discrimination ratios, Mann-Whitney U tests, cluster analysis.
"""

import json
import os
import numpy as np
from datetime import datetime, timezone
from scipy import stats
from pathlib import Path

CALIBRATION_DIR = Path(__file__).parent

def load_data():
    with open(CALIBRATION_DIR / "binance_derivatives_data.json") as f:
        deriv = json.load(f)
    with open(CALIBRATION_DIR / "binance_sample.json") as f:
        sample = json.load(f)
    return deriv, sample

def safe_get(d, *keys):
    """Safely navigate nested dict, return None if any key missing."""
    for k in keys:
        if d is None or not isinstance(d, dict):
            return None
        d = d.get(k)
    return d

def extract_metric(tokens, group, section, metric):
    """Extract metric values for a group (winner/loser), skipping None."""
    vals = []
    for t in tokens.values():
        if t["group"] != group:
            continue
        v = safe_get(t, section, metric)
        if v is not None and not (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            vals.append(v)
    return vals

def analyze_metric(tokens, section, metric, name):
    """Compare winners vs losers for a metric."""
    w = extract_metric(tokens, "winner", section, metric)
    l = extract_metric(tokens, "loser", section, metric)

    if len(w) < 5 or len(l) < 5:
        return None

    w_med = np.median(w)
    l_med = np.median(l)
    w_mean = np.mean(w)
    l_mean = np.mean(l)

    # Discrimination ratio (handle zero/negative)
    if l_med != 0 and w_med != 0:
        if abs(l_med) > 0.0000001:
            disc_ratio = w_med / l_med
        else:
            disc_ratio = float('inf')
    else:
        disc_ratio = None

    # Mann-Whitney U test
    try:
        stat, p_value = stats.mannwhitneyu(w, l, alternative='two-sided')
    except:
        p_value = 1.0

    return {
        "name": name,
        "section": section,
        "metric": metric,
        "winners_n": len(w),
        "losers_n": len(l),
        "winners_median": round(w_med, 6),
        "losers_median": round(l_med, 6),
        "winners_mean": round(w_mean, 6),
        "losers_mean": round(l_mean, 6),
        "winners_p25": round(np.percentile(w, 25), 6),
        "winners_p75": round(np.percentile(w, 75), 6),
        "losers_p25": round(np.percentile(l, 25), 6),
        "losers_p75": round(np.percentile(l, 75), 6),
        "discrimination_ratio": round(disc_ratio, 3) if disc_ratio and disc_ratio != float('inf') else None,
        "p_value": round(p_value, 6),
        "significant": p_value < 0.05,
    }

def main():
    deriv, sample = load_data()
    tokens = deriv["tokens"]

    # Build MC lookup from sample
    mc_lookup = {}
    for w in sample["winners"]:
        mc_lookup[w["symbol"]] = {"mc": w.get("start_mc"), "mult": w.get("multiplier"), "group": "winner"}
    for l in sample["losers"]:
        mc_lookup[l["symbol"]] = {"mc": l.get("start_mc"), "drop": l.get("drop_pct"), "group": "loser"}

    print("=" * 80)
    print("  BINANCE DERIVATIVES CALIBRATION — ANALYSIS")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)

    # ════════════════════════════════════════════
    # PHASE 6: Statistical Analysis
    # ════════════════════════════════════════════

    metrics_to_test = [
        # Spot volume
        ("spot", "vol_7d_avg_t7", "Spot Vol 7d avg (T-7)"),
        ("spot", "vol_7d_avg_t30", "Spot Vol 7d avg (T-30)"),
        ("spot", "taker_buy_ratio_t7", "Spot Taker Buy Ratio (T-7)"),
        ("spot", "taker_buy_ratio_t30", "Spot Taker Buy Ratio (T-30)"),
        ("spot", "vol_growth_t7", "Spot Vol Growth (T-7 vs T-30)"),

        # Futures volume
        ("futures", "vol_7d_avg_t7", "Futures Vol 7d avg (T-7)"),
        ("futures", "vol_7d_avg_t30", "Futures Vol 7d avg (T-30)"),
        ("futures", "taker_buy_ratio_t7", "Futures Taker Buy Ratio (T-7)"),
        ("futures", "taker_buy_ratio_t30", "Futures Taker Buy Ratio (T-30)"),
        ("futures", "vol_growth_t7", "Futures Vol Growth (T-7 vs T-30)"),
        ("futures", "futures_spot_ratio_t7", "Futures/Spot Vol Ratio (T-7)"),
        ("futures", "futures_spot_ratio_t30", "Futures/Spot Vol Ratio (T-30)"),

        # Funding rate
        ("funding", "avg_30d", "Funding Avg 30d"),
        ("funding", "avg_14d", "Funding Avg 14d"),
        ("funding", "avg_7d", "Funding Avg 7d"),
        ("funding", "persistence_30d", "Funding Persistence 30d (% positive)"),
        ("funding", "max_30d", "Funding Max 30d"),
        ("funding", "annualized_30d", "Funding Annualized 30d"),

        # Basis
        ("basis", "avg_7d", "Basis Avg 7d (% premium)"),
        ("basis", "avg_30d", "Basis Avg 30d (% premium)"),
        ("basis", "persistence_30d", "Basis Persistence 30d (% positive)"),
    ]

    results = []
    for section, metric, name in metrics_to_test:
        r = analyze_metric(tokens, section, metric, name)
        if r:
            results.append(r)

    # Sort by p-value (most significant first)
    results.sort(key=lambda x: x["p_value"])

    print(f"\n{'─'*80}")
    print(f"  PHASE 6: METRIC DISCRIMINATION (sorted by significance)")
    print(f"{'─'*80}")
    print(f"{'Metric':<40s} {'W med':>10s} {'L med':>10s} {'Ratio':>8s} {'p-val':>8s} {'Sig':>4s}")
    print(f"{'─'*40} {'─'*10} {'─'*10} {'─'*8} {'─'*8} {'─'*4}")

    for r in results:
        w_med = r["winners_median"]
        l_med = r["losers_median"]
        # Format numbers
        if abs(w_med) > 1000:
            w_str = f"${w_med/1e6:.2f}M" if abs(w_med) > 1e6 else f"${w_med/1e3:.0f}K"
            l_str = f"${l_med/1e6:.2f}M" if abs(l_med) > 1e6 else f"${l_med/1e3:.0f}K"
        elif abs(w_med) < 0.001:
            w_str = f"{w_med:.6f}"
            l_str = f"{l_med:.6f}"
        else:
            w_str = f"{w_med:.4f}"
            l_str = f"{l_med:.4f}"

        dr = f"{r['discrimination_ratio']:.2f}" if r['discrimination_ratio'] else "N/A"
        sig = "***" if r['p_value'] < 0.001 else "**" if r['p_value'] < 0.01 else "*" if r['p_value'] < 0.05 else ""
        print(f"{r['name']:<40s} {w_str:>10s} {l_str:>10s} {dr:>8s} {r['p_value']:>8.4f} {sig:>4s}")

    # ════════════════════════════════════════════
    # FUNDING RATE HYPOTHESIS TEST
    # ════════════════════════════════════════════
    print(f"\n{'─'*80}")
    print(f"  FUNDING RATE HYPOTHESIS: Persistent positive funding → short squeeze")
    print(f"{'─'*80}")

    w_persist = extract_metric(tokens, "winner", "funding", "persistence_30d")
    l_persist = extract_metric(tokens, "loser", "funding", "persistence_30d")

    if w_persist and l_persist:
        # High persistence (>0.7) distribution
        w_high = sum(1 for x in w_persist if x > 0.7)
        l_high = sum(1 for x in l_persist if x > 0.7)
        w_low = sum(1 for x in w_persist if x < 0.5)
        l_low = sum(1 for x in l_persist if x < 0.5)

        print(f"  Winners: median persistence = {np.median(w_persist):.3f}, mean = {np.mean(w_persist):.3f}")
        print(f"  Losers:  median persistence = {np.median(l_persist):.3f}, mean = {np.mean(l_persist):.3f}")
        print(f"  Winners with high persistence (>0.7): {w_high}/{len(w_persist)} ({w_high/len(w_persist)*100:.0f}%)")
        print(f"  Losers with high persistence (>0.7):  {l_high}/{len(l_persist)} ({l_high/len(l_persist)*100:.0f}%)")
        print(f"  Winners with low persistence (<0.5):  {w_low}/{len(w_persist)} ({w_low/len(w_persist)*100:.0f}%)")
        print(f"  Losers with low persistence (<0.5):   {l_low}/{len(l_persist)} ({l_low/len(l_persist)*100:.0f}%)")

        # Funding × volume interaction
        print(f"\n  Interaction: Funding persistence × Volume growth")
        w_interact = []
        l_interact = []
        for t in tokens.values():
            fp = safe_get(t, "funding", "persistence_30d")
            vg = safe_get(t, "spot", "vol_growth_t7")
            if fp is not None and vg is not None:
                if t["group"] == "winner":
                    w_interact.append(fp * vg)
                else:
                    l_interact.append(fp * vg)
        if w_interact and l_interact:
            stat, p = stats.mannwhitneyu(w_interact, l_interact, alternative='two-sided')
            print(f"  Winners: median interaction = {np.median(w_interact):.4f}")
            print(f"  Losers:  median interaction = {np.median(l_interact):.4f}")
            print(f"  Mann-Whitney p-value = {p:.6f}")

    # Annualized funding comparison
    w_ann = extract_metric(tokens, "winner", "funding", "annualized_30d")
    l_ann = extract_metric(tokens, "loser", "funding", "annualized_30d")
    if w_ann and l_ann:
        print(f"\n  Annualized funding rate:")
        print(f"  Winners: median {np.median(w_ann)*100:.2f}%, mean {np.mean(w_ann)*100:.2f}%")
        print(f"  Losers:  median {np.median(l_ann)*100:.2f}%, mean {np.mean(l_ann)*100:.2f}%")

    # ════════════════════════════════════════════
    # TAKER BUY RATIO ANALYSIS
    # ════════════════════════════════════════════
    print(f"\n{'─'*80}")
    print(f"  TAKER BUY RATIO: Buying pressure signal")
    print(f"{'─'*80}")

    for timeframe in ["t7", "t30"]:
        w_tbr_spot = extract_metric(tokens, "winner", "spot", f"taker_buy_ratio_{timeframe}")
        l_tbr_spot = extract_metric(tokens, "loser", "spot", f"taker_buy_ratio_{timeframe}")
        w_tbr_fut = extract_metric(tokens, "winner", "futures", f"taker_buy_ratio_{timeframe}")
        l_tbr_fut = extract_metric(tokens, "loser", "futures", f"taker_buy_ratio_{timeframe}")

        if w_tbr_spot and l_tbr_spot:
            _, p_spot = stats.mannwhitneyu(w_tbr_spot, l_tbr_spot, alternative='two-sided')
            print(f"  Spot TBR ({timeframe}): W={np.median(w_tbr_spot):.4f} L={np.median(l_tbr_spot):.4f} p={p_spot:.4f}")
        if w_tbr_fut and l_tbr_fut:
            _, p_fut = stats.mannwhitneyu(w_tbr_fut, l_tbr_fut, alternative='two-sided')
            print(f"  Futures TBR ({timeframe}): W={np.median(w_tbr_fut):.4f} L={np.median(l_tbr_fut):.4f} p={p_fut:.4f}")

    # High TBR (>0.55) distribution
    w_high_tbr = [safe_get(t, "spot", "taker_buy_ratio_t7") for t in tokens.values() if t["group"]=="winner"]
    w_high_tbr = [x for x in w_high_tbr if x is not None]
    l_high_tbr = [safe_get(t, "spot", "taker_buy_ratio_t7") for t in tokens.values() if t["group"]=="loser"]
    l_high_tbr = [x for x in l_high_tbr if x is not None]
    if w_high_tbr and l_high_tbr:
        w_above = sum(1 for x in w_high_tbr if x > 0.52)
        l_above = sum(1 for x in l_high_tbr if x > 0.52)
        print(f"  Spot TBR > 0.52: Winners {w_above}/{len(w_high_tbr)} ({w_above/len(w_high_tbr)*100:.0f}%), Losers {l_above}/{len(l_high_tbr)} ({l_above/len(l_high_tbr)*100:.0f}%)")

    # ════════════════════════════════════════════
    # FUTURES/SPOT RATIO ANALYSIS
    # ════════════════════════════════════════════
    print(f"\n{'─'*80}")
    print(f"  FUTURES/SPOT VOLUME RATIO")
    print(f"{'─'*80}")

    w_fsr = extract_metric(tokens, "winner", "futures", "futures_spot_ratio_t7")
    l_fsr = extract_metric(tokens, "loser", "futures", "futures_spot_ratio_t7")
    if w_fsr and l_fsr:
        _, p = stats.mannwhitneyu(w_fsr, l_fsr, alternative='two-sided')
        print(f"  Winners: median={np.median(w_fsr):.3f}, P25={np.percentile(w_fsr,25):.3f}, P75={np.percentile(w_fsr,75):.3f}")
        print(f"  Losers:  median={np.median(l_fsr):.3f}, P25={np.percentile(l_fsr,25):.3f}, P75={np.percentile(l_fsr,75):.3f}")
        print(f"  p-value: {p:.6f}")

        # Distribution: low (<1 = spot-driven), high (>3 = leverage-driven)
        w_low = sum(1 for x in w_fsr if x < 1.0)
        l_low = sum(1 for x in l_fsr if x < 1.0)
        w_high = sum(1 for x in w_fsr if x > 3.0)
        l_high = sum(1 for x in l_fsr if x > 3.0)
        print(f"  Spot-driven (ratio<1): W={w_low}/{len(w_fsr)} ({w_low/len(w_fsr)*100:.0f}%) L={l_low}/{len(l_fsr)} ({l_low/len(l_fsr)*100:.0f}%)")
        print(f"  Leverage-heavy (ratio>3): W={w_high}/{len(w_fsr)} ({w_high/len(w_fsr)*100:.0f}%) L={l_high}/{len(l_fsr)} ({l_high/len(l_fsr)*100:.0f}%)")

    # ════════════════════════════════════════════
    # PHASE 7: MC INTERACTION
    # ════════════════════════════════════════════
    print(f"\n{'─'*80}")
    print(f"  PHASE 7: MARKET CAP INTERACTION")
    print(f"{'─'*80}")

    w_mc = [(mc_lookup.get(t["symbol"],{}).get("mc") or 0) for t in tokens.values() if t["group"]=="winner"]
    l_mc = [(mc_lookup.get(t["symbol"],{}).get("mc") or 0) for t in tokens.values() if t["group"]=="loser"]
    w_mc_valid = [m for m in w_mc if m > 0]
    l_mc_valid = [m for m in l_mc if m > 0]

    if w_mc_valid and l_mc_valid:
        print(f"  Winners MC: median ${np.median(w_mc_valid)/1e6:.1f}M, mean ${np.mean(w_mc_valid)/1e6:.1f}M (n={len(w_mc_valid)})")
        print(f"  Losers MC:  median ${np.median(l_mc_valid)/1e6:.1f}M, mean ${np.mean(l_mc_valid)/1e6:.1f}M (n={len(l_mc_valid)})")
        _, p = stats.mannwhitneyu(w_mc_valid, l_mc_valid, alternative='two-sided')
        print(f"  p-value: {p:.6f}")

    # MC × Funding interaction: among small MC (<$100M), does funding matter more?
    print(f"\n  MC × Funding persistence interaction:")
    for mc_label, mc_min, mc_max in [("Micro <$50M", 0, 50e6), ("Small $50-300M", 50e6, 300e6), ("Mid+ >$300M", 300e6, 1e12)]:
        w_fp = []
        l_fp = []
        for sym, t in tokens.items():
            mc = (mc_lookup.get(sym, {}).get("mc") or 0)
            if mc < mc_min or mc >= mc_max:
                continue
            fp = safe_get(t, "funding", "persistence_30d")
            if fp is None:
                continue
            if t["group"] == "winner":
                w_fp.append(fp)
            else:
                l_fp.append(fp)
        if len(w_fp) >= 3 and len(l_fp) >= 3:
            print(f"  {mc_label}: W persist={np.median(w_fp):.3f} (n={len(w_fp)}), L persist={np.median(l_fp):.3f} (n={len(l_fp)})")

    # ════════════════════════════════════════════
    # PHASE 8: CLUSTER-LIKE ANALYSIS
    # ════════════════════════════════════════════
    print(f"\n{'─'*80}")
    print(f"  PHASE 8: MULTIPLIER-BASED SEGMENTATION")
    print(f"{'─'*80}")

    # Segment winners by multiplier
    for label, mult_min, mult_max in [("2-2.5x", 2.0, 2.5), ("2.5-3x", 2.5, 3.0), ("3x+", 3.0, 100)]:
        syms = [w["symbol"] for w in sample["winners"] if mult_min <= w.get("multiplier", 0) < mult_max]
        if len(syms) < 3:
            continue
        fp_vals = [safe_get(tokens.get(s, {}), "funding", "persistence_30d") for s in syms]
        fp_vals = [x for x in fp_vals if x is not None]
        fsr_vals = [safe_get(tokens.get(s, {}), "futures", "futures_spot_ratio_t7") for s in syms]
        fsr_vals = [x for x in fsr_vals if x is not None]
        tbr_vals = [safe_get(tokens.get(s, {}), "spot", "taker_buy_ratio_t7") for s in syms]
        tbr_vals = [x for x in tbr_vals if x is not None]

        print(f"\n  {label} winners (n={len(syms)}):")
        if fp_vals:
            print(f"    Funding persistence: {np.median(fp_vals):.3f}")
        if fsr_vals:
            print(f"    Futures/Spot ratio: {np.median(fsr_vals):.3f}")
        if tbr_vals:
            print(f"    Spot Taker Buy: {np.median(tbr_vals):.4f}")

    # ════════════════════════════════════════════
    # PHASE 9: SUMMARY & THRESHOLDS
    # ════════════════════════════════════════════
    print(f"\n{'='*80}")
    print(f"  TOP DISCRIMINATING FEATURES (by p-value)")
    print(f"{'='*80}")

    significant = [r for r in results if r["p_value"] < 0.05]
    for i, r in enumerate(significant[:10], 1):
        print(f"  {i}. {r['name']}")
        print(f"     Winners: {r['winners_median']} (P25={r['winners_p25']}, P75={r['winners_p75']})")
        print(f"     Losers:  {r['losers_median']} (P25={r['losers_p25']}, P75={r['losers_p75']})")
        print(f"     Ratio: {r['discrimination_ratio']}, p={r['p_value']:.6f}")

    not_significant = [r for r in results if r["p_value"] >= 0.05]
    if not_significant:
        print(f"\n  NOT SIGNIFICANT (p >= 0.05):")
        for r in not_significant:
            print(f"    {r['name']}: W={r['winners_median']}, L={r['losers_median']}, p={r['p_value']:.4f}")

    # Save results
    output = {
        "metadata": {
            "created": datetime.now(timezone.utc).isoformat(),
            "winners": 137,
            "losers": 67,
        },
        "metrics": results,
        "significant_metrics": [r for r in results if r["significant"]],
    }

    with open(CALIBRATION_DIR / "binance_analysis_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n✓ Results saved to calibration/binance_analysis_results.json")

    # ════════════════════════════════════════════
    # GENERATE REPORT
    # ════════════════════════════════════════════
    generate_report(results, tokens, sample, mc_lookup)


def generate_report(results, tokens, sample, mc_lookup):
    """Generate markdown report in Russian."""

    sig = [r for r in results if r["significant"]]
    not_sig = [r for r in results if not r["significant"]]

    report = f"""# Калибровка деривативных метрик Binance

Дата: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}

## Выборка
- **Winners**: 137 токенов (2x+ за 30 дней, MC $5M-$2B, листинг на Binance спот+фьючерсы)
- **Losers**: 67 токенов (-50%+ за 30 дней)
- **Данные**: spot klines, futures klines, funding rate, basis (T-60 to T+5)
- Доступность данных: spot ~173, futures ~182, funding ~187, basis ~175 токенов

## Ключевые находки (по статистической значимости)

### Значимые метрики (p < 0.05)

| # | Метрика | Winners median | Losers median | Ratio | p-value |
|---|---------|---------------|--------------|-------|---------|
"""
    for i, r in enumerate(sig, 1):
        report += f"| {i} | {r['name']} | {r['winners_median']} | {r['losers_median']} | {r['discrimination_ratio']} | {r['p_value']:.6f} |\n"

    report += f"""
### Незначимые метрики (p >= 0.05)

| Метрика | Winners median | Losers median | p-value |
|---------|---------------|--------------|---------|
"""
    for r in not_sig:
        report += f"| {r['name']} | {r['winners_median']} | {r['losers_median']} | {r['p_value']:.4f} |\n"

    # Funding hypothesis
    w_persist = extract_metric(tokens, "winner", "funding", "persistence_30d")
    l_persist = extract_metric(tokens, "loser", "funding", "persistence_30d")
    w_ann = extract_metric(tokens, "winner", "funding", "annualized_30d")
    l_ann = extract_metric(tokens, "loser", "funding", "annualized_30d")

    report += f"""
## Гипотеза фандинга

**Тезис**: Устойчивый положительный фандинг за 30 дней до пампа = накопление шортов → топливо для short squeeze.

**Результаты**:
- Winners funding persistence: median {np.median(w_persist):.3f} (mean {np.mean(w_persist):.3f})
- Losers funding persistence: median {np.median(l_persist):.3f} (mean {np.mean(l_persist):.3f})
"""
    if w_persist and l_persist:
        w_high = sum(1 for x in w_persist if x > 0.7)
        l_high = sum(1 for x in l_persist if x > 0.7)
        report += f"""- Winners с high persistence (>0.7): {w_high}/{len(w_persist)} ({w_high/len(w_persist)*100:.0f}%)
- Losers с high persistence (>0.7): {l_high}/{len(l_persist)} ({l_high/len(l_persist)*100:.0f}%)
"""

    if w_ann and l_ann:
        report += f"""
**Annualized funding**:
- Winners: median {np.median(w_ann)*100:.2f}%
- Losers: median {np.median(l_ann)*100:.2f}%
"""

    # Futures/Spot ratio
    w_fsr = extract_metric(tokens, "winner", "futures", "futures_spot_ratio_t7")
    l_fsr = extract_metric(tokens, "loser", "futures", "futures_spot_ratio_t7")
    if w_fsr and l_fsr:
        report += f"""
## Соотношение фьючерсы/спот

- Winners median: {np.median(w_fsr):.3f}
- Losers median: {np.median(l_fsr):.3f}
"""
        w_low = sum(1 for x in w_fsr if x < 1.0)
        l_low = sum(1 for x in l_fsr if x < 1.0)
        w_hi = sum(1 for x in w_fsr if x > 3.0)
        l_hi = sum(1 for x in l_fsr if x > 3.0)
        report += f"""- Spot-driven (ratio<1): Winners {w_low}/{len(w_fsr)} ({w_low/len(w_fsr)*100:.0f}%), Losers {l_low}/{len(l_fsr)} ({l_low/len(l_fsr)*100:.0f}%)
- Leverage-heavy (ratio>3): Winners {w_hi}/{len(w_fsr)} ({w_hi/len(w_fsr)*100:.0f}%), Losers {l_hi}/{len(l_fsr)} ({l_hi/len(l_fsr)*100:.0f}%)
"""

    # Thresholds
    report += """
## Калиброванные пороги (предварительные)

На основе распределения winners vs losers:

| Метрика | Buy Zone | Neutral | Avoid |
|---------|----------|---------|-------|
"""

    # Generate thresholds based on data
    threshold_metrics = [
        ("Funding persistence 30d", "funding", "persistence_30d", True),
        ("Funding annualized 30d", "funding", "annualized_30d", True),
        ("Spot Taker Buy Ratio", "spot", "taker_buy_ratio_t7", True),
        ("Futures/Spot Ratio", "futures", "futures_spot_ratio_t7", None),  # ambiguous direction
        ("Basis avg 7d", "basis", "avg_7d", None),
        ("Spot Vol Growth", "spot", "vol_growth_t7", True),
    ]

    for name, section, metric, higher_better in threshold_metrics:
        w = extract_metric(tokens, "winner", section, metric)
        l = extract_metric(tokens, "loser", section, metric)
        if len(w) < 5 or len(l) < 5:
            continue
        w_p25 = np.percentile(w, 25)
        w_med = np.median(w)
        l_med = np.median(l)

        if higher_better is True:
            buy = f"> {w_p25:.4f}"
            neutral = f"{l_med:.4f} - {w_p25:.4f}"
            avoid = f"< {l_med:.4f}"
        elif higher_better is False:
            buy = f"< {w_p25:.4f}"
            neutral = f"{w_p25:.4f} - {l_med:.4f}"
            avoid = f"> {l_med:.4f}"
        else:
            buy = f"~{w_med:.4f}"
            neutral = f"—"
            avoid = f"~{l_med:.4f}"

        report += f"| {name} | {buy} | {neutral} | {avoid} |\n"

    report += """
## Рекомендации для обновления персон

### CC (Cluster Analyst)
- Добавить Futures/Spot volume ratio в Screen B (Vol/MC Spike)
- Сегментировать скоринг по типу объёма: spot-driven vs leverage-driven
- Funding persistence как дополнительный сигнал в кластерах A и E

### CG (Evidence Analyst)
- Добавить Taker Buy Ratio в Microstructure dimension
- Funding rate и basis в Derivatives dimension (вес 0.10)
- Gate check: funding persistence > threshold для entry signal
- Кросс-проверка spot vs futures volume (конфликт = red flag)

### G (Due Diligence)
- Высокий futures/spot ratio (>3) = leverage-driven, риск squeeze в обе стороны
- Extreme funding rate = crowded positioning
- Basis persistence как индикатор рыночных ожиданий
"""

    with open(CALIBRATION_DIR / "binance_calibration_report.md", "w") as f:
        f.write(report)

    print(f"✓ Report saved to calibration/binance_calibration_report.md")


if __name__ == "__main__":
    main()
