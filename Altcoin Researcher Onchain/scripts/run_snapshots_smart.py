"""
Smart snapshot runner — processes tokens from smallest to largest.

Strategy:
1. First probe: try to get transfers from block 0 with 1 page
2. If < 10,000 → token is small, process immediately
3. If = 10,000 → token is big, defer to later batch
4. Process deferred tokens last (with recursive chunking)

This ensures we get maximum coverage quickly on small tokens.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from collect_holder_snapshots import (
    load_evm_tokens, collect_token_snapshots,
    SNAPSHOTS_DIR, PROGRESS_FILE, FREE_CHAINS,
    get_token_transfers_page, get_block_by_timestamp,
)
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "errors": [], "skipped": []}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def probe_token_size(token: dict) -> int:
    """Quick probe: how many transfers does this token have? Returns count or -1 for error."""
    chain_id = token["chain_id"]
    contract = token["contract"].lower()
    event_date = token["event_date"]

    t_event = int(datetime.strptime(event_date, "%Y-%m-%d").timestamp())
    try:
        block_t = get_block_by_timestamp(chain_id, t_event, "before")
    except Exception:
        return -1

    if block_t == 0:
        return -1

    try:
        transfers = get_token_transfers_page(
            chain_id, contract, 0, block_t,
            page=1, offset=10000, sort="asc"
        )
    except Exception:
        return -1

    if transfers is None:
        return -1  # Chain not supported

    return len(transfers)


def main():
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    tokens = load_evm_tokens()
    completed_set = set(progress["completed"])
    skipped_set = {s["coin_id"] for s in progress.get("skipped", [])}

    to_process = [
        t for t in tokens
        if t["coin_id"] not in completed_set
        and t["coin_id"] not in skipped_set
    ]

    # Sort: free chains first, winners first
    cat_priority = {"winner": 0, "pump_and_dump": 1, "loser": 2}
    to_process.sort(key=lambda t: (
        0 if t["chain_id"] in FREE_CHAINS else 1,
        cat_priority.get(t["category"], 9),
    ))

    print(f"=" * 60)
    print(f"SMART SNAPSHOT RUNNER")
    print(f"=" * 60)
    print(f"Total: {len(tokens)}, Already done: {len(completed_set)}, To process: {len(to_process)}")
    print()

    # Phase 1: Probe all tokens and sort by size
    print("Phase 1: Probing token sizes...")
    small_tokens = []  # < 10,000 transfers (can do in one shot)
    big_tokens = []    # 10,000 = capped (need recursive chunking)
    failed_tokens = [] # probe failed

    for i, token in enumerate(to_process):
        if (i + 1) % 20 == 0:
            print(f"  Probed {i+1}/{len(to_process)}...")
        size = probe_token_size(token)
        if size == -1:
            failed_tokens.append(token)
        elif size >= 10000:
            big_tokens.append((token, size))
        else:
            small_tokens.append((token, size))

    print(f"\nProbe results:")
    print(f"  Small (<10k transfers): {len(small_tokens)}")
    print(f"  Big (10k+ transfers): {len(big_tokens)}")
    print(f"  Failed/unsupported: {len(failed_tokens)}")

    # Sort small by size (smallest first)
    small_tokens.sort(key=lambda x: x[1])

    # Phase 2: Process small tokens first
    print(f"\nPhase 2: Processing {len(small_tokens)} small tokens...")
    processed = 0
    for i, (token, size) in enumerate(small_tokens):
        print(f"\n[{i+1}/{len(small_tokens)}] {token['symbol']} ({token['coin_id']}) "
              f"— {token['category']} — ~{size} transfers")

        try:
            result = collect_token_snapshots(token)
        except Exception as e:
            print(f"    ERROR: {e}")
            progress["errors"].append({"coin_id": token["coin_id"], "error": str(e)})
            save_progress(progress)
            continue

        if result is None:
            progress["skipped"].append({
                "coin_id": token["coin_id"],
                "reason": "no data or chain not supported",
            })
        else:
            outfile = SNAPSHOTS_DIR / f"{token['coin_id']}.json"
            with open(outfile, "w") as f:
                json.dump(result, f)
            progress["completed"].append(token["coin_id"])
            processed += 1
            print(f"    OK: {result['total_transfers']} transfers → {result['snapshot_count']} snapshots")

        if (i + 1) % 5 == 0:
            save_progress(progress)
            print(f"    [Progress: {len(progress['completed'])} done, "
                  f"{len(progress['skipped'])} skipped, {len(progress['errors'])} errors]")

    save_progress(progress)
    print(f"\nSmall tokens done: {processed} processed")

    # Phase 3: Process big tokens (recursive chunking)
    print(f"\nPhase 3: Processing {len(big_tokens)} big tokens (will be slow)...")
    for i, (token, size) in enumerate(big_tokens):
        print(f"\n[{i+1}/{len(big_tokens)}] {token['symbol']} ({token['coin_id']}) "
              f"— {token['category']} — 10k+ transfers (chunked)")

        try:
            result = collect_token_snapshots(token)
        except Exception as e:
            print(f"    ERROR: {e}")
            progress["errors"].append({"coin_id": token["coin_id"], "error": str(e)})
            save_progress(progress)
            continue

        if result is None:
            progress["skipped"].append({
                "coin_id": token["coin_id"],
                "reason": "no data or chain not supported",
            })
        else:
            outfile = SNAPSHOTS_DIR / f"{token['coin_id']}.json"
            with open(outfile, "w") as f:
                json.dump(result, f)
            progress["completed"].append(token["coin_id"])
            print(f"    OK: {result['total_transfers']} transfers → {result['snapshot_count']} snapshots")

        save_progress(progress)

    # Handle failed probes
    for token in failed_tokens:
        progress["skipped"].append({
            "coin_id": token["coin_id"],
            "reason": "probe failed (chain not supported or API error)",
        })

    save_progress(progress)
    print(f"\n{'=' * 60}")
    print(f"FINAL: {len(progress['completed'])} completed, "
          f"{len(progress['skipped'])} skipped, {len(progress['errors'])} errors")


if __name__ == "__main__":
    main()
