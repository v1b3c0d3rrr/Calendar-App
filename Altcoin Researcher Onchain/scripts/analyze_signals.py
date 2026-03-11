"""
Phase 4: Statistical analysis of onchain signals — winners vs losers.

ML approach:
- 70/15/15 train/val/test split (stratified by category)
- Feature extraction from labeled_metrics.json
- Statistical tests (Mann-Whitney U, effect size)
- Feature importance ranking
- Threshold calibration on train, validation on val, report on test

Signals analyzed:
- Transfer count delta (T-7→T vs T-14→T-7)
- CEX inflow/outflow patterns
- Whale volume concentration
- DEX activity
- Address diversity
- Volume patterns
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import random

DATA_DIR = Path(__file__).parent.parent / "data"
LABELED_FILE = DATA_DIR / "labeled" / "labeled_metrics.json"
REPORT_FILE = DATA_DIR / "onchain_signal_report.md"


def load_data():
    """Load labeled metrics and split into features."""
    with open(LABELED_FILE) as f:
        data = json.load(f)

    results = data["results"]

    # Filter: need both baseline and signal periods with data
    valid = []
    for r in results:
        bp = r.get("baseline_period", {})
        sp = r.get("signal_period", {})
        if bp.get("transfer_count", 0) > 0 and sp.get("transfer_count", 0) > 0:
            valid.append(r)

    return valid


def extract_features(token: dict) -> dict:
    """Extract ML features from a single token's metrics."""
    bp = token["baseline_period"]
    sp = token["signal_period"]
    deltas = token["deltas"]

    # Avoid division by zero
    def safe_ratio(a, b):
        return a / b if b != 0 else 0

    features = {
        # Category (target)
        "category": token["category"],
        "coin_id": token["coin_id"],
        "symbol": token["symbol"],
        "multiplier": token.get("multiplier"),
        "start_mc": token.get("start_mc"),

        # Signal period raw metrics
        "sp_transfer_count": sp.get("transfer_count", 0),
        "sp_unique_addresses": sp.get("unique_addresses", 0),
        "sp_cex_inflow_pct": sp.get("cex_inflow_pct", 0),
        "sp_cex_outflow_pct": sp.get("cex_outflow_pct", 0),
        "sp_cex_net_flow_pct": sp.get("cex_net_flow_pct", 0),
        "sp_dex_volume_pct": sp.get("dex_volume_pct", 0),
        "sp_whale_volume_pct": sp.get("whale_volume_pct", 0),
        "sp_bridge_volume_pct": sp.get("bridge_volume_pct", 0),

        # Baseline period raw metrics
        "bp_transfer_count": bp.get("transfer_count", 0),
        "bp_unique_addresses": bp.get("unique_addresses", 0),
        "bp_cex_inflow_pct": bp.get("cex_inflow_pct", 0),
        "bp_cex_outflow_pct": bp.get("cex_outflow_pct", 0),
        "bp_cex_net_flow_pct": bp.get("cex_net_flow_pct", 0),
        "bp_dex_volume_pct": bp.get("dex_volume_pct", 0),
        "bp_whale_volume_pct": bp.get("whale_volume_pct", 0),

        # Deltas (signal vs baseline)
        "delta_transfer_count": deltas.get("transfer_count_delta_pct"),
        "delta_unique_addresses": deltas.get("unique_addresses_delta_pct"),
        "delta_cex_inflow": deltas.get("cex_inflow_pct_delta_pct"),
        "delta_cex_outflow": deltas.get("cex_outflow_pct_delta_pct"),
        "delta_cex_net_flow": deltas.get("cex_net_flow_pct_delta_pct"),
        "delta_dex_volume": deltas.get("dex_volume_pct_delta_pct"),
        "delta_whale_volume": deltas.get("whale_volume_pct_delta_pct"),

        # Derived features
        "transfer_intensity": safe_ratio(sp.get("transfer_count", 0), bp.get("transfer_count", 1)),
        "address_growth": safe_ratio(sp.get("unique_addresses", 0), bp.get("unique_addresses", 1)),
        "cex_flow_shift": (sp.get("cex_net_flow_pct", 0) - bp.get("cex_net_flow_pct", 0)),
        "whale_shift": (sp.get("whale_volume_pct", 0) - bp.get("whale_volume_pct", 0)),
        "dex_shift": (sp.get("dex_volume_pct", 0) - bp.get("dex_volume_pct", 0)),
    }

    return features


def stratified_split(data: list, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=42):
    """Stratified train/val/test split by category."""
    random.seed(seed)

    by_cat = defaultdict(list)
    for item in data:
        by_cat[item["category"]].append(item)

    train, val, test = [], [], []

    for cat, items in by_cat.items():
        random.shuffle(items)
        n = len(items)
        n_train = max(1, int(n * train_ratio))
        n_val = max(1, int(n * val_ratio))

        train.extend(items[:n_train])
        val.extend(items[n_train:n_train + n_val])
        test.extend(items[n_train + n_val:])

    return train, val, test


def mann_whitney_u(group1: list, group2: list) -> dict:
    """Manual Mann-Whitney U test (no scipy needed)."""
    if not group1 or not group2:
        return {"u_stat": None, "p_value": None, "effect_size": None}

    n1 = len(group1)
    n2 = len(group2)

    # Combine and rank
    combined = [(v, 0) for v in group1] + [(v, 1) for v in group2]
    combined.sort(key=lambda x: x[0])

    # Assign ranks (handle ties)
    ranks = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2  # 1-indexed
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    # Sum ranks for group1
    r1 = sum(ranks[k] for k in range(len(combined)) if combined[k][1] == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    u_stat = min(u1, u2)

    # Normal approximation for p-value
    mu = n1 * n2 / 2
    sigma = (n1 * n2 * (n1 + n2 + 1) / 12) ** 0.5

    if sigma == 0:
        return {"u_stat": u_stat, "p_value": 1.0, "effect_size": 0.0}

    z = abs(u_stat - mu) / sigma

    # Two-tailed p-value approximation using error function
    import math
    p_value = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))

    # Effect size (rank-biserial correlation)
    effect_size = 1 - (2 * u_stat) / (n1 * n2)

    return {
        "u_stat": round(u_stat, 1),
        "p_value": round(p_value, 6),
        "effect_size": round(effect_size, 4),
        "z_score": round(z, 3),
    }


def analyze_feature(feature_name: str, winners: list, losers: list) -> dict:
    """Analyze a single feature's discriminative power."""
    w_vals = [f[feature_name] for f in winners if f.get(feature_name) is not None]
    l_vals = [f[feature_name] for f in losers if f.get(feature_name) is not None]

    if not w_vals or not l_vals:
        return None

    w_mean = sum(w_vals) / len(w_vals)
    l_mean = sum(l_vals) / len(l_vals)
    w_median = sorted(w_vals)[len(w_vals) // 2]
    l_median = sorted(l_vals)[len(l_vals) // 2]

    mwu = mann_whitney_u(w_vals, l_vals)

    return {
        "feature": feature_name,
        "w_count": len(w_vals),
        "l_count": len(l_vals),
        "w_mean": round(w_mean, 4),
        "l_mean": round(l_mean, 4),
        "w_median": round(w_median, 4),
        "l_median": round(l_median, 4),
        "ratio": round(w_mean / l_mean, 3) if l_mean != 0 else None,
        **mwu,
    }


def find_best_threshold(feature_name: str, train_data: list, target_recall=0.6):
    """Find threshold that best separates winners from losers on training data."""
    winners = [f[feature_name] for f in train_data if f["category"] == "winner" and f.get(feature_name) is not None]
    losers = [f[feature_name] for f in train_data if f["category"] == "loser" and f.get(feature_name) is not None]

    if not winners or not losers:
        return None

    all_vals = sorted(set(winners + losers))
    best_threshold = None
    best_f1 = 0
    best_direction = ">"

    for direction in [">", "<"]:
        for thresh in all_vals:
            if direction == ">":
                tp = sum(1 for v in winners if v > thresh)
                fp = sum(1 for v in losers if v > thresh)
                fn = sum(1 for v in winners if v <= thresh)
            else:
                tp = sum(1 for v in winners if v < thresh)
                fp = sum(1 for v in losers if v < thresh)
                fn = sum(1 for v in winners if v >= thresh)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            if f1 > best_f1:
                best_f1 = f1
                best_threshold = thresh
                best_direction = direction

    return {
        "threshold": best_threshold,
        "direction": best_direction,
        "train_f1": round(best_f1, 3),
    }


def evaluate_threshold(feature_name: str, data: list, threshold: float, direction: str):
    """Evaluate a threshold on a dataset."""
    winners = [f[feature_name] for f in data if f["category"] == "winner" and f.get(feature_name) is not None]
    losers = [f[feature_name] for f in data if f["category"] == "loser" and f.get(feature_name) is not None]

    if not winners or not losers:
        return None

    if direction == ">":
        tp = sum(1 for v in winners if v > threshold)
        fp = sum(1 for v in losers if v > threshold)
        fn = sum(1 for v in winners if v <= threshold)
        tn = sum(1 for v in losers if v <= threshold)
    else:
        tp = sum(1 for v in winners if v < threshold)
        fp = sum(1 for v in losers if v < threshold)
        fn = sum(1 for v in winners if v >= threshold)
        tn = sum(1 for v in losers if v >= threshold)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "accuracy": round(accuracy, 3),
    }


def main():
    print("Loading data...", flush=True)
    raw_data = load_data()
    print(f"Valid tokens: {len(raw_data)}", flush=True)

    # Extract features
    features = [extract_features(t) for t in raw_data]

    # Count categories
    cats = defaultdict(int)
    for f in features:
        cats[f["category"]] += 1
    print(f"Categories: {dict(cats)}", flush=True)

    # Train/val/test split (70/15/15, stratified)
    train, val, test = stratified_split(features)
    print(f"\nSplit: train={len(train)}, val={len(val)}, test={len(test)}")
    for split_name, split_data in [("train", train), ("val", val), ("test", test)]:
        sc = defaultdict(int)
        for f in split_data:
            sc[f["category"]] += 1
        print(f"  {split_name}: {dict(sc)}")

    # Analyze features on TRAINING set only
    feature_names = [
        "sp_transfer_count", "sp_unique_addresses",
        "sp_cex_inflow_pct", "sp_cex_outflow_pct", "sp_cex_net_flow_pct",
        "sp_dex_volume_pct", "sp_whale_volume_pct", "sp_bridge_volume_pct",
        "delta_transfer_count", "delta_unique_addresses",
        "delta_cex_inflow", "delta_cex_outflow", "delta_cex_net_flow",
        "delta_dex_volume", "delta_whale_volume",
        "transfer_intensity", "address_growth",
        "cex_flow_shift", "whale_shift", "dex_shift",
    ]

    train_w = [f for f in train if f["category"] == "winner"]
    train_l = [f for f in train if f["category"] == "loser"]

    print(f"\n{'='*80}")
    print(f"FEATURE ANALYSIS (on training set: {len(train_w)} winners vs {len(train_l)} losers)")
    print(f"{'='*80}")

    results = []
    for fname in feature_names:
        r = analyze_feature(fname, train_w, train_l)
        if r:
            results.append(r)

    # Sort by p-value
    results.sort(key=lambda x: x.get("p_value", 1))

    print(f"\n{'Feature':<30} {'W_mean':>10} {'L_mean':>10} {'Ratio':>8} {'p-value':>10} {'Effect':>8}")
    print("-" * 80)
    for r in results:
        ratio_str = f"{r['ratio']:.2f}x" if r['ratio'] is not None else "N/A"
        sig = "***" if r['p_value'] < 0.001 else "**" if r['p_value'] < 0.01 else "*" if r['p_value'] < 0.05 else ""
        print(f"{r['feature']:<30} {r['w_mean']:>10.2f} {r['l_mean']:>10.2f} {ratio_str:>8} {r['p_value']:>9.4f}{sig} {r['effect_size']:>7.3f}")

    # Find thresholds for significant features (p < 0.1)
    significant = [r for r in results if r.get("p_value", 1) < 0.1]

    print(f"\n{'='*80}")
    print(f"THRESHOLD CALIBRATION (significant features, p < 0.1)")
    print(f"{'='*80}")

    calibrated = []
    for r in significant:
        fname = r["feature"]
        thresh_info = find_best_threshold(fname, train)
        if thresh_info:
            # Validate on val set
            val_eval = evaluate_threshold(fname, val, thresh_info["threshold"], thresh_info["direction"])
            test_eval = evaluate_threshold(fname, test, thresh_info["threshold"], thresh_info["direction"])

            entry = {
                **r,
                **thresh_info,
                "val_metrics": val_eval,
                "test_metrics": test_eval,
            }
            calibrated.append(entry)

            print(f"\n  {fname}:")
            print(f"    Threshold: {thresh_info['direction']} {thresh_info['threshold']}")
            print(f"    Train F1: {thresh_info['train_f1']}")
            if val_eval:
                print(f"    Val   F1: {val_eval['f1']} (P={val_eval['precision']}, R={val_eval['recall']})")
            if test_eval:
                print(f"    Test  F1: {test_eval['f1']} (P={test_eval['precision']}, R={test_eval['recall']})")

    # Generate report
    report = generate_report(results, calibrated, train, val, test)
    with open(REPORT_FILE, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {REPORT_FILE}")

    # Save structured results
    output = {
        "dataset": {
            "total": len(features),
            "train": len(train),
            "val": len(val),
            "test": len(test),
            "categories": dict(cats),
        },
        "feature_analysis": results,
        "calibrated_thresholds": calibrated,
    }
    with open(DATA_DIR / "labeled" / "signal_analysis.json", "w") as f:
        json.dump(output, f, indent=2)


def generate_report(results, calibrated, train, val, test) -> str:
    """Generate markdown report."""
    lines = [
        "# Onchain Signal Discovery Report",
        "",
        "## Dataset",
        f"- Total tokens: {len(train) + len(val) + len(test)}",
        f"- Train: {len(train)} ({sum(1 for f in train if f['category']=='winner')}W / {sum(1 for f in train if f['category']=='loser')}L)",
        f"- Val: {len(val)} ({sum(1 for f in val if f['category']=='winner')}W / {sum(1 for f in val if f['category']=='loser')}L)",
        f"- Test: {len(test)} ({sum(1 for f in test if f['category']=='winner')}W / {sum(1 for f in test if f['category']=='loser')}L)",
        "",
        "## Feature Ranking (by p-value on training set)",
        "",
        "| Feature | W mean | L mean | Ratio | p-value | Effect |",
        "|---------|--------|--------|-------|---------|--------|",
    ]

    for r in results:
        ratio_str = f"{r['ratio']:.2f}x" if r['ratio'] is not None else "N/A"
        sig = " ***" if r['p_value'] < 0.001 else " **" if r['p_value'] < 0.01 else " *" if r['p_value'] < 0.05 else ""
        lines.append(f"| {r['feature']} | {r['w_mean']:.2f} | {r['l_mean']:.2f} | {ratio_str} | {r['p_value']:.4f}{sig} | {r['effect_size']:.3f} |")

    lines.extend([
        "",
        "## Calibrated Thresholds",
        "",
    ])

    for c in calibrated:
        fname = c["feature"]
        lines.extend([
            f"### {fname}",
            f"- Direction: {c['direction']} {c['threshold']}",
            f"- Train F1: {c['train_f1']}",
        ])
        if c.get("val_metrics"):
            vm = c["val_metrics"]
            lines.append(f"- Val: F1={vm['f1']}, P={vm['precision']}, R={vm['recall']}, Acc={vm['accuracy']}")
        if c.get("test_metrics"):
            tm = c["test_metrics"]
            lines.append(f"- Test: F1={tm['f1']}, P={tm['precision']}, R={tm['recall']}, Acc={tm['accuracy']}")
        lines.append("")

    lines.extend([
        "## Key Findings",
        "",
        "### Strongest Discriminators (p < 0.05)",
        "",
    ])

    strong = [r for r in results if r.get("p_value", 1) < 0.05]
    for r in strong:
        direction = "higher" if r["w_mean"] > r["l_mean"] else "lower"
        lines.append(f"- **{r['feature']}**: Winners {direction} ({r['w_mean']:.2f} vs {r['l_mean']:.2f}, p={r['p_value']:.4f})")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
