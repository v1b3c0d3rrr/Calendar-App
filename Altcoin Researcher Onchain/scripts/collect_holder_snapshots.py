"""
Collect holder snapshots from genesis to T (peak/bottom) for each EVM token.

For each token:
1. Fetch ALL ERC-20 transfers from block 0 to block T (event date)
2. Process transfers chronologically, maintaining address → balance map
3. Every 12 hours (by timestamp), take a snapshot of holder distribution
4. Compute metrics: holder count, concentration, Gini, new/exited holders, etc.

Output: data/snapshots/{coin_id}.json per token
Progress: data/snapshot_progress.json (resumable)

Uses two API keys: KEY_1 for free chains, KEY_2 for BSC/paid chains.
"""

import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

import requests

# ============================================================
# Config
# ============================================================

load_dotenv()

API_KEY_1 = os.getenv("ETHERSCAN_API_KEY")      # Free chains
API_KEY_2 = os.getenv("ETHERSCAN_API_KEY_2")     # BSC / paid chains
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

CHAINS = {
    "ethereum": 1,
    "binance-smart-chain": 56,
    "polygon-pos": 137,
    "arbitrum-one": 42161,
    "optimistic-ethereum": 10,
    "base": 8453,
    "avalanche": 43114,
    "fantom": 250,
    "linea": 59144,
    "scroll": 534352,
    "zksync": 324,
    "blast": 81457,
    "mantle": 5000,
}

FREE_CHAINS = {1, 137, 42161, 59144, 534352}

CHAIN_PRIORITY = [1, 137, 42161, 59144, 534352, 56, 10, 8453, 43114, 250]

DATA_DIR = Path(__file__).parent.parent / "data"
CALIBRATION_DIR = Path(__file__).parent.parent.parent / "Alt Boss" / "calibration"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
PROGRESS_FILE = DATA_DIR / "snapshot_progress.json"

SNAPSHOT_INTERVAL = 12 * 3600  # 12 hours in seconds
ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# Limits to keep collection feasible
MAX_14D_TRANSFERS = 5000       # Skip tokens with >5000 transfers in 14-day window
MAX_RECURSION_DEPTH = 8        # Max binary-split depth (256 chunks max)
MAX_TOTAL_TRANSFERS = 100_000  # Abort if token has >100k lifetime transfers
TRANSFERS_DIR = DATA_DIR / "transfers"  # Phase 2 data for filtering

# ============================================================
# Rate-limited API
# ============================================================

@sleep_and_retry
@limits(calls=5, period=1)
def _request(chain_id: int, module: str, action: str, **params) -> dict:
    """Rate-limited Etherscan v2 API request with key rotation."""
    api_key = API_KEY_1 if chain_id in FREE_CHAINS else API_KEY_2
    params.update({
        "chainid": chain_id,
        "module": module,
        "action": action,
        "apikey": api_key,
    })
    for attempt in range(3):
        try:
            resp = requests.get(ETHERSCAN_V2_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "0":
                result_str = str(data.get("result", ""))
                msg = data.get("message", "")
                if "No transactions found" in msg or "No records found" in msg:
                    return data
                if "rate limit" in result_str.lower() or "rate limit" in msg.lower():
                    time.sleep(2 + attempt)
                    continue
                if "not supported" in result_str.lower() or "upgrade" in result_str.lower():
                    return {"status": "0", "result": [], "_chain_not_supported": True}
            return data
        except requests.exceptions.Timeout:
            time.sleep(2 + attempt)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 + attempt)
    return {"status": "0", "result": []}


def get_block_by_timestamp(chain_id: int, timestamp: int, closest: str = "before") -> int:
    data = _request(chain_id, "block", "getblocknobytime", timestamp=timestamp, closest=closest)
    return int(data.get("result", 0))


def get_token_transfers_page(
    chain_id: int, contract: str, start_block: int, end_block: int,
    page: int = 1, offset: int = 10000, sort: str = "asc"
) -> list:
    data = _request(
        chain_id, "account", "tokentx",
        contractaddress=contract,
        startblock=start_block,
        endblock=end_block,
        page=page,
        offset=offset,
        sort=sort,
    )
    if data.get("_chain_not_supported"):
        return None  # Signal: chain not available
    result = data.get("result", [])
    return result if isinstance(result, list) else []


# ============================================================
# Token loading (same as collect_transfers.py)
# ============================================================

def load_evm_tokens() -> list:
    with open(DATA_DIR / "evm_tokens.json") as f:
        data = json.load(f)

    with open(CALIBRATION_DIR / "candidates_clean.json") as f:
        candidates = json.load(f)

    date_lookup = {}
    for t in candidates.get("pure_winners", []):
        date_lookup[t["coin_id"]] = {
            "event_date": t["peak_date"],
            "category": "winner",
        }
    for t in candidates.get("pump_and_dump", []):
        date_lookup[t["coin_id"]] = {
            "event_date": t["peak_date"],
            "category": "pump_and_dump",
        }
    for t in candidates.get("losers", []):
        date_lookup[t["coin_id"]] = {
            "event_date": t.get("bottom_date", t["start_date"]),
            "category": "loser",
        }

    tokens = []
    for t in data["evm_tokens"]:
        dates = date_lookup.get(t["coin_id"])
        if not dates:
            continue

        best_chain = None
        best_contract = None
        for chain_id in CHAIN_PRIORITY:
            for cg_name, cid in CHAINS.items():
                if cid == chain_id and cg_name in t.get("contracts", {}):
                    best_chain = cid
                    best_contract = t["contracts"][cg_name]
                    break
            if best_chain:
                break

        if not best_chain or not best_contract:
            continue

        tokens.append({
            "coin_id": t["coin_id"],
            "symbol": t["symbol"],
            "name": t["name"],
            "category": dates["category"],
            "multiplier": t.get("multiplier"),
            "start_mc": t.get("start_mc"),
            "event_date": dates["event_date"],
            "chain_id": best_chain,
            "chain_name": next(k for k, v in CHAINS.items() if v == best_chain),
            "contract": best_contract,
        })

    return tokens


# ============================================================
# Snapshot computation
# ============================================================

def compute_gini(balances: list[int]) -> float:
    """Compute Gini coefficient from list of balances."""
    if not balances or len(balances) < 2:
        return 0.0
    n = len(balances)
    sorted_b = sorted(balances)
    total = sum(sorted_b)
    if total == 0:
        return 0.0
    cumulative = 0
    gini_sum = 0
    for i, b in enumerate(sorted_b):
        cumulative += b
        gini_sum += (2 * (i + 1) - n - 1) * b
    return gini_sum / (n * total)


def compute_hhi(balances: list[int], total_supply: int) -> float:
    """Herfindahl-Hirschman Index — sum of squared market shares."""
    if total_supply == 0 or not balances:
        return 0.0
    return sum((b / total_supply) ** 2 for b in balances)


def classify_holder_size(balance: int, supply: int) -> str:
    """Classify holder by balance relative to supply.

    Buckets:
    - dust:   < 0.001% of supply
    - tiny:   0.001% - 0.01%
    - small:  0.01% - 0.1%
    - medium: 0.1% - 1%
    - large:  1% - 5%
    - whale:  > 5%
    """
    if supply <= 0:
        return "unknown"
    pct = balance / supply
    if pct < 0.00001:
        return "dust"
    elif pct < 0.0001:
        return "tiny"
    elif pct < 0.001:
        return "small"
    elif pct < 0.01:
        return "medium"
    elif pct < 0.05:
        return "large"
    else:
        return "whale"


SIZE_BUCKETS = ["dust", "tiny", "small", "medium", "large", "whale"]


def take_snapshot(
    balances: dict[str, int],
    total_supply: int,
    timestamp: int,
    period_transfers: int,
    period_volume: int,
    prev_holders: set,
    prev_balances: dict[str, int],
) -> dict:
    """Compute holder distribution snapshot at a point in time.

    Now includes size-bucketed new/exited holders:
    - new holders classified by their CURRENT balance (what they accumulated)
    - exited holders classified by their PREVIOUS balance (what they had before leaving)
    """
    # Filter to positive balances, exclude zero address
    holders = {
        addr: bal for addr, bal in balances.items()
        if bal > 0 and addr != ZERO_ADDR
    }

    if not holders:
        return {
            "timestamp": timestamp,
            "datetime": datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M"),
            "total_holders": 0,
            "total_supply_held": 0,
            "metrics": {},
        }

    holder_set = set(holders.keys())
    bals = sorted(holders.values(), reverse=True)
    n = len(bals)
    total_held = sum(bals)
    supply = total_supply if total_supply > 0 else total_held

    # Top N concentration
    def top_pct(k):
        if n < k:
            return 1.0
        return sum(bals[:k]) / supply if supply > 0 else 0

    # Whale threshold: holders with > 1% of supply
    whale_threshold = supply * 0.01
    whale_count = sum(1 for b in bals if b >= whale_threshold)

    # New / exited holders
    new_holders = holder_set - prev_holders if prev_holders else set()
    exited_holders = prev_holders - holder_set if prev_holders else set()

    # Size-bucketed new holders (by their current balance)
    new_by_size = {b: 0 for b in SIZE_BUCKETS}
    for addr in new_holders:
        bal = holders.get(addr, 0)
        bucket = classify_holder_size(bal, supply)
        new_by_size[bucket] = new_by_size.get(bucket, 0) + 1

    # Size-bucketed exited holders (by their PREVIOUS balance — what they held before leaving)
    exit_by_size = {b: 0 for b in SIZE_BUCKETS}
    for addr in exited_holders:
        prev_bal = prev_balances.get(addr, 0)
        bucket = classify_holder_size(prev_bal, supply)
        exit_by_size[bucket] = exit_by_size.get(bucket, 0) + 1

    return {
        "timestamp": timestamp,
        "datetime": datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M"),
        "total_holders": n,
        "total_supply_held": total_held,
        "top10_pct": round(top_pct(10), 6),
        "top20_pct": round(top_pct(20), 6),
        "top50_pct": round(top_pct(50), 6),
        "top100_pct": round(top_pct(100), 6),
        "gini": round(compute_gini(bals), 6),
        "hhi": round(compute_hhi(bals, supply), 8),
        "whale_count": whale_count,
        "median_holding": bals[n // 2] if n > 0 else 0,
        "mean_holding": total_held // n if n > 0 else 0,
        "max_holding": bals[0] if n > 0 else 0,
        "new_holders": len(new_holders),
        "exited_holders": len(exited_holders),
        "new_by_size": new_by_size,
        "exit_by_size": exit_by_size,
        "transfers_in_period": period_transfers,
        "volume_in_period": period_volume,
    }


# ============================================================
# Main collection logic
# ============================================================

def collect_transfers_chunked(
    chain_id: int, contract: str, start_block: int, end_block: int,
    max_per_page: int = 10000, depth: int = 0, running_total: list = None,
) -> Optional[list]:
    """
    Collect ALL transfers between start_block and end_block.

    Etherscan caps at 10,000 results per query. If we hit the cap,
    split the block range in half and recurse.

    Safety limits:
    - MAX_RECURSION_DEPTH (8) = max 256 chunks
    - MAX_TOTAL_TRANSFERS (300k) = abort if too many
    """
    if running_total is None:
        running_total = [0]  # mutable counter shared across recursion

    # Check depth limit
    if depth > MAX_RECURSION_DEPTH:
        print(f"      [depth limit {depth}] block range {start_block}-{end_block}")
        return []

    transfers = get_token_transfers_page(
        chain_id, contract, start_block, end_block,
        page=1, offset=max_per_page, sort="asc"
    )

    if transfers is None:
        return None  # Chain not supported

    if not transfers:
        return []

    # If we got less than max, we have all transfers for this range
    if len(transfers) < max_per_page:
        running_total[0] += len(transfers)
        if running_total[0] > MAX_TOTAL_TRANSFERS:
            print(f"      [ABORT] total transfers {running_total[0]} > {MAX_TOTAL_TRANSFERS}")
            return None
        if running_total[0] % 50000 < max_per_page:
            print(f"      ... {running_total[0]} transfers collected so far")
        return transfers

    # Hit the cap — split range and recurse
    if start_block >= end_block:
        running_total[0] += len(transfers)
        return transfers

    mid_block = (start_block + end_block) // 2
    if mid_block == start_block:
        running_total[0] += len(transfers)
        return transfers

    left = collect_transfers_chunked(chain_id, contract, start_block, mid_block, max_per_page, depth + 1, running_total)
    if left is None:
        return None

    right = collect_transfers_chunked(chain_id, contract, mid_block + 1, end_block, max_per_page, depth + 1, running_total)
    if right is None:
        return None

    return left + right


def collect_token_snapshots(token: dict) -> Optional[dict]:
    """
    Collect all transfers from genesis to T for a token,
    build 12h holder snapshots.
    """
    coin_id = token["coin_id"]
    chain_id = token["chain_id"]
    contract = token["contract"].lower()
    event_date = token["event_date"]

    # Event timestamp (T)
    t_event = int(datetime.strptime(event_date, "%Y-%m-%d").timestamp())

    # Get block at T
    block_t = get_block_by_timestamp(chain_id, t_event, "before")
    if block_t == 0:
        print(f"    SKIP: could not resolve block for T={event_date}")
        return None

    # Collect ALL transfers from block 0 to block_t using chunked approach
    print(f"    Collecting transfers from block 0 to {block_t}...")
    all_transfers = collect_transfers_chunked(chain_id, contract, 0, block_t)

    if all_transfers is None:
        print(f"    SKIP: chain {chain_id} not supported on current plan")
        return None

    if not all_transfers:
        print(f"    SKIP: no transfers found")
        return None

    print(f"    Total transfers: {len(all_transfers)}")

    # Sort by timestamp (should already be sorted by block, but ensure)
    for tx in all_transfers:
        tx["_ts"] = int(tx.get("timeStamp", 0))
    all_transfers.sort(key=lambda x: (x["_ts"], x.get("blockNumber", "0")))

    # Find first transfer timestamp — this is effective genesis
    first_ts = all_transfers[0]["_ts"]
    last_ts = all_transfers[-1]["_ts"]

    # Get token decimals
    decimals = int(all_transfers[0].get("tokenDecimal", 18))

    # Build snapshot timeline
    # Align to 12h boundaries starting from first transfer
    snapshot_times = []
    t = first_ts
    while t <= t_event:
        snapshot_times.append(t)
        t += SNAPSHOT_INTERVAL
    # Always include final snapshot at t_event
    if snapshot_times[-1] < t_event:
        snapshot_times.append(t_event)

    # Process transfers chronologically, taking snapshots
    balances = defaultdict(int)  # address -> raw balance (in smallest unit)
    total_supply = 0
    tx_idx = 0
    snapshots = []
    prev_holders = set()
    prev_balances = {}  # address -> balance at previous snapshot

    period_transfers = 0
    period_volume = 0

    for snap_ts in snapshot_times:
        # Process all transfers up to this snapshot time
        while tx_idx < len(all_transfers) and all_transfers[tx_idx]["_ts"] <= snap_ts:
            tx = all_transfers[tx_idx]
            from_addr = tx.get("from", "").lower()
            to_addr = tx.get("to", "").lower()
            value = int(tx.get("value", 0))

            # Update balances
            if from_addr == ZERO_ADDR:
                # Mint
                total_supply += value
            else:
                balances[from_addr] -= value

            if to_addr == ZERO_ADDR:
                # Burn
                total_supply -= value
            else:
                balances[to_addr] += value

            period_transfers += 1
            period_volume += value
            tx_idx += 1

        # Take snapshot (with size-bucketed new/exited holders)
        snap = take_snapshot(
            balances, total_supply, snap_ts,
            period_transfers, period_volume, prev_holders, prev_balances
        )
        snapshots.append(snap)

        # Update prev state for next period
        prev_holders = {
            addr for addr, bal in balances.items()
            if bal > 0 and addr != ZERO_ADDR
        }
        # Save current balances for size classification of future exits
        prev_balances = {
            addr: bal for addr, bal in balances.items()
            if bal > 0 and addr != ZERO_ADDR
        }
        period_transfers = 0
        period_volume = 0

    return {
        "coin_id": coin_id,
        "symbol": token["symbol"],
        "name": token["name"],
        "category": token["category"],
        "multiplier": token.get("multiplier"),
        "start_mc": token.get("start_mc"),
        "chain_id": chain_id,
        "chain_name": token["chain_name"],
        "contract": contract,
        "event_date": event_date,
        "block_t": block_t,
        "decimals": decimals,
        "total_transfers": len(all_transfers),
        "first_transfer": datetime.utcfromtimestamp(first_ts).strftime("%Y-%m-%d %H:%M"),
        "last_transfer": datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M"),
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
    }


# ============================================================
# Progress management
# ============================================================

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "errors": [], "skipped": []}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ============================================================
# Main
# ============================================================

def main():
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    tokens = load_evm_tokens()
    progress = load_progress()

    print(f"=" * 60)
    print(f"HOLDER SNAPSHOT COLLECTOR")
    print(f"=" * 60)
    print(f"Total EVM tokens: {len(tokens)}")
    print(f"Already completed: {len(progress['completed'])}")
    print(f"API keys: KEY_1={'YES' if API_KEY_1 else 'NO'}, KEY_2={'YES' if API_KEY_2 else 'NO'}")

    completed_set = set(progress["completed"])
    skipped_set = {s["coin_id"] for s in progress.get("skipped", [])}
    error_set = {e["coin_id"] for e in progress.get("errors", [])}

    # Load 14-day transfer counts from Phase 2 to filter heavy tokens
    transfer_counts = {}
    if TRANSFERS_DIR.exists():
        for f in TRANSFERS_DIR.glob("*.json"):
            try:
                with open(f) as fp:
                    d = json.load(fp)
                transfer_counts[d["coin_id"]] = d.get("transfer_count", 0)
            except Exception:
                pass
    print(f"Phase 2 transfer data: {len(transfer_counts)} tokens")

    to_process = []
    heavy_skipped = 0
    for t in tokens:
        cid = t["coin_id"]
        if cid in completed_set or cid in skipped_set:
            continue
        # Skip tokens with too many 14-day transfers (genesis will be way more)
        count_14d = transfer_counts.get(cid, 0)
        if count_14d > MAX_14D_TRANSFERS:
            heavy_skipped += 1
            progress["skipped"].append({
                "coin_id": cid,
                "reason": f"too heavy: {count_14d} transfers in 14d (limit {MAX_14D_TRANSFERS})",
            })
            continue
        to_process.append(t)

    if heavy_skipped:
        print(f"Skipped {heavy_skipped} heavy tokens (>{MAX_14D_TRANSFERS} 14d transfers)")
        save_progress(progress)

    # Sort: free chains first, winners first
    cat_priority = {"winner": 0, "pump_and_dump": 1, "loser": 2}
    to_process.sort(key=lambda t: (
        0 if t["chain_id"] in FREE_CHAINS else 1,
        cat_priority.get(t["category"], 9),
    ))

    print(f"To process: {len(to_process)}")

    # Chain stats
    chain_counts = {}
    for t in to_process:
        cn = t["chain_name"]
        chain_counts[cn] = chain_counts.get(cn, 0) + 1
    print(f"By chain: {json.dumps(chain_counts)}")

    cat_counts = {}
    for t in to_process:
        cat_counts[t["category"]] = cat_counts.get(t["category"], 0) + 1
    print(f"By category: {json.dumps(cat_counts)}")
    print()

    for i, token in enumerate(to_process):
        print(f"[{i+1}/{len(to_process)}] {token['symbol']} ({token['coin_id']}) — "
              f"{token['category']} — {token['chain_name']} (chain {token['chain_id']})")

        try:
            result = collect_token_snapshots(token)
        except Exception as e:
            print(f"    ERROR: {e}")
            progress["errors"].append({
                "coin_id": token["coin_id"],
                "error": str(e),
            })
            save_progress(progress)
            continue

        if result is None:
            progress["skipped"].append({
                "coin_id": token["coin_id"],
                "reason": "no data or chain not supported",
            })
        else:
            # Save snapshot file
            outfile = SNAPSHOTS_DIR / f"{token['coin_id']}.json"
            with open(outfile, "w") as f:
                json.dump(result, f)

            progress["completed"].append(token["coin_id"])
            print(f"    OK: {result['total_transfers']} transfers → "
                  f"{result['snapshot_count']} snapshots ({result['first_transfer']} → {result['last_transfer']})")

        # Save progress every 3 tokens
        if (i + 1) % 3 == 0:
            save_progress(progress)
            print(f"    [Progress: {len(progress['completed'])} done, "
                  f"{len(progress['skipped'])} skipped, {len(progress['errors'])} errors]")

    save_progress(progress)
    print(f"\n{'=' * 60}")
    print(f"DONE: {len(progress['completed'])} completed, "
          f"{len(progress['skipped'])} skipped, {len(progress['errors'])} errors")


if __name__ == "__main__":
    main()
