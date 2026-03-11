#!/usr/bin/env python3
"""
Live Progress Dashboard — обновляется каждые 60 секунд.
Показывает реальное состояние всех фаз и ETA.

Запуск: python scripts/progress_dashboard.py
Выход: Ctrl+C
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

# History for ETA calculation
_history: dict[str, list[tuple[float, int]]] = {}


def track(key: str, value: int) -> str:
    """Track a metric over time and estimate ETA."""
    now = time.time()
    if key not in _history:
        _history[key] = []
    _history[key].append((now, value))
    # Keep last 30 data points
    _history[key] = _history[key][-30:]
    return ""


def estimate_eta(key: str, target: int) -> str:
    """Estimate time remaining based on observed rate of change."""
    pts = _history.get(key, [])
    if len(pts) < 2:
        return "calculating..."

    # Use oldest and newest points for rate
    t0, v0 = pts[0]
    t1, v1 = pts[-1]
    dt = t1 - t0
    dv = v1 - v0

    if dt < 1 or dv <= 0:
        return "—"

    rate = dv / dt  # items per second
    remaining = target - v1
    if remaining <= 0:
        return "DONE"

    eta_sec = remaining / rate
    if eta_sec > 86400:
        return f"~{eta_sec/3600:.0f}h"
    elif eta_sec > 3600:
        h = int(eta_sec // 3600)
        m = int((eta_sec % 3600) // 60)
        return f"~{h}h {m}m"
    elif eta_sec > 60:
        return f"~{eta_sec/60:.0f}m"
    else:
        return f"~{eta_sec:.0f}s"


def bar(done: int, total: int, width: int = 40) -> str:
    """Render a progress bar."""
    if total == 0:
        return f"[{'░' * width}]   0%"
    pct = done / total
    filled = int(width * pct)
    empty = width - filled
    pct_str = f"{pct * 100:.0f}%"
    return f"[{'█' * filled}{'░' * empty}] {pct_str:>4}"


def load_json(path: Path) -> dict | list | None:
    """Safely load JSON."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def count_files(directory: Path, ext: str = ".json") -> int:
    """Count files in directory."""
    try:
        return sum(1 for f in os.listdir(directory) if f.endswith(ext))
    except FileNotFoundError:
        return 0


def get_phase2_eth_status() -> dict:
    """Phase 2a: Ethereum transfer collection."""
    progress = load_json(DATA / "transfer_collection_progress.json") or {}
    completed = len(progress.get("completed", []))
    errors = len(progress.get("errors", []))
    skipped_list = progress.get("skipped", [])
    skipped = len(skipped_list) if isinstance(skipped_list, list) else 0
    total = completed + errors + skipped
    # Also count actual files
    files = count_files(DATA / "transfers")
    return {"completed": completed, "errors": errors, "skipped": skipped,
            "total": max(total, 1), "files": files}


def get_phase2_bsc_status() -> dict:
    """Phase 2b: BSC transfer collection."""
    progress = load_json(DATA / "bsc_transfer_progress.json") or {}
    completed = len(progress.get("completed", []))
    errors = len(progress.get("errors", []))
    skipped_list = progress.get("skipped", [])
    skipped = len(skipped_list) if isinstance(skipped_list, list) else 0
    # Total BSC tokens from evm_tokens
    evm_data = load_json(DATA / "evm_tokens.json")
    bsc_total = 0
    if evm_data:
        for t in evm_data.get("evm_tokens", []):
            contracts = t.get("contracts", {})
            if "binance-smart-chain" in contracts:
                bsc_total += 1
    total = max(bsc_total, completed + errors + skipped, 1)
    return {"completed": completed, "errors": errors, "skipped": skipped, "total": total}


def get_phase3_status() -> dict:
    """Phase 3: Address labeling."""
    labeled = load_json(DATA / "labeled" / "labeled_metrics.json")
    if not labeled:
        return {"labeled": 0, "total": 197}
    n = labeled.get("total_tokens", 0)
    # Total = transfer files available
    files = count_files(DATA / "transfers")
    return {"labeled": n, "total": max(files, n)}


def get_phase4_status() -> dict:
    """Phase 4: Signal analysis."""
    analysis = load_json(DATA / "labeled" / "signal_analysis.json")
    if not analysis:
        return {"analyzed": 0, "total": 0, "significant": 0, "features": 0}
    ds = analysis.get("dataset", {})
    feats = analysis.get("feature_analysis", [])
    sig = sum(1 for f in feats if f.get("p_value", 1) < 0.05)
    borderline = sum(1 for f in feats if 0.05 <= f.get("p_value", 1) < 0.10)
    cats = ds.get("categories", {})
    return {
        "analyzed": ds.get("total", 0),
        "winners": cats.get("winner", 0),
        "losers": cats.get("loser", 0),
        "features": len(feats),
        "significant": sig,
        "borderline": borderline,
        "target_per_group": 80,
    }


def get_phase5_status() -> dict:
    """Phase 5: Holder snapshots."""
    progress = load_json(DATA / "snapshot_progress.json") or {}
    completed = len(progress.get("completed", []))
    errors = len(progress.get("errors", []))
    skipped_list = progress.get("skipped", [])
    skipped = len(skipped_list) if isinstance(skipped_list, list) else 0
    files = count_files(DATA / "snapshots")
    total = count_files(DATA / "transfers")  # target = all collected tokens
    return {"completed": completed, "errors": errors, "skipped": skipped,
            "files": files, "total": max(total, 1)}


def get_power_status(phase4: dict) -> dict:
    """Power analysis status."""
    w = phase4.get("winners", 0)
    l = phase4.get("losers", 0)
    min_group = min(w, l)
    # Thresholds from power analysis
    levels = [
        (48, "power=0.90, d≥0.68 (strong)"),
        (80, "power=0.90, d≥0.53 (medium)"),
        (121, "power=0.90, d≥0.43 (all actionable)"),
    ]
    achieved = []
    next_target = None
    for n, desc in levels:
        if min_group >= n:
            achieved.append(desc)
        elif next_target is None:
            next_target = (n, desc)
    return {
        "min_group": min_group,
        "winners": w,
        "losers": l,
        "achieved": achieved,
        "next_target": next_target,
        "bottleneck": "winners" if w < l else "losers",
    }


def render(iteration: int):
    """Render the full dashboard."""
    # Clear screen
    print("\033[2J\033[H", end="")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{'═' * 72}")
    print(f"  📊 ONCHAIN SIGNAL DISCOVERY — LIVE DASHBOARD")
    print(f"  {now}  (refresh #{iteration}, every 60s, Ctrl+C to exit)")
    print(f"{'═' * 72}")

    # Phase 2a: ETH transfers
    p2e = get_phase2_eth_status()
    track("p2e", p2e["completed"])
    print(f"\n  Phase 2a: ETH Transfer Collection")
    print(f"  {bar(p2e['completed'], p2e['total'])}  "
          f"{p2e['completed']}/{p2e['total']}  "
          f"(err:{p2e['errors']}, skip:{p2e['skipped']})  "
          f"files: {p2e['files']}")

    # Phase 2b: BSC transfers
    p2b = get_phase2_bsc_status()
    track("p2b", p2b["completed"])
    eta_p2b = estimate_eta("p2b", p2b["total"])
    print(f"\n  Phase 2b: BSC Transfer Collection")
    print(f"  {bar(p2b['completed'], p2b['total'])}  "
          f"{p2b['completed']}/{p2b['total']}  "
          f"(err:{p2b['errors']}, skip:{p2b['skipped']})  "
          f"ETA: {eta_p2b}")

    # Phase 3: Labeling
    p3 = get_phase3_status()
    track("p3", p3["labeled"])
    eta_p3 = estimate_eta("p3", p3["total"])
    print(f"\n  Phase 3: Address Labeling")
    print(f"  {bar(p3['labeled'], p3['total'])}  "
          f"{p3['labeled']}/{p3['total']}  "
          f"ETA: {eta_p3}")

    # Phase 4: Signal Analysis
    p4 = get_phase4_status()
    print(f"\n  Phase 4: Signal Analysis")
    print(f"  {bar(p4['analyzed'], p4['analyzed'])}  "
          f"{p4['analyzed']} tokens ({p4['winners']}W + {p4['losers']}L)")
    print(f"  Features: {p4['features']} tested, "
          f"{p4['significant']} significant (p<0.05), "
          f"{p4['borderline']} borderline (p<0.10)")

    # Power Analysis
    pw = get_power_status(p4)
    print(f"\n  ⚡ Statistical Power")
    print(f"  Min group size: {pw['min_group']} "
          f"(W:{pw['winners']}, L:{pw['losers']}) — bottleneck: {pw['bottleneck']}")
    for a in pw["achieved"]:
        print(f"    ✅ {a}")
    if pw["next_target"]:
        n, desc = pw["next_target"]
        need = n - pw["min_group"]
        print(f"    ⬜ {desc} — need {need} more {pw['bottleneck']}")

    # Phase 5: Snapshots
    p5 = get_phase5_status()
    track("p5", p5["completed"])
    eta_p5 = estimate_eta("p5", p5["total"])
    print(f"\n  Phase 5: Holder Snapshots (Genesis → T)")
    print(f"  {bar(p5['completed'], p5['total'])}  "
          f"{p5['completed']}/{p5['total']}  "
          f"(err:{p5['errors']}, skip:{p5['skipped']})  "
          f"files: {p5['files']}  ETA: {eta_p5}")

    # Overall
    total_tasks = 5
    # Weight phases by importance
    overall = (
        min(p2e["completed"] / max(p2e["total"], 1), 1.0) * 0.15 +
        min(p2b["completed"] / max(p2b["total"], 1), 1.0) * 0.15 +
        min(p3["labeled"] / max(p3["total"], 1), 1.0) * 0.20 +
        (1.0 if p4["significant"] >= 2 else p4["significant"] / 2) * 0.20 +
        min(p5["completed"] / max(p5["total"], 1), 1.0) * 0.30
    )
    print(f"\n{'─' * 72}")
    print(f"  OVERALL: {bar(int(overall * 100), 100)}  "
          f"weighted across all phases")
    print(f"{'═' * 72}")

    # Action items
    print(f"\n  📋 Next Steps:")
    if p3["labeled"] < p3["total"]:
        gap = p3["total"] - p3["labeled"]
        print(f"    1. Label {gap} unlabeled tokens → python scripts/label_transfers.py")
    if pw["next_target"]:
        n, desc = pw["next_target"]
        need = n - pw["min_group"]
        print(f"    2. Collect {need}+ BSC {pw['bottleneck']} → python scripts/collect_transfers_bsc.py")
    if p5["completed"] < 50:
        print(f"    3. Run Phase 5 snapshots → python scripts/collect_holder_snapshots.py")
    print()


def main():
    print("Starting dashboard... (updates every 60s, Ctrl+C to exit)\n")
    iteration = 0
    try:
        while True:
            iteration += 1
            render(iteration)
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n\nDashboard stopped.")


if __name__ == "__main__":
    main()
