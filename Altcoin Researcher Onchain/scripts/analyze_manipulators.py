"""
Deep analysis of tokens with KNOWN manipulators.

Goal: Identify manipulator wallets and their behavioral patterns.
These patterns can then be used as features for the broader W vs L classification.

Tokens:
- River (RIVER): ETH, 0xdA7AD9dea9397cffdDAE2F8a052B82f1484252B3
  Peak: Jan 26, 2026 ($87.79), Low: Sept 22, 2025 ($1.14)
- Folks (FOLKS): ETH, 0xff7f8f301f7a706e3cfd3d2275f5dc0b9ee8009b
  Peak: Dec 14, 2025 ($50), Low: Nov 6, 2025 ($1.00)

Approach:
1. Collect ALL transfers for these tokens (genesis to peak)
2. Build complete address behavior profiles
3. Identify suspicious patterns:
   - Addresses with outsized volume (>1% total)
   - Coordinated timing (multiple addresses acting in sync)
   - CEX-DEX bridging (moving tokens between exchanges and DEX)
   - Accumulation before pump, distribution at peak
   - Cluster analysis: addresses funded from the same source
4. Rank addresses by "manipulation score"
5. Profile the top suspects: what patterns do they exhibit?
"""

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from label_db import LabelDB
from explorer_api import get_token_transfers, get_block_by_timestamp

DATA_DIR = Path(__file__).parent.parent / "data"
MANIPULATOR_DIR = DATA_DIR / "manipulator_analysis"
MANIPULATOR_DIR.mkdir(exist_ok=True)

# Tokens to analyze
TARGETS = [
    # PUMP phases (accumulation before peak)
    {
        "name": "River (PUMP)",
        "symbol": "RIVER",
        "contract": "0xdA7AD9dea9397cffdDAE2F8a052B82f1484252B3",
        "chain_id": 1,
        "peak_date": "2026-01-26",  # ATH $87.79
        "phase": "pump",
    },
    {
        "name": "Folks Finance (PUMP)",
        "symbol": "FOLKS",
        "contract": "0xff7f8f301f7a706e3cfd3d2275f5dc0b9ee8009b",
        "chain_id": 1,
        "peak_date": "2025-12-14",  # ATH $50
        "phase": "pump",
    },
    # DUMP phases (distribution after peak)
    {
        "name": "River (DUMP)",
        "symbol": "RIVER_DUMP",
        "contract": "0xdA7AD9dea9397cffdDAE2F8a052B82f1484252B3",
        "chain_id": 1,
        "peak_date": "2026-03-01",  # Recent price ~$15 (dumped from $87)
        "phase": "dump",
    },
    {
        "name": "Folks Finance (DUMP)",
        "symbol": "FOLKS_DUMP",
        "contract": "0xff7f8f301f7a706e3cfd3d2275f5dc0b9ee8009b",
        "chain_id": 1,
        "peak_date": "2026-02-01",  # Post-ATH dump period
        "phase": "dump",
    },
]


def collect_transfers(token: dict) -> list:
    """Collect all transfers for a token from T-30 to T (peak)."""
    contract = token["contract"]
    chain_id = token["chain_id"]
    peak_date = token["peak_date"]

    # T = peak, T-30 = 30 days before peak (wider window for context)
    peak_ts = int(datetime.strptime(peak_date, "%Y-%m-%d").timestamp())
    t_minus_30_ts = peak_ts - 30 * 86400
    t_minus_14_ts = peak_ts - 14 * 86400
    t_minus_7_ts = peak_ts - 7 * 86400

    # Get block numbers
    print(f"  Getting block numbers...")
    block_t30 = get_block_by_timestamp(chain_id, t_minus_30_ts, "before")
    block_t14 = get_block_by_timestamp(chain_id, t_minus_14_ts, "before")
    block_t7 = get_block_by_timestamp(chain_id, t_minus_7_ts, "before")
    block_peak = get_block_by_timestamp(chain_id, peak_ts, "before")

    if not all([block_t30, block_t14, block_t7, block_peak]):
        print(f"  ERROR: Could not get block numbers")
        return []

    print(f"  Blocks: T-30={block_t30}, T-14={block_t14}, T-7={block_t7}, T={block_peak}")

    # Collect all transfers T-30 to T
    print(f"  Collecting transfers from block {block_t30} to {block_peak}...")
    all_transfers = []
    start_block = block_t30

    while True:
        transfers = get_token_transfers(
            chain_id=chain_id,
            contract=contract,
            start_block=start_block,
            end_block=block_peak,
            offset=10000,
            sort="asc",
        )
        if not transfers:
            break

        all_transfers.extend(transfers)
        print(f"    Got {len(transfers)} transfers (total: {len(all_transfers)})")

        if len(transfers) < 10000:
            break

        # Pagination: next batch starts after last block
        last_block = max(int(t["blockNumber"]) for t in transfers)
        if last_block >= block_peak:
            break
        start_block = last_block + 1
        time.sleep(0.3)

    print(f"  Total: {len(all_transfers)} transfers")

    return {
        "transfers": all_transfers,
        "blocks": {
            "t_minus_30": block_t30,
            "t_minus_14": block_t14,
            "t_minus_7": block_t7,
            "t_peak": block_peak,
        },
        "timestamps": {
            "t_minus_30": t_minus_30_ts,
            "t_minus_14": t_minus_14_ts,
            "t_minus_7": t_minus_7_ts,
            "t_peak": peak_ts,
        },
    }


def analyze_token(token: dict, data: dict, db: LabelDB) -> dict:
    """Deep analysis of a single token to find manipulators."""
    transfers = data["transfers"]
    chain_id = token["chain_id"]
    ts = data["timestamps"]

    if not transfers:
        return {"error": "No transfers"}

    # Label addresses
    all_addrs = set()
    for t in transfers:
        all_addrs.add(t["from"].lower())
        all_addrs.add(t["to"].lower())

    labels = {}
    for addr in all_addrs:
        label = db.lookup(addr, chain_id)
        if label:
            labels[addr] = label

    # ===== BUILD ADDRESS PROFILES =====
    # Periods: early (T-30→T-14), baseline (T-14→T-7), signal (T-7→T)
    profiles = {}

    for t in transfers:
        sender = t["from"].lower()
        receiver = t["to"].lower()
        tx_ts = int(t["timeStamp"])
        value = int(t.get("value", 0))

        if tx_ts < ts["t_minus_30"]:
            continue

        if tx_ts < ts["t_minus_14"]:
            period = "early"
        elif tx_ts < ts["t_minus_7"]:
            period = "baseline"
        else:
            period = "signal"

        for addr, role in [(sender, "out"), (receiver, "in")]:
            if addr not in profiles:
                profiles[addr] = {
                    "label": labels.get(addr, {}).get("type", "unknown"),
                    "entity": labels.get(addr, {}).get("entity", "unknown"),
                    "name": labels.get(addr, {}).get("name", ""),
                    "early": _empty_period(),
                    "baseline": _empty_period(),
                    "signal": _empty_period(),
                }

            p = profiles[addr][period]
            p[f"{role}_count"] += 1
            p[f"{role}_volume"] += value
            other = receiver if addr == sender else sender
            p["counterparties"].add(other)
            p["timestamps"].append(tx_ts)
            p["tx_hashes"].add(t.get("hash", ""))

            # Track interaction types
            other_type = labels.get(other, {}).get("type", "unknown")
            if other_type == "cex":
                p["cex_interactions"] += 1
            elif other_type == "dex":
                p["dex_interactions"] += 1

    # ===== COMPUTE MANIPULATION SCORES =====
    total_volume = sum(int(t.get("value", 0)) for t in transfers)

    scores = {}
    for addr, prof in profiles.items():
        if prof["label"] in ("cex", "dex", "bridge", "token", "airdrop"):
            continue

        score = 0
        reasons = []

        # Total volume across all periods
        addr_vol = sum(
            prof[p]["in_volume"] + prof[p]["out_volume"]
            for p in ["early", "baseline", "signal"]
        )
        vol_pct = addr_vol / max(total_volume, 1) * 100

        # 1. Volume concentration (>1% = suspicious)
        if vol_pct > 5:
            score += 3
            reasons.append(f"volume={vol_pct:.1f}%")
        elif vol_pct > 1:
            score += 1
            reasons.append(f"volume={vol_pct:.1f}%")

        # 2. Accumulation before pump (net inflow in early/baseline, net outflow in signal)
        early_net = prof["early"]["in_volume"] - prof["early"]["out_volume"]
        baseline_net = prof["baseline"]["in_volume"] - prof["baseline"]["out_volume"]
        signal_net = prof["signal"]["in_volume"] - prof["signal"]["out_volume"]

        if early_net > 0 and signal_net < 0 and addr_vol > 0:
            # Accumulated early, sold later — classic pump pattern
            accum_then_dump = min(abs(early_net), abs(signal_net)) / max(addr_vol, 1)
            if accum_then_dump > 0.3:
                score += 3
                reasons.append(f"accum_then_dump={accum_then_dump:.2f}")
            elif accum_then_dump > 0.1:
                score += 1
                reasons.append(f"accum_then_dump={accum_then_dump:.2f}")

        if baseline_net > 0 and signal_net < 0:
            score += 2
            reasons.append("baseline_accum→signal_dump")

        # 3. CEX-DEX bridging (interacts with both)
        total_cex = sum(prof[p]["cex_interactions"] for p in ["early", "baseline", "signal"])
        total_dex = sum(prof[p]["dex_interactions"] for p in ["early", "baseline", "signal"])
        if total_cex >= 2 and total_dex >= 2:
            score += 2
            reasons.append(f"cex_dex_bridge(cex={total_cex},dex={total_dex})")

        # 4. High transaction count (bot-like)
        total_tx = sum(
            prof[p]["in_count"] + prof[p]["out_count"]
            for p in ["early", "baseline", "signal"]
        )
        if total_tx >= 50:
            score += 2
            reasons.append(f"high_tx={total_tx}")
        elif total_tx >= 20:
            score += 1
            reasons.append(f"tx_count={total_tx}")

        # 5. Activity spike in signal period
        baseline_tx = prof["baseline"]["in_count"] + prof["baseline"]["out_count"]
        signal_tx = prof["signal"]["in_count"] + prof["signal"]["out_count"]
        if baseline_tx > 0 and signal_tx / max(baseline_tx, 1) > 3:
            score += 1
            reasons.append(f"signal_spike={signal_tx/max(baseline_tx,1):.1f}x")

        # 6. Many counterparties (distribution network)
        total_cp = len(set().union(
            prof["early"]["counterparties"],
            prof["baseline"]["counterparties"],
            prof["signal"]["counterparties"]
        ))
        if total_cp >= 20:
            score += 1
            reasons.append(f"counterparties={total_cp}")

        # 7. Known MM label
        if prof["label"] == "market_maker":
            score += 3
            reasons.append(f"known_mm={prof['entity']}")

        if score > 0:
            scores[addr] = {
                "score": score,
                "reasons": reasons,
                "vol_pct": vol_pct,
                "total_tx": total_tx,
                "total_cp": total_cp,
                "early_net": early_net,
                "baseline_net": baseline_net,
                "signal_net": signal_net,
                "label": prof["label"],
                "entity": prof["entity"],
                "name": prof["name"],
                "cex_interactions": total_cex,
                "dex_interactions": total_dex,
            }

    # ===== FUNDING CLUSTER ANALYSIS =====
    # Who funded whom? Find the funding tree
    funding_graph = defaultdict(set)
    for t in transfers:
        sender = t["from"].lower()
        receiver = t["to"].lower()
        s_type = labels.get(sender, {}).get("type", "unknown")
        r_type = labels.get(receiver, {}).get("type", "unknown")
        if s_type not in ("cex", "dex", "bridge", "token", "airdrop"):
            if r_type not in ("cex", "dex", "bridge"):
                funding_graph[sender].add(receiver)

    # Find addresses that fund multiple others (potential puppet master)
    puppet_masters = {}
    for funder, funded in funding_graph.items():
        if len(funded) >= 3:
            puppet_masters[funder] = {
                "funded_count": len(funded),
                "funded_addrs": list(funded)[:20],  # cap for output
                "funder_score": scores.get(funder, {}).get("score", 0),
                "funder_vol_pct": scores.get(funder, {}).get("vol_pct", 0),
            }

    # ===== TEMPORAL SYNC ANALYSIS =====
    # Find groups of addresses that act within ±5 min windows repeatedly
    suspicious_addrs = [a for a, s in scores.items() if s["score"] >= 3]

    sync_groups = []
    if len(suspicious_addrs) >= 2:
        # Get timestamp vectors
        addr_times = {}
        for addr in suspicious_addrs:
            times = sorted(
                profiles[addr]["early"]["timestamps"] +
                profiles[addr]["baseline"]["timestamps"] +
                profiles[addr]["signal"]["timestamps"]
            )
            if times:
                addr_times[addr] = times

        # Pairwise sync check
        sync_pairs = []
        addrs = sorted(addr_times.keys())
        for i in range(len(addrs)):
            for j in range(i + 1, len(addrs)):
                a1, a2 = addrs[i], addrs[j]
                t1, t2 = addr_times[a1], addr_times[a2]
                sync = 0
                for ts1 in t1:
                    for ts2 in t2:
                        if abs(ts1 - ts2) <= 300:  # 5 min
                            sync += 1
                            break
                if sync >= 2:
                    sync_pairs.append((a1, a2, sync))

        if sync_pairs:
            sync_groups = [{"pair": (a, b), "sync_count": s} for a, b, s in sync_pairs]

    # ===== RESULTS =====
    # Sort by score
    top_suspects = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)[:30]

    return {
        "token": token["name"],
        "symbol": token["symbol"],
        "n_transfers": len(transfers),
        "n_addresses": len(profiles),
        "n_labeled": len(labels),
        "total_volume": total_volume,
        "top_suspects": [
            {"address": addr, **info} for addr, info in top_suspects
        ],
        "puppet_masters": puppet_masters,
        "sync_groups": [
            {"addr1": g["pair"][0], "addr2": g["pair"][1], "sync_count": g["sync_count"]}
            for g in sync_groups
        ],
        "n_suspects_score_5plus": sum(1 for _, s in scores.items() if s["score"] >= 5),
        "n_suspects_score_3plus": sum(1 for _, s in scores.items() if s["score"] >= 3),
    }


def _empty_period():
    return {
        "in_count": 0, "out_count": 0,
        "in_volume": 0, "out_volume": 0,
        "counterparties": set(),
        "timestamps": [],
        "tx_hashes": set(),
        "cex_interactions": 0,
        "dex_interactions": 0,
    }


def print_report(result: dict):
    """Print human-readable report."""
    print(f"\n{'='*70}")
    print(f"  {result['token']} ({result['symbol']})")
    print(f"{'='*70}")
    print(f"  Transfers: {result['n_transfers']}")
    print(f"  Unique addresses: {result['n_addresses']}")
    print(f"  Labeled: {result['n_labeled']} ({result['n_labeled']/max(result['n_addresses'],1)*100:.1f}%)")
    print(f"  Suspects (score>=5): {result['n_suspects_score_5plus']}")
    print(f"  Suspects (score>=3): {result['n_suspects_score_3plus']}")

    print(f"\n  TOP SUSPECTS:")
    print(f"  {'Rank':>4}  {'Score':>5}  {'Vol%':>6}  {'TX':>5}  {'Label':>15}  {'Address':42}  Reasons")
    print(f"  {'-'*130}")
    for i, s in enumerate(result["top_suspects"][:15], 1):
        reasons_str = ", ".join(s["reasons"])
        label = s.get("entity", s.get("label", "?"))[:15]
        print(f"  {i:4d}  {s['score']:5d}  {s['vol_pct']:5.1f}%  {s['total_tx']:5d}  {label:>15}  {s['address'][:42]}  {reasons_str}")

    if result["puppet_masters"]:
        print(f"\n  PUPPET MASTERS (fund 3+ other addresses):")
        for addr, info in sorted(result["puppet_masters"].items(),
                                  key=lambda x: x[1]["funded_count"], reverse=True)[:10]:
            print(f"    {addr[:42]}  funds {info['funded_count']} addrs, score={info['funder_score']}")

    if result["sync_groups"]:
        print(f"\n  SYNCHRONIZED PAIRS (act within ±5 min):")
        for sg in result["sync_groups"][:10]:
            print(f"    {sg['addr1'][:20]}... ↔ {sg['addr2'][:20]}...  sync={sg['sync_count']} times")


def main():
    from dotenv import load_dotenv
    load_dotenv(DATA_DIR.parent / ".env")

    db = LabelDB()
    db.load_all()
    print(f"LabelDB: {db.stats()['total']} labels")

    all_results = []

    for token in TARGETS:
        print(f"\n{'='*70}")
        print(f"  Processing: {token['name']} ({token['symbol']})")
        print(f"{'='*70}")

        # Check if transfers already collected
        cache_file = MANIPULATOR_DIR / f"{token['symbol'].lower()}_transfers.json"
        if cache_file.exists():
            print(f"  Loading cached transfers from {cache_file}")
            with open(cache_file) as f:
                data = json.load(f)
        else:
            data = collect_transfers(token)
            # Save transfers
            with open(cache_file, "w") as f:
                json.dump(data, f)
            print(f"  Saved to {cache_file}")

        # Analyze
        result = analyze_token(token, data, db)
        all_results.append(result)

        # Print report
        print_report(result)

    # Save combined results
    output_file = MANIPULATOR_DIR / "manipulator_analysis.json"

    def convert(obj):
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        raise TypeError(f"Cannot serialize {type(obj)}")

    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, default=convert)
    print(f"\nResults saved to {output_file}")

    # ===== EXTRACT BEHAVIORAL PATTERNS =====
    print(f"\n{'='*70}")
    print(f"  BEHAVIORAL PATTERNS OF MANIPULATORS")
    print(f"{'='*70}")

    for result in all_results:
        print(f"\n  {result['token']}:")
        top5 = result["top_suspects"][:5]
        if not top5:
            print("    No suspects found")
            continue

        # Common patterns
        patterns = defaultdict(int)
        for s in result["top_suspects"]:
            for r in s["reasons"]:
                key = r.split("=")[0] if "=" in r else r
                patterns[key] += 1

        print(f"    Pattern frequency among all suspects:")
        for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
            print(f"      {pattern}: {count}")

        # Average behavior of top-5 suspects
        avg_vol = np.mean([s["vol_pct"] for s in top5])
        avg_tx = np.mean([s["total_tx"] for s in top5])
        avg_cp = np.mean([s["total_cp"] for s in top5])
        avg_cex = np.mean([s["cex_interactions"] for s in top5])
        avg_dex = np.mean([s["dex_interactions"] for s in top5])

        print(f"\n    Top-5 suspect profile:")
        print(f"      Avg volume share: {avg_vol:.1f}%")
        print(f"      Avg transactions: {avg_tx:.0f}")
        print(f"      Avg counterparties: {avg_cp:.0f}")
        print(f"      Avg CEX interactions: {avg_cex:.0f}")
        print(f"      Avg DEX interactions: {avg_dex:.0f}")

        # Accumulation/distribution pattern
        n_accum_dump = sum(1 for s in top5
                          if s.get("baseline_net", 0) > 0 and s.get("signal_net", 0) < 0)
        print(f"      Accum→Dump pattern: {n_accum_dump}/{len(top5)}")


if __name__ == "__main__":
    main()
