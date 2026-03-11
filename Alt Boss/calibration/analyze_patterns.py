"""
Phase 3: Анализ паттернов — сравнение winners vs control vs losers.

Цель: найти метрики, которые ОТЛИЧАЮТ winners от losers и control ПЕРЕД ростом.
Это позволит откалибровать скоринг в персонах.

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import json
import statistics
from pathlib import Path
from datetime import datetime

data = json.load(open(Path(__file__).parent / "metrics_full.json"))
tokens = data["tokens"]

# Группировка
winners = {k: v for k, v in tokens.items() if v.get("group") == "winner" and "error" not in v}
control = {k: v for k, v in tokens.items() if v.get("group") == "control" and "error" not in v}
losers = {k: v for k, v in tokens.items() if v.get("group") == "loser" and "error" not in v}

print(f"Valid data: {len(winners)} winners, {len(control)} control, {len(losers)} losers")
print(f"Missing: {sum(1 for v in tokens.values() if 'error' in v)} tokens")
print()


def safe_median(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 4)


def safe_mean(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.mean(clean), 4)


def extract_metric(group, timeframe, metric):
    """Извлечь значение метрики для всех токенов группы."""
    values = []
    for t in group.values():
        tf = t.get("timeframes", {}).get(timeframe, {})
        if tf:
            values.append(tf.get(metric))
    return values


def extract_detail(group, key):
    """Извлечь деталь для всех токенов группы."""
    values = []
    for t in group.values():
        d = t.get("details", {})
        values.append(d.get(key))
    return values


def extract_derived(group, key):
    values = []
    for t in group.values():
        d = t.get("derived", {})
        values.append(d.get(key))
    return values


# ============================================================
# АНАЛИЗ 1: Метрики на таймфреймах
# ============================================================
print("=" * 80)
print("ANALYSIS 1: Timeframe metrics comparison (median values)")
print("=" * 80)

tf_metrics = [
    ("market_cap", "Market Cap ($)"),
    ("volume_24h", "Volume 24h ($)"),
    ("avg_volume_7d", "Avg Volume 7d ($)"),
    ("price_change_7d_pct", "Price Change 7d (%)"),
    ("volatility_14d_pct", "Volatility 14d (%)"),
    ("volume_mc_ratio", "Volume/MC Ratio"),
]

for tf in ["T-30", "T-14", "T-7", "T-1"]:
    print(f"\n--- {tf} ---")
    print(f"{'Metric':30} {'Winners':>15} {'Control':>15} {'Losers':>15} {'W vs L':>10}")
    print("-" * 85)
    for metric_key, metric_name in tf_metrics:
        w_vals = extract_metric(winners, tf, metric_key)
        c_vals = extract_metric(control, tf, metric_key)
        l_vals = extract_metric(losers, tf, metric_key)

        w_med = safe_median(w_vals)
        c_med = safe_median(c_vals)
        l_med = safe_median(l_vals)

        diff = ""
        if w_med is not None and l_med is not None and l_med != 0:
            ratio = w_med / l_med
            diff = f"{ratio:.2f}x"

        def fmt(v):
            if v is None:
                return "N/A"
            if abs(v) >= 1_000_000:
                return f"${v/1e6:.1f}M"
            if abs(v) >= 1000:
                return f"${v/1e3:.0f}K"
            return f"{v:.4f}"

        print(f"{metric_name:30} {fmt(w_med):>15} {fmt(c_med):>15} {fmt(l_med):>15} {diff:>10}")

# ============================================================
# АНАЛИЗ 2: Volume trend (approaching T-0)
# ============================================================
print(f"\n{'='*80}")
print("ANALYSIS 2: Volume trend approaching T-0")
print("=" * 80)

w_trend = extract_derived(winners, "volume_trend_t30_to_t1")
c_trend = extract_derived(control, "volume_trend_t30_to_t1")
l_trend = extract_derived(losers, "volume_trend_t30_to_t1")

print(f"Volume T-1 / Volume T-30 ratio (>1 = increasing volume):")
print(f"  Winners median: {safe_median(w_trend)}")
print(f"  Control median: {safe_median(c_trend)}")
print(f"  Losers  median: {safe_median(l_trend)}")
print(f"\n  Winners values: {[v for v in w_trend if v is not None]}")
print(f"  Control values: {[v for v in c_trend if v is not None]}")
print(f"  Losers  values: {[v for v in l_trend if v is not None]}")

# ============================================================
# АНАЛИЗ 3: FDV и Supply metrics
# ============================================================
print(f"\n{'='*80}")
print("ANALYSIS 3: FDV & Supply metrics")
print("=" * 80)

for group_name, group in [("Winners", winners), ("Control", control), ("Losers", losers)]:
    mc_fdv = extract_derived(group, "mc_fdv_ratio")
    supply = extract_derived(group, "supply_ratio")
    print(f"\n{group_name}:")
    print(f"  MC/FDV ratio median: {safe_median(mc_fdv)} (values: {[v for v in mc_fdv if v is not None]})")
    print(f"  Supply ratio median: {safe_median(supply)} (values: {[v for v in supply if v is not None]})")

# ============================================================
# АНАЛИЗ 4: Community & Developer metrics
# ============================================================
print(f"\n{'='*80}")
print("ANALYSIS 4: Community & Developer metrics")
print("=" * 80)

community_metrics = [
    "twitter_followers",
    "telegram_channel_user_count",
    "reddit_subscribers",
]
dev_metrics = [
    "github_stars",
    "github_forks",
    "github_commit_count_4_weeks",
    "github_total_issues",
    "github_pull_requests_merged",
]

print(f"\n{'Metric':35} {'Winners':>12} {'Control':>12} {'Losers':>12}")
print("-" * 75)

for m in community_metrics + dev_metrics:
    w = safe_median(extract_detail(winners, m))
    c = safe_median(extract_detail(control, m))
    l = safe_median(extract_detail(losers, m))
    print(f"{m:35} {str(w):>12} {str(c):>12} {str(l):>12}")

# ============================================================
# АНАЛИЗ 5: Has GitHub?
# ============================================================
print(f"\n{'='*80}")
print("ANALYSIS 5: GitHub presence")
print("=" * 80)

for group_name, group in [("Winners", winners), ("Control", control), ("Losers", losers)]:
    has_gh = sum(1 for t in group.values() if t.get("details", {}).get("has_github"))
    total = len(group)
    print(f"  {group_name}: {has_gh}/{total} have GitHub repos ({has_gh/total*100:.0f}%)")

# ============================================================
# АНАЛИЗ 6: Price action before T-0
# ============================================================
print(f"\n{'='*80}")
print("ANALYSIS 6: Price action before T-0 (consolidation vs trending)")
print("=" * 80)

for tf in ["T-30", "T-14", "T-7", "T-1"]:
    w_chg = extract_metric(winners, tf, "price_change_7d_pct")
    c_chg = extract_metric(control, tf, "price_change_7d_pct")
    l_chg = extract_metric(losers, tf, "price_change_7d_pct")

    w_vol = extract_metric(winners, tf, "volatility_14d_pct")
    c_vol = extract_metric(control, tf, "volatility_14d_pct")
    l_vol = extract_metric(losers, tf, "volatility_14d_pct")

    print(f"\n  {tf}:")
    print(f"    Price 7d change: W={safe_median(w_chg)}%  C={safe_median(c_chg)}%  L={safe_median(l_chg)}%")
    print(f"    Volatility 14d:  W={safe_median(w_vol)}%  C={safe_median(c_vol)}%  L={safe_median(l_vol)}%")

# ============================================================
# АНАЛИЗ 7: Категории (нарративы)
# ============================================================
print(f"\n{'='*80}")
print("ANALYSIS 7: Categories/Narratives")
print("=" * 80)

from collections import Counter

for group_name, group in [("Winners", winners), ("Control", control), ("Losers", losers)]:
    cats = Counter()
    for t in group.values():
        for cat in t.get("details", {}).get("categories", []):
            if cat:
                cats[cat] += 1
    print(f"\n{group_name} top categories:")
    for cat, cnt in cats.most_common(10):
        print(f"  {cnt}x {cat}")

# ============================================================
# АНАЛИЗ 8: Индивидуальные профили winners
# ============================================================
print(f"\n{'='*80}")
print("ANALYSIS 8: Individual winner profiles at T-7")
print("=" * 80)

print(f"{'Symbol':10} {'MC T-7':>10} {'Vol/MC':>8} {'PrChg7d':>8} {'Vol14d':>8} {'VolTrend':>8} {'MC/FDV':>8} {'Twitter':>10} {'Commits':>8} {'Mult':>6}")
print("-" * 100)
for cid, t in sorted(winners.items(), key=lambda x: x[1].get("outcome", {}).get("multiplier", 0), reverse=True):
    tf7 = t.get("timeframes", {}).get("T-7", {})
    mc = tf7.get("market_cap")
    vol_mc = tf7.get("volume_mc_ratio")
    pr_chg = tf7.get("price_change_7d_pct")
    vol14 = tf7.get("volatility_14d_pct")
    v_trend = t.get("derived", {}).get("volume_trend_t30_to_t1")
    mc_fdv = t.get("derived", {}).get("mc_fdv_ratio")
    twitter = t.get("details", {}).get("twitter_followers")
    commits = t.get("details", {}).get("github_commit_count_4_weeks")
    mult = t.get("outcome", {}).get("multiplier")

    print(f"{t['symbol']:10} "
          f"{'$'+str(round(mc/1e6,1))+'M' if mc else 'N/A':>10} "
          f"{str(round(vol_mc,3)) if vol_mc else 'N/A':>8} "
          f"{str(round(pr_chg,1))+'%' if pr_chg is not None else 'N/A':>8} "
          f"{str(round(vol14,1))+'%' if vol14 is not None else 'N/A':>8} "
          f"{str(v_trend) if v_trend else 'N/A':>8} "
          f"{str(mc_fdv) if mc_fdv else 'N/A':>8} "
          f"{str(twitter) if twitter else 'N/A':>10} "
          f"{str(commits) if commits else 'N/A':>8} "
          f"{str(mult)+'x' if mult else '':>6}")

# ============================================================
# SUMMARY: Key discriminating factors
# ============================================================
print(f"\n{'='*80}")
print("SUMMARY: Key discriminating factors (Winners vs Losers)")
print("=" * 80)

findings = []

# Volume/MC at T-7
w_volmc = safe_median(extract_metric(winners, "T-7", "volume_mc_ratio"))
l_volmc = safe_median(extract_metric(losers, "T-7", "volume_mc_ratio"))
if w_volmc and l_volmc:
    findings.append(f"1. Volume/MC ratio at T-7: Winners {w_volmc} vs Losers {l_volmc}")

# Volatility at T-7
w_v = safe_median(extract_metric(winners, "T-7", "volatility_14d_pct"))
l_v = safe_median(extract_metric(losers, "T-7", "volatility_14d_pct"))
if w_v and l_v:
    findings.append(f"2. Volatility 14d at T-7: Winners {w_v}% vs Losers {l_v}%")

# Volume trend
w_vt = safe_median(w_trend)
l_vt = safe_median(l_trend)
if w_vt and l_vt:
    findings.append(f"3. Volume trend T-30→T-1: Winners {w_vt}x vs Losers {l_vt}x")

# MC/FDV
w_mf = safe_median(extract_derived(winners, "mc_fdv_ratio"))
l_mf = safe_median(extract_derived(losers, "mc_fdv_ratio"))
if w_mf and l_mf:
    findings.append(f"4. MC/FDV ratio: Winners {w_mf} vs Losers {l_mf}")

# GitHub
w_gh = sum(1 for t in winners.values() if t.get("details", {}).get("has_github"))
l_gh = sum(1 for t in losers.values() if t.get("details", {}).get("has_github"))
findings.append(f"5. GitHub presence: Winners {w_gh}/{len(winners)} vs Losers {l_gh}/{len(losers)}")

# Twitter
w_tw = safe_median(extract_detail(winners, "twitter_followers"))
l_tw = safe_median(extract_detail(losers, "twitter_followers"))
if w_tw and l_tw:
    findings.append(f"6. Twitter followers: Winners {w_tw} vs Losers {l_tw}")

# Price action at T-7
w_pa = safe_median(extract_metric(winners, "T-7", "price_change_7d_pct"))
l_pa = safe_median(extract_metric(losers, "T-7", "price_change_7d_pct"))
if w_pa is not None and l_pa is not None:
    findings.append(f"7. Price 7d change at T-7: Winners {w_pa}% vs Losers {l_pa}%")

for f in findings:
    print(f"  {f}")

# Save analysis results
output = {
    "generated": datetime.now().isoformat(),
    "attribution": "Data provided by CoinGecko (https://www.coingecko.com/en/api/)",
    "sample_sizes": {"winners": len(winners), "control": len(control), "losers": len(losers)},
    "findings": findings,
}
out_path = Path(__file__).parent / "analysis_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nSaved: {out_path}")
