"""
Anomaly detection: behavioral pattern changes in T-7→T vs T-14→T-7.

Focus on detecting coordinated/manipulative activity without requiring
explicit MM labels. Key insight: MMs use dozens of addresses, so we look
for patterns that indicate coordination rather than individual labels.

Metrics computed per token:
1. COORDINATION METRICS:
   - synchronized_action_score: addresses acting within ±5 min windows
   - burst_ratio: max-hourly / avg-hourly transfer rate (spikes)
   - concentration_delta: change in top-10 address share

2. ACCUMULATION METRICS:
   - smart_money_inflow: CEX→whale addresses volume ratio
   - new_whale_emergence: whales appearing only in signal period
   - whale_buy_sell_ratio: whale buys / whale sells

3. CEX-DEX BRIDGE METRICS:
   - cex_to_dex_ratio: tokens moving CEX→DEX (accumulation signal)
   - dex_to_cex_ratio: tokens moving DEX→CEX (distribution signal)
   - bridge_address_count: addresses touching both CEX and DEX

4. VELOCITY METRICS:
   - transfer_acceleration: signal period tx count / baseline tx count
   - volume_acceleration: signal period volume / baseline volume
   - unique_addr_acceleration: signal period unique addrs / baseline
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional
import numpy as np
from scipy.stats import mannwhitneyu

sys.path.insert(0, str(Path(__file__).parent))
from label_db import LabelDB

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSFERS_DIR = DATA_DIR / "transfers"
OUTPUT_FILE = DATA_DIR / "mm_anomaly_analysis.json"
REPORT_FILE = DATA_DIR / "mm_anomaly_report.md"

WHALE_VOLUME_PCT = 0.03  # >3% of total volume = whale
TEMPORAL_WINDOW = 300  # 5 minutes


def compute_token_anomalies(coin_id: str, db: LabelDB) -> Optional[dict]:
    """Compute all anomaly metrics for a single token."""
    fpath = TRANSFERS_DIR / f"{coin_id}.json"
    if not fpath.exists():
        return None
    with open(fpath) as f:
        data = json.load(f)

    transfers = data.get("transfers", [])
    if len(transfers) < 10:
        return None

    category = data.get("category", "unknown")
    chain_id = data.get("chain_id", 1)
    ts_t14 = data["timestamps"]["t_minus_14"]
    ts_t7 = data["timestamps"]["t_minus_7"]
    ts_t = data["timestamps"]["t_event"]

    # Label all addresses
    all_addrs = set()
    for t in transfers:
        all_addrs.add(t["from"].lower())
        all_addrs.add(t["to"].lower())

    labels = {}
    for addr in all_addrs:
        label = db.lookup(addr, chain_id)
        if label:
            labels[addr] = label

    # Split transfers into baseline and signal periods
    baseline = []
    signal = []
    for t in transfers:
        ts = int(t["timeStamp"])
        if ts_t14 <= ts < ts_t7:
            baseline.append(t)
        elif ts_t7 <= ts <= ts_t:
            signal.append(t)

    if not baseline and not signal:
        return None

    metrics = {"coin_id": coin_id, "category": category, "chain_id": chain_id}

    # === 1. VELOCITY METRICS ===
    n_baseline = len(baseline)
    n_signal = len(signal)
    metrics["transfer_acceleration"] = n_signal / max(n_baseline, 1)

    vol_baseline = sum(int(t.get("value", 0)) for t in baseline)
    vol_signal = sum(int(t.get("value", 0)) for t in signal)
    metrics["volume_acceleration"] = vol_signal / max(vol_baseline, 1)

    addrs_baseline = set()
    addrs_signal = set()
    for t in baseline:
        addrs_baseline.add(t["from"].lower())
        addrs_baseline.add(t["to"].lower())
    for t in signal:
        addrs_signal.add(t["from"].lower())
        addrs_signal.add(t["to"].lower())
    metrics["unique_addr_acceleration"] = len(addrs_signal) / max(len(addrs_baseline), 1)
    metrics["new_addresses_in_signal"] = len(addrs_signal - addrs_baseline)
    metrics["new_addr_pct"] = len(addrs_signal - addrs_baseline) / max(len(addrs_signal), 1)

    # === 2. COORDINATION / BURST METRICS ===
    # Burst ratio: max hourly rate / average hourly rate in signal period
    if signal:
        hourly_counts = defaultdict(int)
        for t in signal:
            hour = int(t["timeStamp"]) // 3600
            hourly_counts[hour] += 1
        if hourly_counts:
            counts = list(hourly_counts.values())
            metrics["burst_ratio"] = max(counts) / max(np.mean(counts), 0.01)
            metrics["burst_max_hourly"] = max(counts)
        else:
            metrics["burst_ratio"] = 0
            metrics["burst_max_hourly"] = 0

        # Synchronized actions: how many transfers happen within ±5 min of another
        timestamps = sorted(int(t["timeStamp"]) for t in signal)
        sync_count = 0
        for i in range(1, len(timestamps)):
            if timestamps[i] - timestamps[i-1] <= TEMPORAL_WINDOW:
                sync_count += 1
        metrics["sync_ratio"] = sync_count / max(len(timestamps) - 1, 1)
    else:
        metrics["burst_ratio"] = 0
        metrics["burst_max_hourly"] = 0
        metrics["sync_ratio"] = 0

    # Compare burst patterns: signal vs baseline
    if baseline:
        hourly_baseline = defaultdict(int)
        for t in baseline:
            hour = int(t["timeStamp"]) // 3600
            hourly_baseline[hour] += 1
        b_counts = list(hourly_baseline.values()) if hourly_baseline else [0]
        baseline_burst = max(b_counts) / max(np.mean(b_counts), 0.01)
        metrics["burst_acceleration"] = metrics["burst_ratio"] / max(baseline_burst, 0.01)
    else:
        metrics["burst_acceleration"] = metrics["burst_ratio"]

    # === 3. CONCENTRATION METRICS ===
    # Top-10 address share change between baseline and signal
    def top_k_share(transfer_list, k=10):
        vol_by_addr = defaultdict(int)
        total = 0
        for t in transfer_list:
            v = int(t.get("value", 0))
            vol_by_addr[t["from"].lower()] += v
            vol_by_addr[t["to"].lower()] += v
            total += v
        if not vol_by_addr or total == 0:
            return 0
        top = sorted(vol_by_addr.values(), reverse=True)[:k]
        return sum(top) / total

    top10_baseline = top_k_share(baseline, 10)
    top10_signal = top_k_share(signal, 10)
    metrics["top10_share_baseline"] = top10_baseline
    metrics["top10_share_signal"] = top10_signal
    metrics["concentration_delta"] = top10_signal - top10_baseline

    # === 4. CEX-DEX BRIDGE METRICS ===
    def count_flows(transfer_list):
        cex_in = 0    # tokens going TO CEX (deposit = selling pressure)
        cex_out = 0   # tokens coming FROM CEX (withdrawal = accumulation)
        dex_in = 0    # tokens going TO DEX (providing liquidity)
        dex_out = 0   # tokens coming FROM DEX (buying)
        bridge_addrs = set()  # addresses touching both CEX and DEX

        addr_touches_cex = set()
        addr_touches_dex = set()

        for t in transfer_list:
            sender = t["from"].lower()
            receiver = t["to"].lower()
            val = int(t.get("value", 0))

            s_type = labels.get(sender, {}).get("type", "unknown")
            r_type = labels.get(receiver, {}).get("type", "unknown")

            if r_type == "cex":
                cex_in += val
                addr_touches_cex.add(sender)
            if s_type == "cex":
                cex_out += val
                addr_touches_cex.add(receiver)
            if r_type == "dex":
                dex_in += val
                addr_touches_dex.add(sender)
            if s_type == "dex":
                dex_out += val
                addr_touches_dex.add(receiver)

        bridge_addrs = addr_touches_cex & addr_touches_dex
        return {
            "cex_in": cex_in, "cex_out": cex_out,
            "dex_in": dex_in, "dex_out": dex_out,
            "bridge_count": len(bridge_addrs),
        }

    baseline_flows = count_flows(baseline)
    signal_flows = count_flows(signal)

    # CEX withdrawal acceleration (accumulation signal)
    metrics["cex_withdrawal_accel"] = signal_flows["cex_out"] / max(baseline_flows["cex_out"], 1)
    metrics["cex_deposit_accel"] = signal_flows["cex_in"] / max(baseline_flows["cex_in"], 1)

    # Net CEX flow direction change
    baseline_net = baseline_flows["cex_in"] - baseline_flows["cex_out"]
    signal_net = signal_flows["cex_in"] - signal_flows["cex_out"]
    total_vol = max(vol_baseline + vol_signal, 1)
    metrics["baseline_net_cex_pct"] = baseline_net / total_vol * 100
    metrics["signal_net_cex_pct"] = signal_net / total_vol * 100
    metrics["net_cex_flow_delta_pct"] = (signal_net - baseline_net) / total_vol * 100

    # Bridge addresses (touching both CEX and DEX)
    metrics["bridge_addr_baseline"] = baseline_flows["bridge_count"]
    metrics["bridge_addr_signal"] = signal_flows["bridge_count"]
    metrics["bridge_addr_accel"] = signal_flows["bridge_count"] / max(baseline_flows["bridge_count"], 1)

    # DEX volume acceleration
    metrics["dex_buy_accel"] = signal_flows["dex_out"] / max(baseline_flows["dex_out"], 1)
    metrics["dex_sell_accel"] = signal_flows["dex_in"] / max(baseline_flows["dex_in"], 1)

    # === 5. WHALE METRICS ===
    def whale_analysis(transfer_list, total_volume):
        """Analyze whale behavior: who are the big movers?"""
        vol_by_addr = defaultdict(lambda: {"in": 0, "out": 0, "tx": 0})
        for t in transfer_list:
            sender = t["from"].lower()
            receiver = t["to"].lower()
            val = int(t.get("value", 0))
            vol_by_addr[sender]["out"] += val
            vol_by_addr[sender]["tx"] += 1
            vol_by_addr[receiver]["in"] += val
            vol_by_addr[receiver]["tx"] += 1

        whales = {}
        for addr, stats in vol_by_addr.items():
            total = stats["in"] + stats["out"]
            addr_type = labels.get(addr, {}).get("type", "unknown")
            if addr_type in ("cex", "dex", "bridge", "token"):
                continue
            if total_volume > 0 and total / total_volume > WHALE_VOLUME_PCT:
                whales[addr] = {
                    "net": stats["in"] - stats["out"],
                    "total": total,
                    "type": addr_type,
                    "is_mm": addr_type == "market_maker",
                }

        n_whales = len(whales)
        n_accumulating = sum(1 for w in whales.values() if w["net"] > 0)
        n_distributing = sum(1 for w in whales.values() if w["net"] < 0)
        n_mm_whales = sum(1 for w in whales.values() if w["is_mm"])

        return {
            "n_whales": n_whales,
            "n_accumulating": n_accumulating,
            "n_distributing": n_distributing,
            "n_mm_whales": n_mm_whales,
            "accumulation_ratio": n_accumulating / max(n_whales, 1),
        }

    whale_baseline = whale_analysis(baseline, vol_baseline)
    whale_signal = whale_analysis(signal, vol_signal)

    metrics["whale_count_baseline"] = whale_baseline["n_whales"]
    metrics["whale_count_signal"] = whale_signal["n_whales"]
    metrics["whale_accumulation_ratio_baseline"] = whale_baseline["accumulation_ratio"]
    metrics["whale_accumulation_ratio_signal"] = whale_signal["accumulation_ratio"]
    metrics["whale_accum_delta"] = (
        whale_signal["accumulation_ratio"] - whale_baseline["accumulation_ratio"]
    )

    # New whales in signal period
    metrics["new_whales"] = max(whale_signal["n_whales"] - whale_baseline["n_whales"], 0)

    # === 6. MANIPULATOR PATTERN FEATURES ===
    # Inspired by River/Folks known manipulator analysis

    # 6a. Puppet network: addresses that fund 3+ other addresses
    funding_map = defaultdict(set)  # sender -> set of receivers
    for t in signal:
        sender = t["from"].lower()
        receiver = t["to"].lower()
        # Skip CEX/DEX/token contracts
        s_type = labels.get(sender, {}).get("type", "unknown")
        r_type = labels.get(receiver, {}).get("type", "unknown")
        if s_type in ("cex", "dex", "bridge", "token"):
            continue
        if r_type in ("cex", "dex", "bridge", "token"):
            continue
        funding_map[sender].add(receiver)

    puppet_masters = {a: len(r) for a, r in funding_map.items() if len(r) >= 3}
    metrics["n_puppet_masters"] = len(puppet_masters)
    metrics["max_puppet_size"] = max(puppet_masters.values()) if puppet_masters else 0
    total_puppet_addrs = sum(puppet_masters.values())
    metrics["puppet_addr_pct"] = total_puppet_addrs / max(len(addrs_signal), 1)

    # 6b. Accum→Dump pattern: addresses that received in baseline, sent in signal
    accum_dump_count = 0
    for addr in addrs_baseline & addrs_signal:
        # Check if net was positive in baseline, negative in signal
        base_in = sum(int(t["value"]) for t in baseline if t["to"].lower() == addr)
        base_out = sum(int(t["value"]) for t in baseline if t["from"].lower() == addr)
        sig_in = sum(int(t["value"]) for t in signal if t["to"].lower() == addr)
        sig_out = sum(int(t["value"]) for t in signal if t["from"].lower() == addr)
        if base_in > base_out and sig_out > sig_in:
            accum_dump_count += 1
    metrics["accum_dump_addrs"] = accum_dump_count
    metrics["accum_dump_pct"] = accum_dump_count / max(len(addrs_baseline & addrs_signal), 1)

    # 6c. DEX-only activity: addresses with high tx count touching only DEX (no CEX)
    dex_only_volume = 0
    total_volume = vol_baseline + vol_signal
    for addr in addrs_signal:
        addr_type = labels.get(addr, {}).get("type", "unknown")
        if addr_type == "unknown":
            # Check if they only interact with DEX
            dex_touches = sum(1 for t in signal
                            if (t["from"].lower() == addr and labels.get(t["to"].lower(), {}).get("type") == "dex")
                            or (t["to"].lower() == addr and labels.get(t["from"].lower(), {}).get("type") == "dex"))
            cex_touches = sum(1 for t in signal
                            if (t["from"].lower() == addr and labels.get(t["to"].lower(), {}).get("type") == "cex")
                            or (t["to"].lower() == addr and labels.get(t["from"].lower(), {}).get("type") == "cex"))
            if dex_touches > 5 and cex_touches == 0:
                vol = sum(int(t["value"]) for t in signal
                         if t["from"].lower() == addr or t["to"].lower() == addr)
                dex_only_volume += vol

    metrics["dex_only_vol_pct"] = dex_only_volume / max(total_volume, 1) * 100

    # === 7. SMART MONEY COMPOSITE ===
    # Combine: CEX withdrawal spike + whale accumulation + low retail concentration
    metrics["smart_money_score"] = (
        min(metrics.get("cex_withdrawal_accel", 1), 10) * 0.3 +
        metrics.get("whale_accumulation_ratio_signal", 0.5) * 0.3 +
        (1 - metrics.get("top10_share_signal", 0.5)) * 0.2 +
        min(metrics.get("transfer_acceleration", 1), 5) * 0.2
    )

    return metrics


def run_analysis():
    """Run full anomaly detection across all tokens."""
    db = LabelDB()
    db.load_all()
    print(f"LabelDB: {db.stats()['total']} labels")

    # Scan ALL transfer files in data/transfers/ (includes ETH + BSC)
    transfer_files = sorted(TRANSFERS_DIR.glob("*.json"))
    coin_ids = [f.stem for f in transfer_files]
    print(f"Found {len(coin_ids)} transfer files")

    results = []
    for i, coin_id in enumerate(coin_ids):
        try:
            m = compute_token_anomalies(coin_id, db)
            if m:
                results.append(m)
        except Exception as e:
            print(f"  ERROR {coin_id}: {e}")

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}] {len(results)} processed...")

    print(f"\nTotal: {len(results)} tokens")

    winners = [r for r in results if r["category"] == "winner"]
    losers = [r for r in results if r["category"] == "loser"]
    print(f"  {len(winners)}W vs {len(losers)}L")

    # === STATISTICAL TESTS ===
    # Get all metric names (exclude non-numeric fields)
    skip_keys = {"coin_id", "category", "chain_id"}
    metric_names = sorted(set(k for r in results for k in r.keys()) - skip_keys)

    print(f"\n{'='*70}")
    print(f"MANN-WHITNEY U TESTS: {len(winners)}W vs {len(losers)}L")
    print(f"{'='*70}")

    test_results = {}
    significant = []

    for metric in metric_names:
        w_vals = [float(r.get(metric, 0)) for r in winners]
        l_vals = [float(r.get(metric, 0)) for r in losers]

        # Filter inf/nan
        w_vals = [v for v in w_vals if np.isfinite(v)]
        l_vals = [v for v in l_vals if np.isfinite(v)]

        if len(w_vals) < 10 or len(l_vals) < 10:
            continue

        try:
            stat, pval = mannwhitneyu(w_vals, l_vals, alternative="two-sided")
            n = len(w_vals) * len(l_vals)
            effect = 1 - (2 * stat) / n if n > 0 else 0

            w_med = np.median(w_vals)
            l_med = np.median(l_vals)
            ratio = w_med / l_med if l_med != 0 else float("inf")

            test_results[metric] = {
                "p_value": float(pval),
                "effect_size": float(effect),
                "winner_median": float(w_med),
                "loser_median": float(l_med),
                "ratio": float(ratio) if np.isfinite(ratio) else None,
            }

            sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
            if pval < 0.1:
                significant.append((metric, pval, effect, w_med, l_med, sig))

            print(f"  {metric:40s} W={w_med:12.4f}  L={l_med:12.4f}  p={pval:.4f} {sig}")
        except Exception as e:
            pass

    # Summary of significant findings
    print(f"\n{'='*70}")
    print(f"SIGNIFICANT SIGNALS (p < 0.1)")
    print(f"{'='*70}")
    for name, p, eff, w, l, sig in sorted(significant, key=lambda x: x[1]):
        direction = "↑ W" if w > l else "↓ W"
        ratio = w / l if l != 0 else "∞"
        ratio_str = f"{ratio:.2f}x" if isinstance(ratio, float) else ratio
        print(f"  {sig:3s} {name:40s} p={p:.4f}  W={w:.4f}  L={l:.4f}  {direction}  {ratio_str}")

    # Save
    output = {
        "n_tokens": len(results),
        "n_winners": len(winners),
        "n_losers": len(losers),
        "test_results": test_results,
        "significant_signals": [
            {"metric": n, "p": p, "effect": eff, "w_med": w, "l_med": l}
            for n, p, eff, w, l, s in sorted(significant, key=lambda x: x[1])
        ],
        "tokens": results,
    }

    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, set):
            return list(obj)
        return str(obj)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, default=convert)
    print(f"\nSaved to {OUTPUT_FILE}")

    # Generate report
    generate_report(results, test_results, significant)


def generate_report(results, test_results, significant):
    """Generate markdown report."""
    winners = [r for r in results if r["category"] == "winner"]
    losers = [r for r in results if r["category"] == "loser"]

    lines = [
        "# Market Maker & Anomaly Detection Report",
        "",
        f"**Sample**: {len(results)} tokens ({len(winners)}W vs {len(losers)}L)",
        f"**Method**: Mann-Whitney U (two-sided), T-7→T vs T-14→T-7 comparison",
        "",
        "## Significant Signals (p < 0.1)",
        "",
    ]

    if significant:
        lines.append("| # | Feature | W median | L median | p-value | Effect | Direction |")
        lines.append("|---|---------|---------|---------|---------|--------|-----------|")
        for i, (name, p, eff, w, l, sig) in enumerate(sorted(significant, key=lambda x: x[1]), 1):
            direction = "W higher" if w > l else "L higher"
            lines.append(f"| {i} | {name} | {w:.4f} | {l:.4f} | {p:.4f} {sig} | {eff:.3f} | {direction} |")
    else:
        lines.append("No significant signals found.")

    lines.extend([
        "",
        "## Metric Categories",
        "",
        "### Velocity (activity acceleration T-7→T vs T-14→T-7)",
        "- `transfer_acceleration`: tx count ratio",
        "- `volume_acceleration`: volume ratio",
        "- `unique_addr_acceleration`: unique addresses ratio",
        "",
        "### Coordination (burst & sync patterns)",
        "- `burst_ratio`: max hourly / avg hourly rate",
        "- `sync_ratio`: fraction of transfers within ±5 min of another",
        "- `burst_acceleration`: signal burst / baseline burst",
        "",
        "### Concentration (top-holder dynamics)",
        "- `top10_share_*`: top-10 address volume share",
        "- `concentration_delta`: change in top-10 share",
        "",
        "### CEX-DEX Bridge (liquidity movement)",
        "- `cex_withdrawal_accel`: CEX withdrawal volume acceleration",
        "- `bridge_addr_*`: addresses touching both CEX and DEX",
        "- `net_cex_flow_delta_pct`: change in net CEX flow direction",
        "",
        "### Whale Behavior",
        "- `whale_accumulation_ratio_*`: fraction of whales accumulating",
        "- `whale_accum_delta`: change in accumulation ratio",
        "- `new_whales`: new whale addresses in signal period",
        "",
        "### Composite",
        "- `smart_money_score`: weighted combination of CEX withdrawal + whale accum + activity",
    ])

    report = "\n".join(lines)
    REPORT_FILE.write_text(report)
    print(f"Report saved to {REPORT_FILE}")


if __name__ == "__main__":
    run_analysis()
