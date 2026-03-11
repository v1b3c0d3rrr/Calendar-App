"""
Analyze holder dynamics from snapshots — compare winners vs losers.

Two analysis windows:
1. LAGGING: T-7 → T (T = peak/bottom) — during price movement, NOT predictive
2. LEADING: S-7 → S (S = start_date) — BEFORE price movement, predictive signal

Only LEADING metrics are actionable for trading.

Loads all snapshot files from data/snapshots/ and computes metrics for both windows.
"""

import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
CALIBRATION_DIR = Path(__file__).parent.parent.parent / "Alt Boss" / "calibration"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
REPORT_FILE = DATA_DIR / "holder_dynamics_report.md"


def load_start_dates() -> dict:
    """Load start_date for each token from candidates_clean.json."""
    with open(CALIBRATION_DIR / "candidates_clean.json") as f:
        cands = json.load(f)

    dates = {}
    for group in ["pure_winners", "pump_and_dump", "losers"]:
        for t in cands.get(group, []):
            dates[t["coin_id"]] = t["start_date"]
    return dates


def load_all_snapshots() -> list[dict]:
    """Load all snapshot files."""
    results = []
    for f in sorted(SNAPSHOTS_DIR.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
        results.append(data)
    return results


def compute_dynamics(token_data: dict, start_dates: dict) -> Optional[dict]:
    """Compute dynamic metrics from a token's snapshots.

    Two windows:
    - LAGGING: T-7 → T (during movement, NOT predictive)
    - LEADING: S-7 → S (before movement, predictive)
    Where S = start_date, T = event_date (peak/bottom)
    """
    snapshots = token_data.get("snapshots", [])
    if len(snapshots) < 3:
        return None

    # Filter snapshots with data
    valid = [s for s in snapshots if s.get("total_holders", 0) > 0]
    if len(valid) < 3:
        return None

    # Time span
    first_ts = valid[0]["timestamp"]
    last_ts = valid[-1]["timestamp"]
    span_days = (last_ts - first_ts) / 86400

    if span_days < 1:
        return None

    # === Holder growth ===
    first_holders = valid[0]["total_holders"]
    last_holders = valid[-1]["total_holders"]
    holder_growth_total = (last_holders - first_holders) / max(first_holders, 1)
    holder_growth_daily = holder_growth_total / max(span_days, 1)

    # === LAGGING window: T-7 → T (during price movement) ===
    event_ts = last_ts
    t_minus_7 = event_ts - 7 * 86400
    t_minus_14 = event_ts - 14 * 86400

    snaps_14d = [s for s in valid if s["timestamp"] >= t_minus_14]
    snaps_7d = [s for s in valid if s["timestamp"] >= t_minus_7]
    snaps_baseline = [s for s in valid if t_minus_14 <= s["timestamp"] < t_minus_7]

    # === LEADING window: S-7 → S (BEFORE price movement) ===
    coin_id = token_data["coin_id"]
    start_date_str = start_dates.get(coin_id)
    start_ts = None
    if start_date_str:
        start_ts = int(datetime.strptime(start_date_str, "%Y-%m-%d").timestamp())

    s_minus_7 = start_ts - 7 * 86400 if start_ts else None
    s_minus_14 = start_ts - 14 * 86400 if start_ts else None

    # Leading snapshots: week before start
    snaps_pre_start_7d = []
    snaps_pre_start_baseline = []
    if start_ts and s_minus_7:
        snaps_pre_start_7d = [s for s in valid if s_minus_7 <= s["timestamp"] < start_ts]
        snaps_pre_start_baseline = [s for s in valid if s_minus_14 <= s["timestamp"] < s_minus_7]

    def avg_metric(snaps, key):
        vals = [s.get(key, 0) for s in snaps if key in s]
        return sum(vals) / len(vals) if vals else 0

    def delta_metric(snaps, key):
        """Change from first to last snapshot in a period."""
        vals = [s for s in snaps if key in s and s.get(key) is not None]
        if len(vals) < 2:
            return 0
        return vals[-1][key] - vals[0][key]

    def total_metric(snaps, key):
        return sum(s.get(key, 0) for s in snaps)

    # ================================================================
    # LAGGING metrics (T-7 → T) — during price movement, NOT actionable
    # ================================================================
    gini_delta_7d = delta_metric(snaps_7d, "gini")
    top10_delta_7d = delta_metric(snaps_7d, "top10_pct")

    new_holders_7d = total_metric(snaps_7d, "new_holders")
    exited_holders_7d = total_metric(snaps_7d, "exited_holders")
    net_holders_7d = new_holders_7d - exited_holders_7d
    churn_rate_7d = exited_holders_7d / max(new_holders_7d, 1)

    whale_delta_7d = delta_metric(snaps_7d, "whale_count")

    vol_7d = total_metric(snaps_7d, "volume_in_period")
    vol_baseline = total_metric(snaps_baseline, "volume_in_period")
    transfers_7d = total_metric(snaps_7d, "transfers_in_period")
    transfers_baseline = total_metric(snaps_baseline, "transfers_in_period")

    # ================================================================
    # LEADING metrics (S-7 → S) — BEFORE price movement, ACTIONABLE
    # ================================================================
    lead_new_holders = 0
    lead_exited_holders = 0
    lead_net_holders = 0
    lead_churn_rate = 0
    lead_gini_delta = 0
    lead_top10_delta = 0
    lead_whale_delta = 0
    lead_transfers = 0
    lead_volume = 0
    lead_has_data = False

    # Leading baseline: S-14 → S-7
    lead_bl_new_holders = 0
    lead_bl_transfers = 0
    lead_bl_volume = 0
    lead_new_holder_accel = 0
    lead_transfer_accel = 0
    lead_vol_accel = 0

    # Holder count at S (start of movement)
    lead_holders_at_s = 0

    # Size-bucketed leading metrics
    size_buckets = ["dust", "tiny", "small", "medium", "large", "whale"]
    lead_new_by_size = {b: 0 for b in size_buckets}
    lead_exit_by_size = {b: 0 for b in size_buckets}

    if snaps_pre_start_7d:
        lead_has_data = True
        lead_new_holders = total_metric(snaps_pre_start_7d, "new_holders")
        lead_exited_holders = total_metric(snaps_pre_start_7d, "exited_holders")
        lead_net_holders = lead_new_holders - lead_exited_holders
        lead_churn_rate = lead_exited_holders / max(lead_new_holders, 1)
        lead_gini_delta = delta_metric(snaps_pre_start_7d, "gini")
        lead_top10_delta = delta_metric(snaps_pre_start_7d, "top10_pct")
        lead_whale_delta = delta_metric(snaps_pre_start_7d, "whale_count")
        lead_transfers = total_metric(snaps_pre_start_7d, "transfers_in_period")
        lead_volume = total_metric(snaps_pre_start_7d, "volume_in_period")

        # Holders at S
        last_pre_snap = snaps_pre_start_7d[-1]
        lead_holders_at_s = last_pre_snap.get("total_holders", 0)

        # Aggregate size-bucketed new/exited across S-7→S snapshots
        for s in snaps_pre_start_7d:
            new_sz = s.get("new_by_size", {})
            exit_sz = s.get("exit_by_size", {})
            for b in size_buckets:
                lead_new_by_size[b] += new_sz.get(b, 0)
                lead_exit_by_size[b] += exit_sz.get(b, 0)

        # Baseline for acceleration
        if snaps_pre_start_baseline:
            lead_bl_new_holders = total_metric(snaps_pre_start_baseline, "new_holders")
            lead_bl_transfers = total_metric(snaps_pre_start_baseline, "transfers_in_period")
            lead_bl_volume = total_metric(snaps_pre_start_baseline, "volume_in_period")

            n_pre = len(snaps_pre_start_7d)
            n_bl = len(snaps_pre_start_baseline)

            lead_new_holder_accel = (
                (lead_new_holders / max(n_pre, 1)) /
                max(lead_bl_new_holders / max(n_bl, 1), 0.01)
            )
            lead_transfer_accel = (
                (lead_transfers / max(n_pre, 1)) /
                max(lead_bl_transfers / max(n_bl, 1), 0.01)
            )
            lead_vol_accel = (
                (lead_volume / max(n_pre, 1)) /
                max(lead_bl_volume / max(n_bl, 1), 0.01)
            )

    return {
        "coin_id": token_data["coin_id"],
        "symbol": token_data["symbol"],
        "category": token_data["category"],
        "multiplier": token_data.get("multiplier"),
        "start_mc": token_data.get("start_mc"),
        "chain_name": token_data.get("chain_name"),
        "total_transfers": token_data.get("total_transfers", 0),
        "span_days": round(span_days, 1),
        "snapshot_count": len(valid),

        # General
        "first_holders": first_holders,
        "last_holders": last_holders,
        "holder_growth_daily": round(holder_growth_daily, 4),

        # LAGGING (T-7→T) — marked with lag_ prefix
        "lag_net_holders_7d": net_holders_7d,
        "lag_churn_rate_7d": round(churn_rate_7d, 4),
        "lag_new_holders_7d": new_holders_7d,
        "lag_gini_delta_7d": round(gini_delta_7d, 6),
        "lag_top10_delta_7d": round(top10_delta_7d, 6),
        "lag_whale_delta_7d": whale_delta_7d,

        # LEADING (S-7→S) — the actionable metrics
        "lead_has_data": lead_has_data,
        "lead_holders_at_s": lead_holders_at_s,
        "lead_new_holders": lead_new_holders,
        "lead_exited_holders": lead_exited_holders,
        "lead_net_holders": lead_net_holders,
        "lead_churn_rate": round(lead_churn_rate, 4),
        "lead_gini_delta": round(lead_gini_delta, 6),
        "lead_top10_delta": round(lead_top10_delta, 6),
        "lead_whale_delta": lead_whale_delta,
        "lead_transfers": lead_transfers,
        "lead_volume": lead_volume,
        "lead_new_holder_accel": round(lead_new_holder_accel, 4),
        "lead_transfer_accel": round(lead_transfer_accel, 4),
        "lead_vol_accel": round(lead_vol_accel, 4),

        # Size-bucketed leading (S-7→S)
        # New holders by size
        "lead_new_dust": lead_new_by_size.get("dust", 0),
        "lead_new_tiny": lead_new_by_size.get("tiny", 0),
        "lead_new_small": lead_new_by_size.get("small", 0),
        "lead_new_medium": lead_new_by_size.get("medium", 0),
        "lead_new_large": lead_new_by_size.get("large", 0),
        "lead_new_whale": lead_new_by_size.get("whale", 0),
        # Exited holders by size (their balance BEFORE exiting)
        "lead_exit_dust": lead_exit_by_size.get("dust", 0),
        "lead_exit_tiny": lead_exit_by_size.get("tiny", 0),
        "lead_exit_small": lead_exit_by_size.get("small", 0),
        "lead_exit_medium": lead_exit_by_size.get("medium", 0),
        "lead_exit_large": lead_exit_by_size.get("large", 0),
        "lead_exit_whale": lead_exit_by_size.get("whale", 0),

        # Concentration at S
        "gini_last": valid[-1].get("gini", 0),
        "top10_last": valid[-1].get("top10_pct", 0),
        "whale_count_last": valid[-1].get("whale_count", 0),
    }


def mann_whitney_u(group_a: list, group_b: list) -> tuple:
    """Simple Mann-Whitney U test. Returns (U, p-value approximation)."""
    if len(group_a) < 5 or len(group_b) < 5:
        return (0, 1.0)

    na, nb = len(group_a), len(group_b)
    combined = [(v, "a") for v in group_a] + [(v, "b") for v in group_b]
    combined.sort(key=lambda x: x[0])

    # Assign ranks (handle ties with average rank)
    ranks = {}
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2  # 1-indexed
        for k in range(i, j):
            if k not in ranks:
                ranks[k] = []
            ranks[k] = avg_rank
        i = j

    rank_sum_a = sum(ranks[i] for i in range(len(combined)) if combined[i][1] == "a")
    u_a = rank_sum_a - na * (na + 1) / 2
    u_b = na * nb - u_a
    u = min(u_a, u_b)

    # Normal approximation for p-value
    mu = na * nb / 2
    sigma = math.sqrt(na * nb * (na + nb + 1) / 12)
    if sigma == 0:
        return (u, 1.0)
    z = (u - mu) / sigma
    # Two-tailed p-value approximation
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return (round(u, 2), round(p, 6))


def generate_report(dynamics: list[dict]):
    """Generate statistical comparison report with LEADING and LAGGING sections."""
    winners = [d for d in dynamics if d["category"] == "winner"]
    losers = [d for d in dynamics if d["category"] == "loser"]

    # Only tokens with leading data
    lead_winners = [d for d in winners if d.get("lead_has_data")]
    lead_losers = [d for d in losers if d.get("lead_has_data")]

    def median(vals):
        if not vals:
            return 0
        s = sorted(vals)
        n = len(s)
        return s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2

    lines = [
        "# Holder Dynamics Analysis Report",
        "",
        f"**Total tokens**: {len(dynamics)} (winners: {len(winners)}, losers: {len(losers)})",
        f"**With leading data (S-7→S)**: {len(lead_winners)}W + {len(lead_losers)}L",
        "",
        "## LEADING Metrics (S-7 → S) — BEFORE price movement",
        "",
        "These are actionable: measured in the week BEFORE the token starts moving.",
        "S = start_date = moment price begins rising (winners) or falling (losers).",
        "",
        "| Metric | Winners (med) | Losers (med) | P-value | Signal |",
        "|--------|:---:|:---:|:---:|:---:|",
    ]

    leading_metrics = [
        ("lead_net_holders", "Net holders S-7→S"),
        ("lead_new_holders", "New holders S-7→S"),
        ("lead_exited_holders", "Exited holders S-7→S"),
        ("lead_churn_rate", "Churn rate S-7→S"),
        ("lead_gini_delta", "Gini change S-7→S"),
        ("lead_top10_delta", "Top10% change S-7→S"),
        ("lead_whale_delta", "Whale change S-7→S"),
        ("lead_transfers", "Transfers S-7→S"),
        ("lead_volume", "Volume S-7→S"),
        ("lead_new_holder_accel", "New holder accel (vs S-14→S-7)"),
        ("lead_transfer_accel", "Transfer accel (vs S-14→S-7)"),
        ("lead_vol_accel", "Volume accel (vs S-14→S-7)"),
        ("lead_holders_at_s", "Total holders at S"),
    ]

    # Size-bucketed metrics
    size_metrics = [
        ("lead_new_dust", "New dust (<0.001%) S-7→S"),
        ("lead_new_tiny", "New tiny (0.001-0.01%) S-7→S"),
        ("lead_new_small", "New small (0.01-0.1%) S-7→S"),
        ("lead_new_medium", "New medium (0.1-1%) S-7→S"),
        ("lead_new_large", "New large (1-5%) S-7→S"),
        ("lead_new_whale", "New whale (>5%) S-7→S"),
        ("lead_exit_dust", "Exit dust (<0.001%) S-7→S"),
        ("lead_exit_tiny", "Exit tiny (0.001-0.01%) S-7→S"),
        ("lead_exit_small", "Exit small (0.01-0.1%) S-7→S"),
        ("lead_exit_medium", "Exit medium (0.1-1%) S-7→S"),
        ("lead_exit_large", "Exit large (1-5%) S-7→S"),
        ("lead_exit_whale", "Exit whale (>5%) S-7→S"),
    ]

    for key, label in leading_metrics:
        w_vals = [d[key] for d in lead_winners if d.get(key) is not None]
        l_vals = [d[key] for d in lead_losers if d.get(key) is not None]
        w_med = median(w_vals)
        l_med = median(l_vals)
        _, p = mann_whitney_u(w_vals, l_vals)
        sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else "-"
        lines.append(f"| {label} | {w_med:.4f} | {l_med:.4f} | {p:.4f} | {sig} |")

    # Size-bucketed section
    lines.extend([
        "",
        "## Size-Bucketed Holders (S-7 → S) — WHO enters/exits before movement?",
        "",
        "Size relative to supply: dust <0.001%, tiny 0.001-0.01%, small 0.01-0.1%, "
        "medium 0.1-1%, large 1-5%, whale >5%",
        "",
        "| Metric | Winners (med) | Losers (med) | P-value | Signal |",
        "|--------|:---:|:---:|:---:|:---:|",
    ])

    for key, label in size_metrics:
        w_vals = [d[key] for d in lead_winners if d.get(key) is not None]
        l_vals = [d[key] for d in lead_losers if d.get(key) is not None]
        w_med = median(w_vals)
        l_med = median(l_vals)
        _, p = mann_whitney_u(w_vals, l_vals)
        sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else "-"
        lines.append(f"| {label} | {w_med:.1f} | {l_med:.1f} | {p:.4f} | {sig} |")

    # LAGGING section
    lines.extend([
        "",
        "## LAGGING Metrics (T-7 → T) — DURING price movement (NOT actionable)",
        "",
        "These reflect holder behavior DURING the pump/dump. Informative but NOT predictive.",
        "",
        "| Metric | Winners (med) | Losers (med) | P-value | Signal |",
        "|--------|:---:|:---:|:---:|:---:|",
    ])

    lagging_metrics = [
        ("lag_net_holders_7d", "Net holders T-7→T"),
        ("lag_new_holders_7d", "New holders T-7→T"),
        ("lag_churn_rate_7d", "Churn rate T-7→T"),
        ("lag_gini_delta_7d", "Gini change T-7→T"),
        ("lag_whale_delta_7d", "Whale change T-7→T"),
    ]

    for key, label in lagging_metrics:
        w_vals = [d[key] for d in winners if d.get(key) is not None]
        l_vals = [d[key] for d in losers if d.get(key) is not None]
        w_med = median(w_vals)
        l_med = median(l_vals)
        _, p = mann_whitney_u(w_vals, l_vals)
        sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else "-"
        lines.append(f"| {label} | {w_med:.4f} | {l_med:.4f} | {p:.4f} | {sig} |")

    # Summary
    lines.extend([
        "",
        "## Key Findings",
        "",
        "### Actionable LEADING signals (p < 0.05, S-7→S window):",
    ])

    found_leading = False
    for key, label in leading_metrics:
        w_vals = [d[key] for d in lead_winners if d.get(key) is not None]
        l_vals = [d[key] for d in lead_losers if d.get(key) is not None]
        _, p = mann_whitney_u(w_vals, l_vals)
        if p < 0.05:
            found_leading = True
            w_med = median(w_vals)
            l_med = median(l_vals)
            ratio = w_med / l_med if l_med != 0 else float('inf')
            lines.append(f"- **{label}**: W={w_med:.4f} vs L={l_med:.4f} (ratio {ratio:.2f}x, p={p:.4f})")

    if not found_leading:
        # Check p < 0.1
        for key, label in leading_metrics:
            w_vals = [d[key] for d in lead_winners if d.get(key) is not None]
            l_vals = [d[key] for d in lead_losers if d.get(key) is not None]
            _, p = mann_whitney_u(w_vals, l_vals)
            if p < 0.1:
                w_med = median(w_vals)
                l_med = median(l_vals)
                lines.append(f"- *{label}*: W={w_med:.4f} vs L={l_med:.4f} (p={p:.4f}, marginal)")

        if not any(p < 0.1 for key, _ in leading_metrics
                   for p in [mann_whitney_u(
                       [d[key] for d in lead_winners if d.get(key) is not None],
                       [d[key] for d in lead_losers if d.get(key) is not None]
                   )[1]]):
            lines.append("- None found at current sample size")

    # Save dynamics data
    dynamics_file = DATA_DIR / "holder_dynamics.json"
    with open(dynamics_file, "w") as f:
        json.dump(dynamics, f, indent=2)
    lines.extend([
        "",
        "---",
        f"Raw data: `data/holder_dynamics.json` ({len(dynamics)} tokens)",
    ])

    report = "\n".join(lines)
    with open(REPORT_FILE, "w") as f:
        f.write(report)

    return report


def main():
    print("Loading snapshots...")
    all_data = load_all_snapshots()
    print(f"Loaded {len(all_data)} token snapshot files")

    print("Loading start dates...")
    start_dates = load_start_dates()
    print(f"Start dates for {len(start_dates)} tokens")

    print("Computing dynamics...")
    dynamics = []
    no_lead = 0
    for token_data in all_data:
        d = compute_dynamics(token_data, start_dates)
        if d:
            dynamics.append(d)
            if not d.get("lead_has_data"):
                no_lead += 1
        else:
            print(f"  Skip {token_data['coin_id']}: insufficient data")

    print(f"Computed dynamics for {len(dynamics)} tokens ({no_lead} without leading data)")

    if not dynamics:
        print("No data to analyze. Run collect_holder_snapshots.py first.")
        return

    report = generate_report(dynamics)
    print(f"\n{report}")
    print(f"\nReport saved to {REPORT_FILE}")


if __name__ == "__main__":
    main()
