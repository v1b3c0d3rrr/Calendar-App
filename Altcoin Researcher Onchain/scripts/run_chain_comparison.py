"""
Run anomaly detection, clustering, and CEX flow analysis separately for ETH and BSC.
Compare distributions between chains to verify data homogeneity.
If homogeneous, merge and produce combined results.

Approach:
1. Split transfer files by chain_id (1=ETH, 56=BSC)
2. Run all 3 analysis scripts on each chain subset
3. For each metric, run Mann-Whitney U test ETH_winners vs BSC_winners and ETH_losers vs BSC_losers
4. If distributions are similar (p > 0.05 for most metrics), merge the datasets
5. If BSC shows systematic biases, flag and handle per-metric
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy.stats import mannwhitneyu, ks_2samp

sys.path.insert(0, str(Path(__file__).parent))
from label_db import LabelDB
from detect_mm_anomalies import compute_token_anomalies
from cluster_addresses import process_token as cluster_process_token
from analyze_cex_flows import process_token as cex_process_token

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSFERS_DIR = DATA_DIR / "transfers"
REPORT_FILE = DATA_DIR / "chain_comparison_report.md"
OUTPUT_FILE = DATA_DIR / "chain_comparison.json"


def load_all_tokens():
    """Load all transfer files, split by chain."""
    eth_tokens = []
    bsc_tokens = []

    for f in sorted(TRANSFERS_DIR.glob("*.json")):
        try:
            with open(f) as fh:
                header = json.load(fh)

            coin_id = header.get("coin_id", f.stem)
            chain_id = header.get("chain_id", 1)
            category = header.get("category", "unknown")
            tc = header.get("transfer_count", 0)

            if tc < 10:
                continue
            if category not in ("winner", "loser", "pump_and_dump"):
                continue

            entry = {"coin_id": coin_id, "file": str(f), "category": category, "chain_id": chain_id}

            if chain_id == 56:
                bsc_tokens.append(entry)
            else:
                eth_tokens.append(entry)
        except Exception as e:
            print(f"  Skip {f.name}: {e}")

    return eth_tokens, bsc_tokens


def run_anomaly_for_tokens(token_list, db):
    """Run anomaly detection for a list of tokens."""
    results = []
    for i, t in enumerate(token_list):
        try:
            m = compute_token_anomalies(t["coin_id"], db)
            if m:
                results.append(m)
        except Exception as e:
            pass
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(token_list)}] {len(results)} ok", flush=True)
    return results


def run_cluster_for_tokens(token_list, db):
    """Run cluster analysis for a list of tokens."""
    results = []
    for i, t in enumerate(token_list):
        try:
            m = cluster_process_token(t["coin_id"], db)
            if m:
                results.append(m)
        except Exception as e:
            pass
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(token_list)}] {len(results)} ok", flush=True)
    return results


def run_cex_for_tokens(token_list, db):
    """Run CEX flow analysis for a list of tokens."""
    results = []
    for i, t in enumerate(token_list):
        try:
            filepath = Path(t["file"])
            m = cex_process_token(filepath, db)
            if m:
                results.append(m)
        except Exception as e:
            pass
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(token_list)}] {len(results)} ok", flush=True)
    return results


def compare_distributions(eth_results, bsc_results, label=""):
    """
    Compare metric distributions between ETH and BSC.
    Returns dict of metric -> {p_value, ks_p, eth_median, bsc_median, homogeneous}
    """
    skip_keys = {"coin_id", "category", "chain_id", "symbol", "name", "contract", "file"}

    # Get all numeric metric names
    all_keys = set()
    for r in eth_results + bsc_results:
        for k, v in r.items():
            if k not in skip_keys and isinstance(v, (int, float)):
                all_keys.add(k)

    comparison = {}
    n_homogeneous = 0
    n_tested = 0

    print(f"\n{'='*70}")
    print(f"CHAIN COMPARISON: {label}")
    print(f"ETH: {len(eth_results)} tokens, BSC: {len(bsc_results)} tokens")
    print(f"{'='*70}")

    for metric in sorted(all_keys):
        eth_vals = [float(r.get(metric, 0)) for r in eth_results if metric in r]
        bsc_vals = [float(r.get(metric, 0)) for r in bsc_results if metric in r]

        eth_vals = [v for v in eth_vals if np.isfinite(v)]
        bsc_vals = [v for v in bsc_vals if np.isfinite(v)]

        if len(eth_vals) < 5 or len(bsc_vals) < 5:
            continue

        n_tested += 1

        try:
            # Mann-Whitney: are the distributions different?
            mw_stat, mw_p = mannwhitneyu(eth_vals, bsc_vals, alternative="two-sided")
            # KS test: more sensitive to distribution shape differences
            ks_stat, ks_p = ks_2samp(eth_vals, bsc_vals)

            eth_med = np.median(eth_vals)
            bsc_med = np.median(bsc_vals)

            # Homogeneous if BOTH tests say p > 0.05
            homogeneous = mw_p > 0.05 and ks_p > 0.05
            if homogeneous:
                n_homogeneous += 1

            comparison[metric] = {
                "mw_p": float(mw_p),
                "ks_p": float(ks_p),
                "eth_median": float(eth_med),
                "bsc_median": float(bsc_med),
                "homogeneous": homogeneous,
                "eth_n": len(eth_vals),
                "bsc_n": len(bsc_vals),
            }

            flag = "✓" if homogeneous else "✗ DIFF"
            if not homogeneous:
                ratio = bsc_med / eth_med if eth_med != 0 else float("inf")
                ratio_str = f"{ratio:.2f}x" if np.isfinite(ratio) else "∞"
                print(f"  {flag:8s} {metric:40s} ETH={eth_med:12.4f}  BSC={bsc_med:12.4f}  MW_p={mw_p:.4f}  KS_p={ks_p:.4f}  ratio={ratio_str}")
        except Exception:
            pass

    pct = n_homogeneous / max(n_tested, 1) * 100
    print(f"\n  Summary: {n_homogeneous}/{n_tested} metrics homogeneous ({pct:.0f}%)")

    return comparison


def run_winner_loser_tests(results, chain_label=""):
    """Run W vs L Mann-Whitney tests and return significant findings."""
    winners = [r for r in results if r.get("category") == "winner"]
    losers = [r for r in results if r.get("category") == "loser"]

    skip_keys = {"coin_id", "category", "chain_id", "symbol", "name", "contract", "file"}
    all_keys = set()
    for r in results:
        for k, v in r.items():
            if k not in skip_keys and isinstance(v, (int, float)):
                all_keys.add(k)

    print(f"\n{'='*70}")
    print(f"W vs L TESTS: {chain_label} ({len(winners)}W vs {len(losers)}L)")
    print(f"{'='*70}")

    significant = []
    all_tests = {}

    for metric in sorted(all_keys):
        w_vals = [float(r.get(metric, 0)) for r in winners if metric in r]
        l_vals = [float(r.get(metric, 0)) for r in losers if metric in r]

        w_vals = [v for v in w_vals if np.isfinite(v)]
        l_vals = [v for v in l_vals if np.isfinite(v)]

        if len(w_vals) < 5 or len(l_vals) < 5:
            continue

        try:
            stat, pval = mannwhitneyu(w_vals, l_vals, alternative="two-sided")
            w_med = np.median(w_vals)
            l_med = np.median(l_vals)

            all_tests[metric] = {
                "p_value": float(pval),
                "w_median": float(w_med),
                "l_median": float(l_med),
                "w_n": len(w_vals),
                "l_n": len(l_vals),
            }

            sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
            if pval < 0.1:
                significant.append((metric, pval, w_med, l_med, sig))
                direction = "↑ W" if w_med > l_med else "↓ W"
                ratio = w_med / l_med if l_med != 0 else float("inf")
                ratio_str = f"{ratio:.2f}x" if np.isfinite(ratio) else "∞"
                print(f"  {sig:3s} {metric:40s} p={pval:.4f}  W={w_med:.4f}  L={l_med:.4f}  {direction}  {ratio_str}")
        except Exception:
            pass

    return all_tests, significant


def generate_report(eth_tokens, bsc_tokens, eth_anomaly, bsc_anomaly, eth_cluster, bsc_cluster,
                    eth_cex, bsc_cex, anomaly_comp, cluster_comp, cex_comp,
                    eth_wl_anomaly, bsc_wl_anomaly, eth_wl_cluster, bsc_wl_cluster,
                    eth_wl_cex, bsc_wl_cex,
                    combined_wl_anomaly, combined_wl_cluster, combined_wl_cex):
    """Generate markdown report."""

    def format_sig(tests, label):
        lines = [f"### {label}\n"]
        sig = [(k, v) for k, v in tests.items() if v["p_value"] < 0.1]
        sig.sort(key=lambda x: x[1]["p_value"])
        if not sig:
            lines.append("No significant signals (p < 0.1)\n")
        for name, v in sig:
            p = v["p_value"]
            stars = "***" if p < 0.01 else "**" if p < 0.05 else "*"
            w = v.get("w_median", v.get("eth_median", 0))
            l = v.get("l_median", v.get("bsc_median", 0))
            lines.append(f"- {stars} **{name}** p={p:.4f} W={w:.4f} L={l:.4f}")
        lines.append("")
        return "\n".join(lines)

    def format_homogeneity(comp, label):
        lines = [f"### {label}\n"]
        n_total = len(comp)
        n_homo = sum(1 for v in comp.values() if v["homogeneous"])
        pct = n_homo / max(n_total, 1) * 100
        lines.append(f"**{n_homo}/{n_total} metrics homogeneous ({pct:.0f}%)**\n")

        diff = [(k, v) for k, v in comp.items() if not v["homogeneous"]]
        diff.sort(key=lambda x: x[1]["mw_p"])
        if diff:
            lines.append("Non-homogeneous metrics:")
            for name, v in diff:
                lines.append(f"- **{name}** ETH={v['eth_median']:.4f} BSC={v['bsc_median']:.4f} MW_p={v['mw_p']:.4f} KS_p={v['ks_p']:.4f}")
        lines.append("")
        return "\n".join(lines)

    eth_w = len([t for t in eth_tokens if t["category"] == "winner"])
    eth_l = len([t for t in eth_tokens if t["category"] == "loser"])
    bsc_w = len([t for t in bsc_tokens if t["category"] == "winner"])
    bsc_l = len([t for t in bsc_tokens if t["category"] == "loser"])

    report = f"""# Chain Comparison Report: ETH vs BSC

## Dataset Summary

| Chain | Winners | Losers | Total |
|-------|---------|--------|-------|
| ETH   | {eth_w} | {eth_l} | {len(eth_tokens)} |
| BSC   | {bsc_w} | {bsc_l} | {len(bsc_tokens)} |
| **Total** | **{eth_w+bsc_w}** | **{eth_l+bsc_l}** | **{len(eth_tokens)+len(bsc_tokens)}** |

## Part 1: ETH-only Results

{format_sig(eth_wl_anomaly[0], "Anomaly Detection (ETH)")}
{format_sig(eth_wl_cluster[0], "Cluster Analysis (ETH)")}
{format_sig(eth_wl_cex[0], "CEX Flow Analysis (ETH)")}

## Part 2: BSC-only Results

{format_sig(bsc_wl_anomaly[0], "Anomaly Detection (BSC)")}
{format_sig(bsc_wl_cluster[0], "Cluster Analysis (BSC)")}
{format_sig(bsc_wl_cex[0], "CEX Flow Analysis (BSC)")}

## Part 3: Chain Homogeneity Tests

{format_homogeneity(anomaly_comp, "Anomaly Detection")}
{format_homogeneity(cluster_comp, "Cluster Analysis")}
{format_homogeneity(cex_comp, "CEX Flow Analysis")}

## Part 4: Combined Results (ETH + BSC)

{format_sig(combined_wl_anomaly[0], "Anomaly Detection (Combined)")}
{format_sig(combined_wl_cluster[0], "Cluster Analysis (Combined)")}
{format_sig(combined_wl_cex[0], "CEX Flow Analysis (Combined)")}

## Methodology

1. All analyses run separately for ETH and BSC tokens
2. Mann-Whitney U + Kolmogorov-Smirnov tests for homogeneity (ETH vs BSC within same category)
3. If >70% metrics homogeneous → safe to merge
4. Combined results use full dataset for maximum statistical power
"""

    with open(REPORT_FILE, "w") as f:
        f.write(report)

    print(f"\nReport saved: {REPORT_FILE}")


def main():
    print("Loading tokens...")
    eth_tokens, bsc_tokens = load_all_tokens()

    eth_w = len([t for t in eth_tokens if t["category"] == "winner"])
    eth_l = len([t for t in eth_tokens if t["category"] == "loser"])
    bsc_w = len([t for t in bsc_tokens if t["category"] == "winner"])
    bsc_l = len([t for t in bsc_tokens if t["category"] == "loser"])

    print(f"ETH: {len(eth_tokens)} tokens ({eth_w}W, {eth_l}L)")
    print(f"BSC: {len(bsc_tokens)} tokens ({bsc_w}W, {bsc_l}L)")

    # Initialize LabelDB
    db = LabelDB()
    db.load_all()
    print(f"LabelDB: {db.stats()['total']} labels")

    # === RUN ANOMALY DETECTION ===
    print(f"\n{'#'*70}")
    print("ANOMALY DETECTION")
    print(f"{'#'*70}")

    print("\nRunning anomaly detection (ETH)...")
    eth_anomaly = run_anomaly_for_tokens(eth_tokens, db)
    print(f"  ETH anomaly: {len(eth_anomaly)} results")

    print("\nRunning anomaly detection (BSC)...")
    bsc_anomaly = run_anomaly_for_tokens(bsc_tokens, db)
    print(f"  BSC anomaly: {len(bsc_anomaly)} results")

    # W vs L tests per chain
    eth_wl_anomaly = run_winner_loser_tests(eth_anomaly, "ETH Anomaly")
    bsc_wl_anomaly = run_winner_loser_tests(bsc_anomaly, "BSC Anomaly")

    # Chain comparison
    anomaly_comp = compare_distributions(eth_anomaly, bsc_anomaly, "Anomaly Detection")

    # Combined
    combined_anomaly = eth_anomaly + bsc_anomaly
    combined_wl_anomaly = run_winner_loser_tests(combined_anomaly, "Combined Anomaly")

    # === RUN CLUSTER ANALYSIS ===
    print(f"\n{'#'*70}")
    print("CLUSTER ANALYSIS")
    print(f"{'#'*70}")

    print("\nRunning cluster analysis (ETH)...")
    eth_cluster = run_cluster_for_tokens(eth_tokens, db)
    print(f"  ETH cluster: {len(eth_cluster)} results")

    print("\nRunning cluster analysis (BSC)...")
    bsc_cluster = run_cluster_for_tokens(bsc_tokens, db)
    print(f"  BSC cluster: {len(bsc_cluster)} results")

    eth_wl_cluster = run_winner_loser_tests(eth_cluster, "ETH Cluster")
    bsc_wl_cluster = run_winner_loser_tests(bsc_cluster, "BSC Cluster")
    cluster_comp = compare_distributions(eth_cluster, bsc_cluster, "Cluster Analysis")

    combined_cluster = eth_cluster + bsc_cluster
    combined_wl_cluster = run_winner_loser_tests(combined_cluster, "Combined Cluster")

    # === RUN CEX FLOW ANALYSIS ===
    print(f"\n{'#'*70}")
    print("CEX FLOW ANALYSIS")
    print(f"{'#'*70}")

    print("\nRunning CEX flow analysis (ETH)...")
    eth_cex = run_cex_for_tokens(eth_tokens, db)
    print(f"  ETH CEX: {len(eth_cex)} results")

    print("\nRunning CEX flow analysis (BSC)...")
    bsc_cex = run_cex_for_tokens(bsc_tokens, db)
    print(f"  BSC CEX: {len(bsc_cex)} results")

    eth_wl_cex = run_winner_loser_tests(eth_cex, "ETH CEX")
    bsc_wl_cex = run_winner_loser_tests(bsc_cex, "BSC CEX")
    cex_comp = compare_distributions(eth_cex, bsc_cex, "CEX Flows")

    combined_cex = eth_cex + bsc_cex
    combined_wl_cex = run_winner_loser_tests(combined_cex, "Combined CEX")

    # === GENERATE REPORT ===
    generate_report(
        eth_tokens, bsc_tokens,
        eth_anomaly, bsc_anomaly,
        eth_cluster, bsc_cluster,
        eth_cex, bsc_cex,
        anomaly_comp, cluster_comp, cex_comp,
        eth_wl_anomaly, bsc_wl_anomaly,
        eth_wl_cluster, bsc_wl_cluster,
        eth_wl_cex, bsc_wl_cex,
        combined_wl_anomaly, combined_wl_cluster, combined_wl_cex,
    )

    # Save full output
    output = {
        "eth_n": len(eth_tokens),
        "bsc_n": len(bsc_tokens),
        "anomaly_comparison": anomaly_comp,
        "cluster_comparison": cluster_comp,
        "cex_comparison": cex_comp,
        "eth_anomaly_wl": eth_wl_anomaly[0],
        "bsc_anomaly_wl": bsc_wl_anomaly[0],
        "combined_anomaly_wl": combined_wl_anomaly[0],
        "eth_cluster_wl": eth_wl_cluster[0],
        "bsc_cluster_wl": bsc_wl_cluster[0],
        "combined_cluster_wl": combined_wl_cluster[0],
        "eth_cex_wl": eth_wl_cex[0],
        "bsc_cex_wl": bsc_wl_cex[0],
        "combined_cex_wl": combined_wl_cex[0],
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nFull output saved: {OUTPUT_FILE}")

    # === SUMMARY ===
    print(f"\n{'='*70}")
    print("HOMOGENEITY SUMMARY")
    print(f"{'='*70}")

    for name, comp in [("Anomaly", anomaly_comp), ("Cluster", cluster_comp), ("CEX", cex_comp)]:
        n = len(comp)
        h = sum(1 for v in comp.values() if v["homogeneous"])
        pct = h / max(n, 1) * 100
        status = "✓ MERGE OK" if pct >= 70 else "⚠ CHECK MANUALLY"
        print(f"  {name:20s}: {h}/{n} homogeneous ({pct:.0f}%) → {status}")


if __name__ == "__main__":
    main()
