"""
Analyze CEX inflows/outflows with CEX-to-CEX rotation filtering.

Approach:
1. Load transfers, label all addresses
2. Identify CEX-to-CEX rotation chains:
   - Token leaves CEX_A → intermediate hops → arrives CEX_B within 7 days
   - These are noise (arbitrage, rebalancing), not real supply/demand signal
3. Remove rotation transfers, keep "real" CEX flows:
   - Real deposit: non-CEX address → CEX (selling pressure)
   - Real withdrawal: CEX → non-CEX address (accumulation)
4. Compute daily metrics for T-14→T-7 (baseline) and T-7→T (signal)
5. Statistical tests: winners vs losers

Key metrics per period:
- real_cex_inflow: tokens deposited to CEX by non-CEX addresses
- real_cex_outflow: tokens withdrawn from CEX to non-CEX addresses
- real_net_flow: inflow - outflow (positive = selling pressure)
- flow_count: number of real CEX transactions
- avg_flow_size: average transfer size
- whale_cex_flows: large deposits/withdrawals (>1% of period volume)
- unique_depositors / unique_withdrawers
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from label_db import LabelDB

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSFERS_DIR = DATA_DIR / "transfers"
REPORT_FILE = DATA_DIR / "cex_flow_report.md"

# CEX-to-CEX rotation window: if token goes CEX→...→CEX within this many seconds, it's rotation
ROTATION_WINDOW = 7 * 86400  # 7 days


def build_address_labels(transfers: list, db: LabelDB, chain_id: int) -> dict:
    """Label all addresses + heuristic for unlabeled."""
    all_addrs = set()
    for t in transfers:
        all_addrs.add(t["from"].lower())
        all_addrs.add(t["to"].lower())

    labels = {}
    for addr in all_addrs:
        label = db.lookup(addr, chain_id)
        if label:
            labels[addr] = label

    # Heuristic: high-activity addresses likely CEX
    addr_stats = defaultdict(lambda: {"in": 0, "out": 0, "counterparties": set()})
    for t in transfers:
        f = t["from"].lower()
        to = t["to"].lower()
        addr_stats[f]["out"] += 1
        addr_stats[f]["counterparties"].add(to)
        addr_stats[to]["in"] += 1
        addr_stats[to]["counterparties"].add(f)

    for addr in all_addrs:
        if addr in labels:
            continue
        s = addr_stats[addr]
        total_tx = s["in"] + s["out"]
        n_cp = len(s["counterparties"])
        if total_tx >= 50 and n_cp >= 20:
            labels[addr] = {"type": "cex", "entity": "unknown_cex", "source": "heuristic"}

    return labels


def find_rotation_transfers(transfers: list, labels: dict) -> set:
    """
    Find CEX-to-CEX rotation chains.

    Algorithm:
    - Track every CEX withdrawal (CEX → addr)
    - For each such withdrawal, follow the tokens forward:
      if any of the receiving addresses eventually deposit to a CEX
      within ROTATION_WINDOW, mark the entire chain as rotation.

    Simplified approach:
    - Build a timeline of each address's interactions
    - If address receives from CEX and sends to CEX within window → rotation intermediary
    - Mark both the receive-from-CEX and send-to-CEX transfers as rotation
    """
    rotation_hashes = set()

    # Index transfers by recipient
    addr_receives = defaultdict(list)  # addr -> [(timestamp, tx_hash, from_addr, value)]
    addr_sends = defaultdict(list)     # addr -> [(timestamp, tx_hash, to_addr, value)]

    for t in transfers:
        ts = int(t.get("timeStamp", 0))
        tx_hash = t.get("hash", "")
        from_addr = t["from"].lower()
        to_addr = t["to"].lower()
        value = int(t.get("value", 0))

        addr_receives[to_addr].append((ts, tx_hash, from_addr, value))
        addr_sends[from_addr].append((ts, tx_hash, to_addr, value))

    # For each non-CEX address: check if it's a rotation intermediary
    # Pattern: receives from CEX → sends to CEX within ROTATION_WINDOW
    all_addrs = set(addr_receives.keys()) | set(addr_sends.keys())

    for addr in all_addrs:
        addr_label = labels.get(addr, {})
        if addr_label.get("type") == "cex":
            continue  # Skip CEX addresses themselves

        # Find receives from CEX
        cex_receives = []
        for ts, tx_hash, from_addr, value in addr_receives.get(addr, []):
            from_label = labels.get(from_addr, {})
            if from_label.get("type") == "cex":
                cex_receives.append((ts, tx_hash, value))

        if not cex_receives:
            continue

        # Find sends to CEX
        cex_sends = []
        for ts, tx_hash, to_addr, value in addr_sends.get(addr, []):
            to_label = labels.get(to_addr, {})
            if to_label.get("type") == "cex":
                cex_sends.append((ts, tx_hash, value))

        if not cex_sends:
            continue

        # Match: receive from CEX_A, then send to CEX_B within window
        for recv_ts, recv_hash, recv_val in cex_receives:
            for send_ts, send_hash, send_val in cex_sends:
                if 0 <= (send_ts - recv_ts) <= ROTATION_WINDOW:
                    # Value match tolerance: within 20% (fees, partial transfers)
                    if recv_val > 0 and send_val > 0:
                        ratio = min(recv_val, send_val) / max(recv_val, send_val)
                        if ratio > 0.5:  # Loosely matched
                            rotation_hashes.add(recv_hash)
                            rotation_hashes.add(send_hash)

    return rotation_hashes


def compute_cex_metrics(
    transfers: list,
    labels: dict,
    rotation_hashes: set,
    token_decimals: int,
) -> dict:
    """Compute clean CEX flow metrics after removing rotations."""
    decimals_factor = 10 ** token_decimals

    # Separate into real deposits, real withdrawals, rotations
    real_deposits = []     # non-CEX → CEX (selling)
    real_withdrawals = []  # CEX → non-CEX (accumulation)
    rotation_count = 0
    rotation_volume = 0

    for t in transfers:
        tx_hash = t.get("hash", "")
        from_addr = t["from"].lower()
        to_addr = t["to"].lower()
        value = int(t.get("value", 0))

        from_label = labels.get(from_addr, {})
        to_label = labels.get(to_addr, {})
        from_type = from_label.get("type", "unknown")
        to_type = to_label.get("type", "unknown")

        # Skip rotation transfers
        if tx_hash in rotation_hashes:
            rotation_count += 1
            rotation_volume += value
            continue

        # Real deposit: non-CEX → CEX
        if to_type == "cex" and from_type != "cex":
            real_deposits.append({
                "from": from_addr,
                "to": to_addr,
                "to_entity": to_label.get("entity", "unknown_cex"),
                "from_type": from_type,
                "from_entity": from_label.get("entity", "unknown"),
                "value": value,
                "timestamp": int(t.get("timeStamp", 0)),
            })

        # Real withdrawal: CEX → non-CEX
        if from_type == "cex" and to_type != "cex":
            real_withdrawals.append({
                "from": from_addr,
                "to": to_addr,
                "from_entity": from_label.get("entity", "unknown_cex"),
                "to_type": to_type,
                "to_entity": to_label.get("entity", "unknown"),
                "value": value,
                "timestamp": int(t.get("timeStamp", 0)),
            })

    # Aggregate metrics
    total_volume = sum(int(t.get("value", 0)) for t in transfers)
    dep_volume = sum(d["value"] for d in real_deposits)
    wd_volume = sum(w["value"] for w in real_withdrawals)
    net_flow = dep_volume - wd_volume  # positive = selling pressure

    # Whale threshold: deposits/withdrawals > 1% of total period volume
    whale_threshold = total_volume * 0.01 if total_volume > 0 else float("inf")
    whale_deposits = [d for d in real_deposits if d["value"] >= whale_threshold]
    whale_withdrawals = [w for w in real_withdrawals if w["value"] >= whale_threshold]

    # Unique participants
    depositors = set(d["from"] for d in real_deposits)
    withdrawers = set(w["to"] for w in real_withdrawals)

    # Depositor types breakdown
    depositor_types = defaultdict(int)
    for d in real_deposits:
        depositor_types[d["from_type"]] += d["value"]

    withdrawer_types = defaultdict(int)
    for w in real_withdrawals:
        withdrawer_types[w["to_type"]] += w["value"]

    # CEX entity breakdown
    cex_deposit_entities = defaultdict(int)
    for d in real_deposits:
        cex_deposit_entities[d["to_entity"]] += d["value"]

    cex_withdraw_entities = defaultdict(int)
    for w in real_withdrawals:
        cex_withdraw_entities[w["from_entity"]] += w["value"]

    return {
        "total_transfers": len(transfers),
        "total_volume": total_volume,
        "total_volume_tokens": round(total_volume / decimals_factor, 2),
        # Rotation
        "rotation_count": rotation_count,
        "rotation_volume": rotation_volume,
        "rotation_pct": round(rotation_volume / total_volume * 100, 2) if total_volume else 0,
        # Real deposits (selling pressure)
        "deposit_count": len(real_deposits),
        "deposit_volume": dep_volume,
        "deposit_volume_tokens": round(dep_volume / decimals_factor, 2),
        "deposit_pct": round(dep_volume / total_volume * 100, 2) if total_volume else 0,
        "deposit_avg_size": round(dep_volume / len(real_deposits) / decimals_factor, 2) if real_deposits else 0,
        "unique_depositors": len(depositors),
        # Real withdrawals (accumulation)
        "withdrawal_count": len(real_withdrawals),
        "withdrawal_volume": wd_volume,
        "withdrawal_volume_tokens": round(wd_volume / decimals_factor, 2),
        "withdrawal_pct": round(wd_volume / total_volume * 100, 2) if total_volume else 0,
        "withdrawal_avg_size": round(wd_volume / len(real_withdrawals) / decimals_factor, 2) if real_withdrawals else 0,
        "unique_withdrawers": len(withdrawers),
        # Net flow (positive = selling pressure)
        "net_flow": net_flow,
        "net_flow_tokens": round(net_flow / decimals_factor, 2),
        "net_flow_pct": round(net_flow / total_volume * 100, 2) if total_volume else 0,
        # Whales
        "whale_deposit_count": len(whale_deposits),
        "whale_deposit_volume_pct": round(sum(d["value"] for d in whale_deposits) / total_volume * 100, 2) if total_volume else 0,
        "whale_withdrawal_count": len(whale_withdrawals),
        "whale_withdrawal_volume_pct": round(sum(w["value"] for w in whale_withdrawals) / total_volume * 100, 2) if total_volume else 0,
        # Participant type breakdown (% of deposit volume)
        "depositor_types": {k: round(v / dep_volume * 100, 1) if dep_volume else 0
                           for k, v in sorted(depositor_types.items(), key=lambda x: -x[1])[:5]},
        "withdrawer_types": {k: round(v / wd_volume * 100, 1) if wd_volume else 0
                            for k, v in sorted(withdrawer_types.items(), key=lambda x: -x[1])[:5]},
        # Top CEX entities
        "top_deposit_cex": {k: round(v / decimals_factor, 2)
                           for k, v in sorted(cex_deposit_entities.items(), key=lambda x: -x[1])[:5]},
        "top_withdraw_cex": {k: round(v / decimals_factor, 2)
                            for k, v in sorted(cex_withdraw_entities.items(), key=lambda x: -x[1])[:5]},
    }


def process_token(filepath: Path, db: LabelDB, max_transfers: int = 200000) -> Optional[dict]:
    """Process one token: filter rotations, compute CEX metrics per period."""
    with open(filepath) as f:
        data = json.load(f)

    transfers = data.get("transfers", [])
    if not transfers or len(transfers) < 5:
        return None

    # For very large files, sample evenly to keep analysis tractable
    if len(transfers) > max_transfers:
        step = len(transfers) / max_transfers
        transfers = [transfers[int(i * step)] for i in range(max_transfers)]

    chain_id = data["chain_id"]
    token_decimals = int(transfers[0].get("tokenDecimal", 18))
    t7_block = data["blocks"]["t_minus_7"]

    # Label addresses
    labels = build_address_labels(transfers, db, chain_id)

    # Find rotation transfers (across FULL 14d window)
    rotation_hashes = find_rotation_transfers(transfers, labels)

    # Split by period
    baseline = [t for t in transfers if int(t["blockNumber"]) < t7_block]
    signal = [t for t in transfers if int(t["blockNumber"]) >= t7_block]

    baseline_metrics = compute_cex_metrics(baseline, labels, rotation_hashes, token_decimals)
    signal_metrics = compute_cex_metrics(signal, labels, rotation_hashes, token_decimals)

    # Compute deltas
    def delta(metric):
        b = baseline_metrics.get(metric, 0)
        s = signal_metrics.get(metric, 0)
        if b != 0:
            return round((s - b) / abs(b) * 100, 1)
        return None

    return {
        "coin_id": data["coin_id"],
        "symbol": data["symbol"],
        "category": data["category"],
        "multiplier": data.get("multiplier"),
        "start_mc": data.get("start_mc"),
        "chain_id": chain_id,
        "event_date": data["event_date"],
        "total_transfers": len(transfers),
        "rotation_filtered": len(rotation_hashes),
        "baseline": baseline_metrics,
        "signal": signal_metrics,
        "deltas": {
            "deposit_count": delta("deposit_count"),
            "deposit_pct": delta("deposit_pct"),
            "withdrawal_count": delta("withdrawal_count"),
            "withdrawal_pct": delta("withdrawal_pct"),
            "net_flow_pct": delta("net_flow_pct"),
            "unique_depositors": delta("unique_depositors"),
            "unique_withdrawers": delta("unique_withdrawers"),
            "whale_deposit_count": delta("whale_deposit_count"),
        },
    }


def mann_whitney_u(g1: list, g2: list) -> dict:
    """Mann-Whitney U test."""
    import math
    if not g1 or not g2:
        return {"p_value": None, "effect_size": None}
    n1, n2 = len(g1), len(g2)
    combined = [(v, 0) for v in g1] + [(v, 1) for v in g2]
    combined.sort(key=lambda x: x[0])
    ranks = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j
    r1 = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    u_stat = min(u1, u2)
    mu = n1 * n2 / 2
    sigma = (n1 * n2 * (n1 + n2 + 1) / 12) ** 0.5
    if sigma == 0:
        return {"p_value": 1.0, "effect_size": 0.0}
    z = abs(u_stat - mu) / sigma
    p_value = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    effect_size = 1 - (2 * u_stat) / (n1 * n2)
    return {"p_value": round(p_value, 6), "effect_size": round(effect_size, 4), "z": round(z, 3)}


def main():
    print("Loading label database...", flush=True)
    db = LabelDB()
    db.load_all()
    print(f"Labels: {db.stats()['total']} (CEX: {db.stats()['by_type'].get('cex', 0)})", flush=True)

    transfer_files = sorted(TRANSFERS_DIR.glob("*.json"))
    print(f"Transfer files: {len(transfer_files)}", flush=True)

    results = []
    for i, fpath in enumerate(transfer_files):
        print(f"[{i+1}/{len(transfer_files)}] {fpath.stem}...", end=" ", flush=True)
        try:
            r = process_token(fpath, db)
            if r:
                results.append(r)
                rot = r["rotation_filtered"]
                dep_s = r["signal"]["deposit_count"]
                wd_s = r["signal"]["withdrawal_count"]
                print(f"OK (rot={rot}, dep={dep_s}, wd={wd_s})", flush=True)
            else:
                print("SKIP", flush=True)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)

    # Split winners/losers
    winners = [r for r in results if r["category"] == "winner"]
    losers = [r for r in results if r["category"] == "loser"]

    print(f"\n{'='*80}")
    print(f"RESULTS: {len(results)} tokens ({len(winners)}W / {len(losers)}L)")
    print(f"{'='*80}")

    # Rotation stats
    rot_counts = [r["rotation_filtered"] for r in results]
    print(f"\nRotation filtering:")
    print(f"  Total rotation transfers removed: {sum(rot_counts)}")
    print(f"  Avg per token: {sum(rot_counts)/len(rot_counts):.1f}")
    print(f"  Tokens with rotations: {sum(1 for r in rot_counts if r > 0)}")

    # Define features to test
    features = {
        # Signal period absolute
        "sp_deposit_pct": lambda r: r["signal"]["deposit_pct"],
        "sp_withdrawal_pct": lambda r: r["signal"]["withdrawal_pct"],
        "sp_net_flow_pct": lambda r: r["signal"]["net_flow_pct"],
        "sp_deposit_count": lambda r: r["signal"]["deposit_count"],
        "sp_withdrawal_count": lambda r: r["signal"]["withdrawal_count"],
        "sp_unique_depositors": lambda r: r["signal"]["unique_depositors"],
        "sp_unique_withdrawers": lambda r: r["signal"]["unique_withdrawers"],
        "sp_deposit_avg_size": lambda r: r["signal"]["deposit_avg_size"],
        "sp_withdrawal_avg_size": lambda r: r["signal"]["withdrawal_avg_size"],
        "sp_whale_deposit_pct": lambda r: r["signal"]["whale_deposit_volume_pct"],
        "sp_whale_withdrawal_pct": lambda r: r["signal"]["whale_withdrawal_volume_pct"],
        "sp_rotation_pct": lambda r: r["signal"]["rotation_pct"],
        # Deltas (signal vs baseline)
        "delta_deposit_count": lambda r: r["deltas"]["deposit_count"],
        "delta_deposit_pct": lambda r: r["deltas"]["deposit_pct"],
        "delta_withdrawal_count": lambda r: r["deltas"]["withdrawal_count"],
        "delta_withdrawal_pct": lambda r: r["deltas"]["withdrawal_pct"],
        "delta_net_flow_pct": lambda r: r["deltas"]["net_flow_pct"],
        "delta_unique_depositors": lambda r: r["deltas"]["unique_depositors"],
        "delta_unique_withdrawers": lambda r: r["deltas"]["unique_withdrawers"],
        # Derived
        "sp_deposit_withdrawal_ratio": lambda r: (
            r["signal"]["deposit_volume"] / r["signal"]["withdrawal_volume"]
            if r["signal"]["withdrawal_volume"] > 0 else None
        ),
        "deposit_intensity": lambda r: (
            r["signal"]["deposit_count"] / r["baseline"]["deposit_count"]
            if r["baseline"]["deposit_count"] > 0 else None
        ),
        "withdrawal_intensity": lambda r: (
            r["signal"]["withdrawal_count"] / r["baseline"]["withdrawal_count"]
            if r["baseline"]["withdrawal_count"] > 0 else None
        ),
    }

    print(f"\n{'Feature':<35} {'W_mean':>10} {'L_mean':>10} {'W_med':>10} {'L_med':>10} {'p':>8} {'eff':>7}")
    print("-" * 95)

    test_results = []
    for fname, extractor in features.items():
        w_vals = [v for r in winners if (v := extractor(r)) is not None]
        l_vals = [v for r in losers if (v := extractor(r)) is not None]
        if len(w_vals) < 5 or len(l_vals) < 5:
            continue
        w_mean = sum(w_vals) / len(w_vals)
        l_mean = sum(l_vals) / len(l_vals)
        w_med = sorted(w_vals)[len(w_vals) // 2]
        l_med = sorted(l_vals)[len(l_vals) // 2]
        mwu = mann_whitney_u(w_vals, l_vals)
        sig = "***" if mwu["p_value"] and mwu["p_value"] < 0.001 else \
              "**" if mwu["p_value"] and mwu["p_value"] < 0.01 else \
              "*" if mwu["p_value"] and mwu["p_value"] < 0.05 else \
              "~" if mwu["p_value"] and mwu["p_value"] < 0.1 else ""
        test_results.append({
            "feature": fname, "w_mean": w_mean, "l_mean": l_mean,
            "w_median": w_med, "l_median": l_med,
            "w_n": len(w_vals), "l_n": len(l_vals), **mwu, "sig": sig,
        })
        p_str = f"{mwu['p_value']:.4f}" if mwu["p_value"] is not None else "N/A"
        e_str = f"{mwu['effect_size']:.3f}" if mwu["effect_size"] is not None else "N/A"
        print(f"{fname:<35} {w_mean:>10.2f} {l_mean:>10.2f} {w_med:>10.2f} {l_med:>10.2f} {p_str:>7}{sig} {e_str:>7}")

    # Sort by p-value
    test_results.sort(key=lambda x: x.get("p_value", 1) or 1)

    # Report
    print(f"\n{'='*80}")
    print("TOP FEATURES (sorted by p-value):")
    print(f"{'='*80}")
    for r in test_results[:10]:
        print(f"  {r['feature']}: p={r['p_value']:.4f}{r['sig']} effect={r['effect_size']:.3f} "
              f"(W={r['w_mean']:.2f} vs L={r['l_mean']:.2f})")

    # Save results
    output = {
        "total_tokens": len(results),
        "winners": len(winners),
        "losers": len(losers),
        "test_results": test_results,
        "token_results": results,
    }
    outfile = DATA_DIR / "labeled" / "cex_flow_analysis.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to: {outfile}")

    # Generate report
    report_lines = [
        "# CEX Flow Analysis (Rotation-Filtered)",
        "",
        f"**Dataset**: {len(results)} tokens ({len(winners)}W / {len(losers)}L)",
        f"**Rotation filtered**: {sum(rot_counts)} transfers removed",
        "",
        "## Feature Ranking (by p-value)",
        "",
        "| Feature | W mean | L mean | W median | L median | p-value | Effect | Sig |",
        "|---------|--------|--------|----------|----------|---------|--------|-----|",
    ]
    for r in test_results:
        p_str = f"{r['p_value']:.4f}" if r["p_value"] is not None else "N/A"
        report_lines.append(
            f"| {r['feature']} | {r['w_mean']:.2f} | {r['l_mean']:.2f} | "
            f"{r['w_median']:.2f} | {r['l_median']:.2f} | {p_str} | {r['effect_size']:.3f} | {r['sig']} |"
        )
    report_lines.extend(["", "## Key Findings", ""])
    strong = [r for r in test_results if r.get("p_value") and r["p_value"] < 0.1]
    if strong:
        for r in strong:
            direction = "higher" if r["w_mean"] > r["l_mean"] else "lower"
            report_lines.append(f"- **{r['feature']}**: Winners {direction} ({r['w_mean']:.2f} vs {r['l_mean']:.2f}, p={r['p_value']:.4f})")
    else:
        report_lines.append("- No features reached p < 0.1")

    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(report_lines))
    print(f"Report: {REPORT_FILE}")


if __name__ == "__main__":
    main()
