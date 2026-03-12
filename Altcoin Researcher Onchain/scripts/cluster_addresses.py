"""
Address clustering and market maker detection for onchain signal discovery.

Approach:
1. For each token's transfer data, build address behavior profiles
2. Cluster related addresses using:
   - Funding source: addresses with common funding parent = same entity
   - Temporal sync: addresses making similar moves within ±5 min = coordinated
   - Volume pattern: addresses with correlated buy/sell timing = potential MM/team
3. Heuristic MM detection: addresses active on both CEX and DEX sides
4. Classify clusters: team, investor, mm, retail
5. Compare cluster behavior T-7→T vs T-14→T-7 (baseline)
6. Statistical tests: winners vs losers

Output: data/cluster_analysis.json with per-token cluster metrics
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from label_db import LabelDB

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSFERS_DIR = DATA_DIR / "transfers"
REPORT_FILE = DATA_DIR / "cluster_analysis_report.md"
OUTPUT_FILE = DATA_DIR / "cluster_analysis.json"

# Clustering parameters
TEMPORAL_WINDOW = 300  # 5 minutes — addresses acting within this window = potential sync
MIN_CLUSTER_SIZE = 2  # minimum addresses to form a cluster
WHALE_VOLUME_PCT = 0.05  # >5% of total volume = whale


def load_token_data(coin_id: str) -> Optional[dict]:
    """Load transfer data for a token."""
    fpath = TRANSFERS_DIR / f"{coin_id}.json"
    if not fpath.exists():
        return None
    with open(fpath) as f:
        return json.load(f)


def build_address_profiles(transfers: list, labels: dict, ts_t7: int, ts_t14: int, ts_t: int) -> dict:
    """
    Build behavioral profile for each address.

    Profile includes:
    - transfer counts (in/out) in baseline (T-14→T-7) and signal (T-7→T) periods
    - volume in/out per period
    - counterparties (unique addresses interacted with)
    - timing patterns (average time between transactions)
    - labeled type from LabelDB
    - interaction with CEX and DEX addresses
    """
    profiles = {}

    for t in transfers:
        sender = t["from"].lower()
        receiver = t["to"].lower()
        ts = int(t["timeStamp"])
        value = int(t["value"]) if t.get("value") else 0

        # Determine period
        if ts_t14 <= ts < ts_t7:
            period = "baseline"
        elif ts_t7 <= ts <= ts_t:
            period = "signal"
        else:
            continue

        for addr, role in [(sender, "out"), (receiver, "in")]:
            if addr not in profiles:
                profiles[addr] = {
                    "label": labels.get(addr, {}).get("type", "unknown"),
                    "entity": labels.get(addr, {}).get("entity", "unknown"),
                    "baseline": {"in_count": 0, "out_count": 0, "in_volume": 0, "out_volume": 0,
                                "counterparties": set(), "timestamps": [], "cex_interactions": 0, "dex_interactions": 0},
                    "signal": {"in_count": 0, "out_count": 0, "in_volume": 0, "out_volume": 0,
                              "counterparties": set(), "timestamps": [], "cex_interactions": 0, "dex_interactions": 0},
                }

            p = profiles[addr][period]
            p[f"{role}_count"] += 1
            p[f"{role}_volume"] += value
            other = receiver if addr == sender else sender
            p["counterparties"].add(other)
            p["timestamps"].append(ts)

            # Track CEX/DEX interactions
            other_type = labels.get(other, {}).get("type", "unknown")
            if other_type == "cex":
                p["cex_interactions"] += 1
            elif other_type == "dex":
                p["dex_interactions"] += 1

    # Convert sets to counts for serialization
    for addr, prof in profiles.items():
        for period in ["baseline", "signal"]:
            prof[period]["n_counterparties"] = len(prof[period]["counterparties"])
            del prof[period]["counterparties"]
            prof[period]["timestamps"].sort()

    return profiles


def find_funding_clusters(transfers: list, labels: dict) -> dict:
    """
    Group addresses by common funding source.

    Logic: if address A sends to B and C (and B,C are not CEX/DEX),
    then B and C are potentially in the same cluster (funded by A).

    Returns: {cluster_id: [addresses]}
    """
    # Build funding graph: who funded whom
    funded_by = defaultdict(set)  # address -> set of funders
    funds_to = defaultdict(set)   # address -> set of funded addresses

    for t in transfers:
        sender = t["from"].lower()
        receiver = t["to"].lower()
        sender_type = labels.get(sender, {}).get("type", "unknown")
        receiver_type = labels.get(receiver, {}).get("type", "unknown")

        # Skip if sender is CEX/DEX/bridge (not a real funding relationship)
        if sender_type in ("cex", "dex", "bridge", "token", "airdrop"):
            continue
        # Skip if receiver is CEX/DEX (it's a deposit, not funding)
        if receiver_type in ("cex", "dex", "bridge"):
            continue

        funded_by[receiver].add(sender)
        funds_to[sender].add(receiver)

    # Cluster: addresses funded by the same parent
    parent_clusters = defaultdict(set)
    for parent, children in funds_to.items():
        if len(children) >= MIN_CLUSTER_SIZE:
            # This parent funds multiple addresses — they form a cluster
            cluster_key = parent
            parent_clusters[cluster_key] = children | {parent}

    # Merge overlapping clusters (if address A is in cluster 1 and 2)
    clusters = {}
    addr_to_cluster = {}
    cluster_id = 0

    for parent, members in parent_clusters.items():
        # Check if any member already belongs to a cluster
        existing = set()
        for m in members:
            if m in addr_to_cluster:
                existing.add(addr_to_cluster[m])

        if existing:
            # Merge into the first existing cluster
            target = min(existing)
            for cid in existing:
                if cid != target and cid in clusters:
                    clusters[target] |= clusters[cid]
                    for m in clusters[cid]:
                        addr_to_cluster[m] = target
                    del clusters[cid]
            clusters[target] |= members
            for m in members:
                addr_to_cluster[m] = target
        else:
            clusters[cluster_id] = members
            for m in members:
                addr_to_cluster[m] = cluster_id
            cluster_id += 1

    return clusters


def find_temporal_clusters(transfers: list, labels: dict, profiles: dict) -> dict:
    """
    Find addresses acting in temporal sync.

    If multiple addresses make transfers within ±TEMPORAL_WINDOW of each other
    repeatedly, they are likely coordinated.

    Returns: {cluster_id: [addresses]}
    """
    # Collect non-labeled (unknown) addresses with significant activity
    active_addrs = []
    for addr, prof in profiles.items():
        label_type = prof["label"]
        if label_type in ("cex", "dex", "bridge", "token", "airdrop"):
            continue
        total_tx = (prof["signal"]["in_count"] + prof["signal"]["out_count"] +
                   prof["baseline"]["in_count"] + prof["baseline"]["out_count"])
        if total_tx >= 3:
            active_addrs.append(addr)

    if len(active_addrs) < 2:
        return {}

    # Cap at 200 most active addresses to avoid O(n²) blowup
    if len(active_addrs) > 200:
        active_addrs.sort(key=lambda a: sum(
            profiles[a][p][f"{d}_count"]
            for p in ["baseline", "signal"] for d in ["in", "out"]
        ), reverse=True)
        active_addrs = active_addrs[:200]

    # Build timestamp vectors for each address
    addr_times = {}
    for addr in active_addrs:
        times = sorted(
            profiles[addr]["baseline"]["timestamps"] +
            profiles[addr]["signal"]["timestamps"]
        )
        if times:
            addr_times[addr] = times

    # Find pairs that act in sync
    sync_pairs = defaultdict(int)  # (addr1, addr2) -> count of synced actions

    addrs = sorted(addr_times.keys())
    for i in range(len(addrs)):
        for j in range(i + 1, len(addrs)):
            a1, a2 = addrs[i], addrs[j]
            t1, t2 = addr_times[a1], addr_times[a2]

            # Count temporal overlaps
            sync_count = 0
            j_start = 0
            for ts1 in t1:
                for k in range(j_start, len(t2)):
                    diff = abs(ts1 - t2[k])
                    if diff <= TEMPORAL_WINDOW:
                        sync_count += 1
                        break
                    elif t2[k] > ts1 + TEMPORAL_WINDOW:
                        break
                    else:
                        j_start = k

            # If synced on 3+ occasions, likely coordinated
            if sync_count >= 3:
                sync_pairs[(a1, a2)] = sync_count

    # Build clusters from sync pairs (union-find)
    parent = {}
    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for (a1, a2) in sync_pairs:
        union(a1, a2)

    # Group by root
    groups = defaultdict(set)
    for (a1, a2) in sync_pairs:
        root = find(a1)
        groups[root].add(a1)
        groups[root].add(a2)

    clusters = {}
    for cid, (root, members) in enumerate(groups.items()):
        if len(members) >= MIN_CLUSTER_SIZE:
            clusters[f"temporal_{cid}"] = members

    return clusters


def detect_heuristic_mm(profiles: dict, labels: dict) -> list:
    """
    Heuristic MM detection: addresses that interact with both CEX and DEX
    with high volume, suggesting they bridge liquidity between venues.

    Criteria:
    - At least 1 CEX interaction AND 1 DEX interaction
    - Total tx count >= 10
    - Not already labeled as cex/dex/bridge
    """
    mm_candidates = []

    for addr, prof in profiles.items():
        if prof["label"] in ("cex", "dex", "bridge", "token", "airdrop"):
            continue

        total_cex = (prof["baseline"]["cex_interactions"] + prof["signal"]["cex_interactions"])
        total_dex = (prof["baseline"]["dex_interactions"] + prof["signal"]["dex_interactions"])
        total_tx = sum(
            prof[p][f"{d}_count"]
            for p in ["baseline", "signal"]
            for d in ["in", "out"]
        )

        if total_cex >= 1 and total_dex >= 1 and total_tx >= 10:
            mm_candidates.append({
                "address": addr,
                "cex_interactions": total_cex,
                "dex_interactions": total_dex,
                "total_tx": total_tx,
                "known_entity": prof["entity"],
                "known_label": prof["label"],
            })

    return mm_candidates


def classify_cluster(members: set, profiles: dict, labels: dict, mm_addrs: set) -> str:
    """
    Classify a cluster as team/investor/mm/retail based on member behavior.

    - MM: cluster contains known MM or heuristic MM addresses
    - Team: cluster with addresses that only sell/distribute (net outflow)
    - Investor: cluster with addresses that accumulate then hold (net inflow, low tx count)
    - Retail: everything else
    """
    has_mm = bool(members & mm_addrs)
    has_known_mm = any(
        profiles.get(m, {}).get("label") == "market_maker"
        for m in members
    )

    if has_mm or has_known_mm:
        return "mm"

    # Check if cluster is mostly distributing (team-like)
    total_in = sum(profiles.get(m, {}).get("signal", {}).get("in_volume", 0) for m in members)
    total_out = sum(profiles.get(m, {}).get("signal", {}).get("out_volume", 0) for m in members)

    if total_out > 0 and total_in / max(total_out, 1) < 0.2:
        return "team"  # mostly distributing

    # Check if accumulating (investor-like)
    avg_tx = np.mean([
        sum(profiles.get(m, {}).get(p, {}).get(f"{d}_count", 0)
            for p in ["baseline", "signal"] for d in ["in", "out"])
        for m in members
    ]) if members else 0

    if total_in > total_out * 1.5 and avg_tx < 20:
        return "investor"

    return "retail"


def compute_cluster_metrics(clusters: dict, profiles: dict, labels: dict,
                           mm_addrs: set, total_volume: float) -> dict:
    """
    Compute per-period metrics for each cluster type.

    Returns metrics aggregated by cluster type (team/investor/mm/retail).
    """
    type_metrics = defaultdict(lambda: {
        "baseline": {"volume": 0, "tx_count": 0, "n_addresses": 0, "n_clusters": 0},
        "signal": {"volume": 0, "tx_count": 0, "n_addresses": 0, "n_clusters": 0},
    })

    for cid, members in clusters.items():
        ctype = classify_cluster(members, profiles, labels, mm_addrs)

        for period in ["baseline", "signal"]:
            vol = sum(
                profiles.get(m, {}).get(period, {}).get("in_volume", 0) +
                profiles.get(m, {}).get(period, {}).get("out_volume", 0)
                for m in members
            )
            tx = sum(
                profiles.get(m, {}).get(period, {}).get("in_count", 0) +
                profiles.get(m, {}).get(period, {}).get("out_count", 0)
                for m in members
            )
            type_metrics[ctype][period]["volume"] += vol
            type_metrics[ctype][period]["tx_count"] += tx
            type_metrics[ctype][period]["n_addresses"] += len(members)
        type_metrics[ctype]["signal"]["n_clusters"] += 1
        type_metrics[ctype]["baseline"]["n_clusters"] += 1

    # Normalize by total volume
    for ctype in type_metrics:
        for period in ["baseline", "signal"]:
            if total_volume > 0:
                type_metrics[ctype][period]["volume_pct"] = (
                    type_metrics[ctype][period]["volume"] / total_volume * 100
                )

    return dict(type_metrics)


def compute_anomaly_scores(profiles: dict, labels: dict, mm_addrs: set) -> dict:
    """
    Compute anomaly scores comparing T-7→T vs T-14→T-7.

    Anomalies:
    - mm_volume_spike: MM volume ratio (signal/baseline)
    - new_addr_activation: addresses active only in signal period
    - coordinated_buying: multiple addresses buying in sync in signal period
    - whale_accumulation: large net inflow in signal period
    - cex_withdrawal_spike: spike in CEX withdrawals in signal period
    """
    metrics = {}

    # MM activity spike
    mm_baseline_vol = 0
    mm_signal_vol = 0
    mm_baseline_tx = 0
    mm_signal_tx = 0

    for addr in mm_addrs:
        prof = profiles.get(addr, {})
        mm_baseline_vol += prof.get("baseline", {}).get("in_volume", 0) + prof.get("baseline", {}).get("out_volume", 0)
        mm_signal_vol += prof.get("signal", {}).get("in_volume", 0) + prof.get("signal", {}).get("out_volume", 0)
        mm_baseline_tx += prof.get("baseline", {}).get("in_count", 0) + prof.get("baseline", {}).get("out_count", 0)
        mm_signal_tx += prof.get("signal", {}).get("in_count", 0) + prof.get("signal", {}).get("out_count", 0)

    metrics["mm_volume_ratio"] = mm_signal_vol / max(mm_baseline_vol, 1)
    metrics["mm_tx_ratio"] = mm_signal_tx / max(mm_baseline_tx, 1)

    # New address activation: addresses only active in signal period
    signal_only = 0
    baseline_only = 0
    both = 0
    for addr, prof in profiles.items():
        if prof["label"] in ("cex", "dex", "bridge", "token"):
            continue
        has_baseline = (prof["baseline"]["in_count"] + prof["baseline"]["out_count"]) > 0
        has_signal = (prof["signal"]["in_count"] + prof["signal"]["out_count"]) > 0
        if has_signal and not has_baseline:
            signal_only += 1
        elif has_baseline and not has_signal:
            baseline_only += 1
        elif has_baseline and has_signal:
            both += 1

    metrics["new_addr_count"] = signal_only
    metrics["new_addr_ratio"] = signal_only / max(both + baseline_only, 1)

    # Whale accumulation in signal period
    whale_net_inflow = 0
    whale_count = 0
    total_signal_vol = sum(
        prof["signal"]["in_volume"] + prof["signal"]["out_volume"]
        for prof in profiles.values()
    )

    for addr, prof in profiles.items():
        if prof["label"] in ("cex", "dex", "bridge", "token"):
            continue
        signal_vol = prof["signal"]["in_volume"] + prof["signal"]["out_volume"]
        if total_signal_vol > 0 and signal_vol / total_signal_vol > WHALE_VOLUME_PCT:
            whale_count += 1
            whale_net_inflow += prof["signal"]["in_volume"] - prof["signal"]["out_volume"]

    metrics["whale_net_inflow"] = whale_net_inflow
    metrics["whale_count_signal"] = whale_count

    # CEX withdrawal spike
    cex_withdrawal_baseline = 0
    cex_withdrawal_signal = 0
    cex_deposit_baseline = 0
    cex_deposit_signal = 0

    for addr, prof in profiles.items():
        if prof["label"] == "cex":
            cex_withdrawal_baseline += prof["baseline"]["out_volume"]
            cex_withdrawal_signal += prof["signal"]["out_volume"]
            cex_deposit_baseline += prof["baseline"]["in_volume"]
            cex_deposit_signal += prof["signal"]["in_volume"]

    metrics["cex_withdrawal_ratio"] = cex_withdrawal_signal / max(cex_withdrawal_baseline, 1)
    metrics["cex_deposit_ratio"] = cex_deposit_signal / max(cex_deposit_baseline, 1)
    metrics["cex_net_flow_baseline"] = cex_deposit_baseline - cex_withdrawal_baseline
    metrics["cex_net_flow_signal"] = cex_deposit_signal - cex_withdrawal_signal

    return metrics


def process_token(coin_id: str, db: LabelDB, max_transfers: int = 200000) -> Optional[dict]:
    """Process a single token: cluster addresses, detect MMs, compute anomalies."""
    data = load_token_data(coin_id)
    if not data or not data.get("transfers"):
        return None

    transfers = data["transfers"]

    # Cap transfers to keep analysis tractable on large BSC tokens
    if len(transfers) > max_transfers:
        step = len(transfers) / max_transfers
        transfers = [transfers[int(i * step)] for i in range(max_transfers)]

    chain_id = data.get("chain_id", 1)
    category = data.get("category", "unknown")

    ts_t14 = data["timestamps"]["t_minus_14"]
    ts_t7 = data["timestamps"]["t_minus_7"]
    ts_t = data["timestamps"]["t_event"]

    # Build labels
    all_addrs = set()
    for t in transfers:
        all_addrs.add(t["from"].lower())
        all_addrs.add(t["to"].lower())

    labels = {}
    for addr in all_addrs:
        label = db.lookup(addr, chain_id)
        if label:
            labels[addr] = label

    # Build address profiles
    profiles = build_address_profiles(transfers, labels, ts_t7, ts_t14, ts_t)

    # Detect heuristic MMs
    mm_candidates = detect_heuristic_mm(profiles, labels)
    mm_addrs = {m["address"] for m in mm_candidates}

    # Add known MM labels
    for addr, prof in profiles.items():
        if prof["label"] == "market_maker":
            mm_addrs.add(addr)

    # Funding source clusters
    funding_clusters = find_funding_clusters(transfers, labels)

    # Temporal sync clusters
    temporal_clusters = find_temporal_clusters(transfers, labels, profiles)

    # Merge all clusters
    all_clusters = {}
    for cid, members in funding_clusters.items():
        all_clusters[f"funding_{cid}"] = members
    all_clusters.update(temporal_clusters)

    # Total volume for normalization
    total_volume = sum(int(t.get("value", 0)) for t in transfers)

    # Cluster metrics
    cluster_metrics = compute_cluster_metrics(all_clusters, profiles, labels, mm_addrs, total_volume)

    # Anomaly scores
    anomalies = compute_anomaly_scores(profiles, labels, mm_addrs)

    return {
        "coin_id": coin_id,
        "category": category,
        "chain_id": chain_id,
        "n_transfers": len(transfers),
        "n_addresses": len(profiles),
        "n_mm_known": sum(1 for a in mm_addrs if profiles.get(a, {}).get("label") == "market_maker"),
        "n_mm_heuristic": len(mm_candidates),
        "n_funding_clusters": len(funding_clusters),
        "n_temporal_clusters": len(temporal_clusters),
        "cluster_metrics": cluster_metrics,
        "anomalies": anomalies,
    }


def run_statistical_tests(results: list) -> dict:
    """Run Mann-Whitney U tests: winners vs losers for all anomaly metrics."""
    from scipy.stats import mannwhitneyu

    winners = [r for r in results if r["category"] == "winner"]
    losers = [r for r in results if r["category"] == "loser"]

    print(f"\n{'='*60}")
    print(f"STATISTICAL TESTS: {len(winners)}W vs {len(losers)}L")
    print(f"{'='*60}")

    # Collect all anomaly metric names
    metric_names = set()
    for r in results:
        metric_names.update(r["anomalies"].keys())

    test_results = {}
    for metric in sorted(metric_names):
        w_vals = [r["anomalies"].get(metric, 0) for r in winners]
        l_vals = [r["anomalies"].get(metric, 0) for r in losers]

        # Filter out None/inf
        w_vals = [float(v) for v in w_vals if v is not None]
        l_vals = [float(v) for v in l_vals if v is not None]
        w_vals = [v for v in w_vals if np.isfinite(v)]
        l_vals = [v for v in l_vals if np.isfinite(v)]

        if len(w_vals) < 5 or len(l_vals) < 5:
            continue

        try:
            stat, pval = mannwhitneyu(w_vals, l_vals, alternative="two-sided")
            effect_size = 1 - (2 * stat) / (len(w_vals) * len(l_vals))

            w_med = np.median(w_vals)
            l_med = np.median(l_vals)

            test_results[metric] = {
                "p_value": pval,
                "effect_size": effect_size,
                "winner_median": w_med,
                "loser_median": l_med,
                "ratio": w_med / max(l_med, 0.001) if l_med != 0 else float("inf"),
            }

            sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
            print(f"  {metric:35s} W={w_med:10.2f}  L={l_med:10.2f}  p={pval:.4f} {sig}  effect={effect_size:.3f}")
        except Exception as e:
            print(f"  {metric:35s} ERROR: {e}")

    # Also test cluster-level metrics
    print(f"\n{'='*60}")
    print("CLUSTER TYPE METRICS")
    print(f"{'='*60}")

    for ctype in ["mm", "team", "investor", "retail"]:
        for period in ["signal"]:
            for mkey in ["volume_pct", "tx_count", "n_addresses"]:
                feature_name = f"cluster_{ctype}_{period}_{mkey}"
                w_vals = []
                l_vals = []
                for r in results:
                    cm = r.get("cluster_metrics", {}).get(ctype, {}).get(period, {})
                    val = cm.get(mkey, 0)
                    if r["category"] == "winner":
                        w_vals.append(val)
                    else:
                        l_vals.append(val)

                w_vals = [v for v in w_vals if v is not None and np.isfinite(v)]
                l_vals = [v for v in l_vals if v is not None and np.isfinite(v)]

                if len(w_vals) < 5 or len(l_vals) < 5:
                    continue

                try:
                    stat, pval = mannwhitneyu(w_vals, l_vals, alternative="two-sided")
                    effect_size = 1 - (2 * stat) / (len(w_vals) * len(l_vals))
                    w_med = np.median(w_vals)
                    l_med = np.median(l_vals)

                    sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
                    print(f"  {feature_name:45s} W={w_med:10.2f}  L={l_med:10.2f}  p={pval:.4f} {sig}")

                    test_results[feature_name] = {
                        "p_value": pval,
                        "effect_size": effect_size,
                        "winner_median": w_med,
                        "loser_median": l_med,
                    }
                except:
                    pass

    return test_results


def generate_report(results: list, test_results: dict):
    """Generate markdown report."""
    winners = [r for r in results if r["category"] == "winner"]
    losers = [r for r in results if r["category"] == "loser"]

    lines = [
        "# Address Clustering & Market Maker Analysis Report",
        "",
        f"**Tokens analyzed**: {len(results)} ({len(winners)}W vs {len(losers)}L)",
        "",
        "## Summary Statistics",
        "",
        f"| Metric | Winners (median) | Losers (median) |",
        f"|--------|-----------------|-----------------|",
    ]

    for metric in ["n_mm_heuristic", "n_funding_clusters", "n_temporal_clusters"]:
        w_med = np.median([r[metric] for r in winners])
        l_med = np.median([r[metric] for r in losers])
        lines.append(f"| {metric} | {w_med:.1f} | {l_med:.1f} |")

    lines.extend(["", "## Significant Signals (p < 0.1)", ""])

    significant = {k: v for k, v in test_results.items() if v["p_value"] < 0.1}
    if significant:
        lines.append("| Feature | W median | L median | p-value | Effect |")
        lines.append("|---------|---------|---------|---------|--------|")
        for feat, vals in sorted(significant.items(), key=lambda x: x[1]["p_value"]):
            lines.append(
                f"| {feat} | {vals['winner_median']:.2f} | {vals['loser_median']:.2f} "
                f"| {vals['p_value']:.4f} | {vals['effect_size']:.3f} |"
            )
    else:
        lines.append("No significant signals found at p < 0.1")

    lines.extend(["", "## Methodology", "",
        "1. **Funding clusters**: addresses with common funding parent grouped together",
        "2. **Temporal clusters**: addresses acting within ±5 min windows on 3+ occasions",
        "3. **Heuristic MM**: addresses interacting with both CEX and DEX, 10+ total tx",
        "4. **Anomaly detection**: signal (T-7→T) vs baseline (T-14→T-7) ratios",
        "5. **Statistical test**: Mann-Whitney U (two-sided)",
    ])

    report = "\n".join(lines)
    REPORT_FILE.write_text(report)
    print(f"\nReport saved to {REPORT_FILE}")


def main():
    db = LabelDB()
    db.load_all()
    stats = db.stats()
    print(f"LabelDB: {stats['total']} labels ({stats['by_type'].get('market_maker', 0)} MM)")

    # Scan ALL transfer files (ETH + BSC)
    transfer_files = sorted(TRANSFERS_DIR.glob("*.json"))
    coin_ids = [f.stem for f in transfer_files]
    print(f"Found {len(coin_ids)} transfer files")

    # Process only tokens with collected transfers
    results = []
    errors = []

    for i, coin_id in enumerate(coin_ids):
        try:
            result = process_token(coin_id, db)
            if result:
                results.append(result)
                if (i + 1) % 20 == 0:
                    print(f"  [{i+1}/{len(coin_ids)}] Processed {len(results)} tokens...")
        except Exception as e:
            errors.append({"coin_id": coin_id, "error": str(e)})
            print(f"  ERROR {coin_id}: {e}")

    print(f"\nProcessed {len(results)} tokens ({len(errors)} errors)")

    # Statistical tests
    test_results = run_statistical_tests(results)

    # Save results
    output = {
        "n_tokens": len(results),
        "n_winners": sum(1 for r in results if r["category"] == "winner"),
        "n_losers": sum(1 for r in results if r["category"] == "loser"),
        "tokens": results,
        "test_results": {k: {kk: float(vv) if isinstance(vv, (np.floating, float)) else vv
                            for kk, vv in v.items()}
                        for k, v in test_results.items()},
        "errors": errors,
    }

    # Convert numpy types for JSON serialization
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, set):
            return list(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, default=convert)
    print(f"Results saved to {OUTPUT_FILE}")

    # Generate report
    generate_report(results, test_results)


if __name__ == "__main__":
    main()
