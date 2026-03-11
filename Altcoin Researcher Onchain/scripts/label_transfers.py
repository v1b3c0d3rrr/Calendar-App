"""
Phase 3: Label addresses in collected transfers and compute per-token metrics.

For each collected token (data/transfers/*.json):
1. Label all unique addresses using LabelDB
2. Apply heuristic labeling for unlabeled addresses
3. Compute metrics for T-14→T-7 (baseline) and T-7→T (signal window)
4. Output labeled summary per token

Metrics computed per period:
- CEX inflow/outflow (tokens moving to/from exchanges)
- DEX volume (tokens moving through DEX routers/pools)
- Whale activity (large transfers)
- Unique addresses active
- Transfer patterns (count, median size, max size)
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
OUTPUT_DIR = DATA_DIR / "labeled"

# Whale threshold: top 0.1% of transfer sizes or > $10k equivalent
# We'll use relative threshold: transfers > 1% of total volume in the period
WHALE_TRANSFER_PCT = 0.01


def is_likely_pool(address: str, transfers: list) -> bool:
    """Heuristic: address that receives AND sends roughly equal amounts = likely LP pool."""
    inflow = 0
    outflow = 0
    for t in transfers:
        val = int(t.get("value", 0))
        if t["to"].lower() == address:
            inflow += val
        if t["from"].lower() == address:
            outflow += val

    if inflow == 0 or outflow == 0:
        return False

    ratio = min(inflow, outflow) / max(inflow, outflow)
    # Pools typically have balanced in/out (ratio > 0.3)
    # and high activity
    return ratio > 0.3 and (inflow + outflow) > 0


def compute_period_metrics(
    transfers: list,
    labels: dict,
    token_decimals: int,
) -> dict:
    """Compute onchain metrics for a set of transfers."""
    if not transfers:
        return {
            "transfer_count": 0,
            "unique_addresses": 0,
            "total_volume": 0,
        }

    decimals_factor = 10 ** token_decimals

    # Track flows
    cex_inflow = 0       # tokens going TO CEX
    cex_outflow = 0      # tokens coming FROM CEX
    dex_volume = 0       # tokens through DEX
    bridge_volume = 0    # tokens through bridges
    total_volume = 0
    transfer_values = []
    unique_from = set()
    unique_to = set()

    # Per-entity tracking
    entity_inflow = defaultdict(int)   # entity -> tokens received
    entity_outflow = defaultdict(int)  # entity -> tokens sent

    for t in transfers:
        from_addr = t["from"].lower()
        to_addr = t["to"].lower()
        value = int(t.get("value", 0))
        value_tokens = value / decimals_factor

        total_volume += value
        transfer_values.append(value)
        unique_from.add(from_addr)
        unique_to.add(to_addr)

        from_label = labels.get(from_addr, {})
        to_label = labels.get(to_addr, {})

        from_type = from_label.get("type", "unknown")
        to_type = to_label.get("type", "unknown")

        # CEX flows
        if to_type == "cex":
            cex_inflow += value
            entity_inflow[to_label.get("entity", "unknown_cex")] += value
        if from_type == "cex":
            cex_outflow += value
            entity_outflow[from_label.get("entity", "unknown_cex")] += value

        # DEX flows
        if to_type == "dex" or from_type == "dex":
            dex_volume += value

        # Bridge flows
        if to_type == "bridge" or from_type == "bridge":
            bridge_volume += value

    all_addrs = unique_from | unique_to

    # Classify transfers by size
    if transfer_values:
        sorted_vals = sorted(transfer_values)
        median_val = sorted_vals[len(sorted_vals) // 2]
        p90_val = sorted_vals[int(len(sorted_vals) * 0.9)]
        max_val = sorted_vals[-1]

        # Whale transfers: > 1% of total volume
        whale_threshold = total_volume * WHALE_TRANSFER_PCT if total_volume > 0 else float('inf')
        whale_transfers = sum(1 for v in transfer_values if v >= whale_threshold)
        whale_volume = sum(v for v in transfer_values if v >= whale_threshold)
    else:
        median_val = p90_val = max_val = 0
        whale_transfers = whale_volume = 0

    # Label coverage
    labeled = sum(1 for a in all_addrs if a in labels)
    labeled_pct = labeled / len(all_addrs) * 100 if all_addrs else 0

    return {
        "transfer_count": len(transfers),
        "unique_addresses": len(all_addrs),
        "unique_senders": len(unique_from),
        "unique_receivers": len(unique_to),
        "total_volume_raw": total_volume,
        "total_volume": round(total_volume / decimals_factor, 4),
        "median_transfer_raw": median_val,
        "p90_transfer_raw": p90_val,
        "max_transfer_raw": max_val,
        # CEX metrics
        "cex_inflow_raw": cex_inflow,
        "cex_outflow_raw": cex_outflow,
        "cex_inflow_pct": round(cex_inflow / total_volume * 100, 2) if total_volume > 0 else 0,
        "cex_outflow_pct": round(cex_outflow / total_volume * 100, 2) if total_volume > 0 else 0,
        "cex_net_flow_raw": cex_inflow - cex_outflow,  # positive = selling pressure
        "cex_net_flow_pct": round((cex_inflow - cex_outflow) / total_volume * 100, 2) if total_volume > 0 else 0,
        # DEX metrics
        "dex_volume_raw": dex_volume,
        "dex_volume_pct": round(dex_volume / total_volume * 100, 2) if total_volume > 0 else 0,
        # Bridge
        "bridge_volume_pct": round(bridge_volume / total_volume * 100, 2) if total_volume > 0 else 0,
        # Whale metrics
        "whale_transfers": whale_transfers,
        "whale_volume_pct": round(whale_volume / total_volume * 100, 2) if total_volume > 0 else 0,
        # Label coverage
        "labeled_addresses": labeled,
        "labeled_pct": round(labeled_pct, 1),
        # Top entities
        "top_cex_inflow": dict(sorted(
            {k: round(v / decimals_factor, 2) for k, v in entity_inflow.items()}.items(),
            key=lambda x: -x[1]
        )[:5]),
        "top_cex_outflow": dict(sorted(
            {k: round(v / decimals_factor, 2) for k, v in entity_outflow.items()}.items(),
            key=lambda x: -x[1]
        )[:5]),
    }


def process_token(filepath: Path, db: LabelDB) -> Optional[dict]:
    """Process a single token's transfer file."""
    with open(filepath) as f:
        data = json.load(f)

    coin_id = data["coin_id"]
    chain_id = data["chain_id"]
    transfers = data.get("transfers", [])

    if not transfers:
        return None

    # Get token decimals
    token_decimals = int(transfers[0].get("tokenDecimal", 18))

    # Label all unique addresses
    all_addrs = set()
    for t in transfers:
        all_addrs.add(t["from"].lower())
        all_addrs.add(t["to"].lower())

    labels = {}
    for addr in all_addrs:
        label = db.lookup(addr, chain_id)
        if label:
            labels[addr] = label

    # --- Heuristic labeling for unlabeled addresses ---
    # Build per-address stats from ALL transfers
    addr_stats = defaultdict(lambda: {
        "in_count": 0, "out_count": 0,
        "in_volume": 0, "out_volume": 0,
        "unique_counterparties": set(),
    })
    for t in transfers:
        from_addr = t["from"].lower()
        to_addr = t["to"].lower()
        value = int(t.get("value", 0))
        addr_stats[from_addr]["out_count"] += 1
        addr_stats[from_addr]["out_volume"] += value
        addr_stats[from_addr]["unique_counterparties"].add(to_addr)
        addr_stats[to_addr]["in_count"] += 1
        addr_stats[to_addr]["in_volume"] += value
        addr_stats[to_addr]["unique_counterparties"].add(from_addr)

    total_volume_all = sum(int(t.get("value", 0)) for t in transfers)

    for addr in all_addrs:
        if addr in labels or addr == "0x0000000000000000000000000000000000000000":
            continue
        s = addr_stats[addr]
        total_tx = s["in_count"] + s["out_count"]
        total_vol = s["in_volume"] + s["out_volume"]
        n_counterparties = len(s["unique_counterparties"])

        # Heuristic 1: DEX Pool — balanced in/out, many counterparties
        if s["in_volume"] > 0 and s["out_volume"] > 0:
            ratio = min(s["in_volume"], s["out_volume"]) / max(s["in_volume"], s["out_volume"])
            if ratio > 0.3 and n_counterparties >= 5 and total_tx >= 10:
                labels[addr] = {"type": "dex_pool", "entity": "unknown_pool", "name": "Heuristic: LP Pool", "source": "heuristic"}
                continue

        # Heuristic 2: CEX-like — very high tx count, many unique counterparties
        if total_tx >= 50 and n_counterparties >= 20:
            # High activity + many counterparties = likely CEX deposit/withdrawal
            labels[addr] = {"type": "cex", "entity": "unknown_cex", "name": "Heuristic: Likely CEX", "source": "heuristic"}
            continue

        # Heuristic 3: Whale — holds/moves > 5% of total volume
        if total_vol > total_volume_all * 0.05 and total_tx < 20:
            labels[addr] = {"type": "whale", "entity": "unknown_whale", "name": "Heuristic: Whale", "source": "heuristic"}
            continue

        # Heuristic 4: Bot/MEV — very high frequency, small spread
        if total_tx >= 30 and n_counterparties <= 3:
            labels[addr] = {"type": "mev_bot", "entity": "unknown_bot", "name": "Heuristic: Bot/MEV", "source": "heuristic"}
            continue

    # Split transfers by period
    t7_block = data["blocks"]["t_minus_7"]
    baseline_transfers = [t for t in transfers if int(t["blockNumber"]) < t7_block]
    signal_transfers = [t for t in transfers if int(t["blockNumber"]) >= t7_block]

    baseline_metrics = compute_period_metrics(baseline_transfers, labels, token_decimals)
    signal_metrics = compute_period_metrics(signal_transfers, labels, token_decimals)

    # Compute deltas (signal vs baseline)
    deltas = {}
    for key in ["transfer_count", "unique_addresses", "cex_inflow_pct", "cex_outflow_pct",
                 "cex_net_flow_pct", "dex_volume_pct", "whale_volume_pct"]:
        b_val = baseline_metrics.get(key, 0)
        s_val = signal_metrics.get(key, 0)
        if b_val != 0:
            deltas[f"{key}_delta_pct"] = round((s_val - b_val) / abs(b_val) * 100, 1)
        else:
            deltas[f"{key}_delta_pct"] = None

    return {
        "coin_id": coin_id,
        "symbol": data["symbol"],
        "name": data["name"],
        "category": data["category"],
        "multiplier": data.get("multiplier"),
        "start_mc": data.get("start_mc"),
        "chain_id": chain_id,
        "chain_name": data["chain_name"],
        "event_date": data["event_date"],
        "total_transfers": len(transfers),
        "token_decimals": token_decimals,
        "labeled_addresses": len(labels),
        "total_unique_addresses": len(all_addrs),
        "label_coverage_pct": round(len(labels) / len(all_addrs) * 100, 1) if all_addrs else 0,
        "baseline_period": {
            "description": "T-14 to T-7 (normal activity)",
            **baseline_metrics,
        },
        "signal_period": {
            "description": "T-7 to T (pre-event)",
            **signal_metrics,
        },
        "deltas": deltas,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading label database...", flush=True)
    db = LabelDB()
    db.load_all()
    stats = db.stats()
    print(f"Labels loaded: {stats['total']} entries", flush=True)

    # Find all transfer files
    transfer_files = sorted(TRANSFERS_DIR.glob("*.json"))
    print(f"\nTransfer files found: {len(transfer_files)}", flush=True)

    results = []
    errors = []

    for i, fpath in enumerate(transfer_files):
        coin_id = fpath.stem
        print(f"[{i+1}/{len(transfer_files)}] {coin_id}...", end=" ", flush=True)

        try:
            result = process_token(fpath, db)
            if result:
                results.append(result)
                print(f"OK (transfers={result['total_transfers']}, "
                      f"labeled={result['label_coverage_pct']}%)", flush=True)
            else:
                print("SKIP (no transfers)", flush=True)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            errors.append({"coin_id": coin_id, "error": str(e)})

    # Save all results
    output = {
        "total_tokens": len(results),
        "errors": len(errors),
        "results": results,
    }
    outfile = OUTPUT_DIR / "labeled_metrics.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(results)} tokens labeled")
    print(f"Errors: {len(errors)}")

    # Summary stats
    if results:
        avg_coverage = sum(r["label_coverage_pct"] for r in results) / len(results)
        print(f"Average label coverage: {avg_coverage:.1f}%")

        # Winners vs losers comparison
        winners = [r for r in results if r["category"] == "winner"]
        losers = [r for r in results if r["category"] == "loser"]

        if winners and losers:
            print(f"\nWinners ({len(winners)}) vs Losers ({len(losers)}) — Signal Period (T-7 to T):")
            for metric in ["cex_inflow_pct", "cex_outflow_pct", "cex_net_flow_pct",
                          "dex_volume_pct", "whale_volume_pct", "transfer_count", "unique_addresses"]:
                w_vals = [r["signal_period"][metric] for r in winners if r["signal_period"].get(metric) is not None]
                l_vals = [r["signal_period"][metric] for r in losers if r["signal_period"].get(metric) is not None]
                if w_vals and l_vals:
                    w_mean = sum(w_vals) / len(w_vals)
                    l_mean = sum(l_vals) / len(l_vals)
                    print(f"  {metric}: W={w_mean:.2f} vs L={l_mean:.2f}")

            print(f"\nDeltas (signal vs baseline):")
            for metric in ["transfer_count_delta_pct", "cex_inflow_pct_delta_pct",
                          "cex_net_flow_pct_delta_pct", "whale_volume_pct_delta_pct"]:
                w_vals = [r["deltas"][metric] for r in winners if r["deltas"].get(metric) is not None]
                l_vals = [r["deltas"][metric] for r in losers if r["deltas"].get(metric) is not None]
                if w_vals and l_vals:
                    w_mean = sum(w_vals) / len(w_vals)
                    l_mean = sum(l_vals) / len(l_vals)
                    print(f"  {metric}: W={w_mean:.1f}% vs L={l_mean:.1f}%")

    print(f"\nSaved to: {outfile}")


if __name__ == "__main__":
    main()
