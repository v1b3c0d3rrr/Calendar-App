"""
BSC token transfer collector via free RPC (eth_getLogs).

Etherscan v2 requires paid plan for BSC, so we use public RPC nodes
to query ERC-20 Transfer events directly from BSC.

Approach:
- Use PublicNode BSC RPC (free, supports eth_getLogs up to 50k blocks)
- Parse Transfer(address,address,uint256) events
- Scan in adaptive chunks (50k blocks, reduce on error)
- Convert timestamps to blocks using anchor block + rate estimation
- Save in same format as ETH transfers for unified analysis pipeline

BSC block time: ~3 sec (actually ~0.45 sec based on measurement)
14 days ≈ 2.7M blocks ≈ 54 requests per token at 50k blocks/chunk
"""

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSFERS_DIR = DATA_DIR / "transfers"
PROGRESS_FILE = DATA_DIR / "bsc_transfer_progress.json"

# BSC RPC endpoints (free, no API key needed)
# NodeReal first — supports historical/archive data
# PublicNode — pruned, only works for recent blocks
RPC_URLS = [
    "https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3",
    "https://bsc-rpc.publicnode.com",
]

# ERC-20 Transfer event topic
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Chunk size (blocks per request)
MAX_CHUNK = 50000
MIN_CHUNK = 1000

# Rate limit: ~2 requests/sec to be safe
REQUEST_DELAY = 0.5

# Calibration points for piecewise block estimation (BSC changed block time!)
# BSC had ~0.75 sec/block until Jan 2026, then switched to ~0.45 sec/block
# Format: (block_number, unix_timestamp)
CALIBRATION_POINTS = [
    (42720265, 1727740598),   # 2024-09-30 23:56 (~0.75 s/block era)
    (56652875, 1754487715),   # 2025-08-06 13:41
    (63036904, 1759276738),   # 2025-09-30 23:58
    (73000000, 1766752069),   # 2025-12-26 12:27 (rate transition zone)
    (75000000, 1768252348),   # 2026-01-12 21:12 (~0.45 s/block starts)
    (77000000, 1769194929),   # 2026-01-23 19:02
    (80000000, 1770545597),   # 2026-02-08 10:13
    (85000000, 1772796115),   # 2026-03-06 11:21
    (85996163, 1773244480),   # 2026-03-11 15:54
]

# Cache for binary-searched blocks
_block_cache = {}


def rpc_call(method: str, params: list, rpc_idx: int = 0, timeout: int = 30) -> dict:
    """Make an RPC call to BSC node."""
    rpc_url = RPC_URLS[rpc_idx % len(RPC_URLS)]
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}

    for attempt in range(3):
        try:
            r = requests.post(rpc_url, json=payload, timeout=timeout)
            data = r.json()
            if "error" in data:
                err = data["error"].get("message", "")
                if "limit" in err.lower() or "rate" in err.lower():
                    time.sleep(2 ** attempt)
                    rpc_idx += 1
                    rpc_url = RPC_URLS[rpc_idx % len(RPC_URLS)]
                    continue
                if "pruned" in err.lower():
                    # This RPC pruned history, try next one
                    rpc_idx += 1
                    rpc_url = RPC_URLS[rpc_idx % len(RPC_URLS)]
                    continue
                return data
            return data
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
                rpc_idx += 1
                rpc_url = RPC_URLS[rpc_idx % len(RPC_URLS)]
            else:
                return {"error": {"message": str(e)}}

    return {"error": {"message": "All retries exhausted"}}


def ts_to_block(timestamp: int) -> int:
    """Estimate BSC block number from Unix timestamp using piecewise interpolation."""
    # Find the two closest calibration points
    pts = sorted(CALIBRATION_POINTS, key=lambda p: p[1])

    # If before first point or after last, extrapolate from nearest segment
    if timestamp <= pts[0][1]:
        b0, t0 = pts[0]
        b1, t1 = pts[1]
        rate = (t1 - t0) / (b1 - b0)
        return b0 + int((timestamp - t0) / rate)
    if timestamp >= pts[-1][1]:
        b0, t0 = pts[-2]
        b1, t1 = pts[-1]
        rate = (t1 - t0) / (b1 - b0)
        return b1 + int((timestamp - t1) / rate)

    # Interpolate between surrounding points
    for i in range(len(pts) - 1):
        b0, t0 = pts[i]
        b1, t1 = pts[i + 1]
        if t0 <= timestamp <= t1:
            rate = (t1 - t0) / (b1 - b0)
            return b0 + int((timestamp - t0) / rate)

    # Fallback
    b0, t0 = pts[-2]
    b1, t1 = pts[-1]
    rate = (t1 - t0) / (b1 - b0)
    return b1 + int((timestamp - t1) / rate)


def ts_to_block_precise(timestamp: int) -> int:
    """Find BSC block for timestamp using binary search (slow but accurate)."""
    if timestamp in _block_cache:
        return _block_cache[timestamp]

    # Start with piecewise estimate (now very accurate with 9 calibration points)
    estimate = ts_to_block(timestamp)
    low = max(1, estimate - 100000)
    high = estimate + 100000

    for _ in range(30):
        if high - low <= 50:
            break
        mid = (low + high) // 2
        ts = get_block_timestamp(mid)
        time.sleep(REQUEST_DELAY)
        if ts is None:
            high = mid - 1
            continue
        if ts < timestamp:
            low = mid
        else:
            high = mid

    _block_cache[timestamp] = low
    return low


def block_to_ts(block: int) -> int:
    """Estimate timestamp from BSC block number using piecewise interpolation."""
    pts = sorted(CALIBRATION_POINTS, key=lambda p: p[0])

    if block <= pts[0][0]:
        b0, t0 = pts[0]
        b1, t1 = pts[1]
        rate = (t1 - t0) / (b1 - b0)
        return t0 + int((block - b0) * rate)
    if block >= pts[-1][0]:
        b0, t0 = pts[-2]
        b1, t1 = pts[-1]
        rate = (t1 - t0) / (b1 - b0)
        return t1 + int((block - b1) * rate)

    for i in range(len(pts) - 1):
        b0, t0 = pts[i]
        b1, t1 = pts[i + 1]
        if b0 <= block <= b1:
            rate = (t1 - t0) / (b1 - b0)
            return t0 + int((block - b0) * rate)

    b0, t0 = pts[-2]
    b1, t1 = pts[-1]
    rate = (t1 - t0) / (b1 - b0)
    return t1 + int((block - b1) * rate)


def get_block_timestamp(block_number: int) -> Optional[int]:
    """Get actual timestamp for a block number."""
    data = rpc_call("eth_getBlockByNumber", [hex(block_number), False])
    if "result" in data and data["result"]:
        return int(data["result"]["timestamp"], 16)
    return None


def get_transfer_logs(contract: str, from_block: int, to_block: int) -> list:
    """Get ERC-20 Transfer events for a contract in a block range."""
    data = rpc_call("eth_getLogs", [{
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
        "address": contract,
        "topics": [TRANSFER_TOPIC],
    }])

    if "error" in data:
        return None  # Signal error (need smaller chunk)

    results = data.get("result", [])
    return results


def parse_transfer_log(log: dict) -> dict:
    """Parse an ERC-20 Transfer event log into a transfer dict."""
    # topics[1] = from (padded to 32 bytes)
    # topics[2] = to (padded to 32 bytes)
    # data = value (uint256)
    topics = log.get("topics", [])
    if len(topics) < 3:
        return None

    from_addr = "0x" + topics[1][-40:]
    to_addr = "0x" + topics[2][-40:]
    value = int(log.get("data", "0x0"), 16)
    block_number = int(log.get("blockNumber", "0x0"), 16)
    tx_hash = log.get("transactionHash", "")
    log_index = int(log.get("logIndex", "0x0"), 16)

    # Estimate timestamp from block
    ts = block_to_ts(block_number)

    return {
        "blockNumber": str(block_number),
        "timeStamp": str(ts),
        "hash": tx_hash,
        "from": from_addr.lower(),
        "to": to_addr.lower(),
        "value": str(value),
        "contractAddress": log.get("address", "").lower(),
        "tokenDecimal": "18",  # Will be updated per-token if known
        "logIndex": str(log_index),
    }


def collect_token_transfers(contract: str, start_block: int, end_block: int,
                            max_transfers: int = 50000) -> list:
    """
    Collect all Transfer events for a token in a block range.

    Uses adaptive chunking: starts at MAX_CHUNK, reduces on error.
    """
    all_transfers = []
    current_block = start_block
    chunk_size = MAX_CHUNK
    request_count = 0

    while current_block <= end_block:
        chunk_end = min(current_block + chunk_size - 1, end_block)

        time.sleep(REQUEST_DELAY)
        logs = get_transfer_logs(contract, current_block, chunk_end)
        request_count += 1

        if logs is None:
            # Error — reduce chunk size
            if chunk_size > MIN_CHUNK:
                chunk_size = chunk_size // 2
                continue
            else:
                print(f"    SKIP block {current_block}-{chunk_end} (persistent error)")
                current_block = chunk_end + 1
                continue

        # Parse logs
        for log in logs:
            t = parse_transfer_log(log)
            if t:
                all_transfers.append(t)

        if request_count % 10 == 0:
            pct = (current_block - start_block) / max(end_block - start_block, 1) * 100
            print(f"    [{pct:.0f}%] block {current_block}, {len(all_transfers)} transfers, chunk={chunk_size}")

        # If we got many results, chunk might be too large
        if len(logs) > 8000:
            chunk_size = max(chunk_size // 2, MIN_CHUNK)
        elif len(logs) < 100 and chunk_size < MAX_CHUNK:
            chunk_size = min(chunk_size * 2, MAX_CHUNK)

        current_block = chunk_end + 1

        if len(all_transfers) >= max_transfers:
            print(f"    Hit max_transfers limit ({max_transfers})")
            break

    print(f"    Done: {len(all_transfers)} transfers, {request_count} RPC requests")
    return all_transfers


def load_progress() -> dict:
    """Load progress tracking."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "skipped": [], "errors": []}


def save_progress(progress: dict):
    """Save progress tracking."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def estimate_transfer_count(contract: str, start_block: int, end_block: int) -> int:
    """Quick estimate of transfer count by sampling."""
    # Sample 3 chunks at beginning, middle, end
    total_range = end_block - start_block
    sample_size = min(10000, total_range // 3)

    total_estimate = 0
    samples = [
        (start_block, start_block + sample_size),
        (start_block + total_range // 2, start_block + total_range // 2 + sample_size),
        (end_block - sample_size, end_block),
    ]

    for s_start, s_end in samples:
        time.sleep(REQUEST_DELAY)
        logs = get_transfer_logs(contract, s_start, s_end)
        if logs is not None:
            rate = len(logs) / sample_size
            total_estimate += rate * total_range / 3

    return int(total_estimate)


def main():
    """Main collection loop."""
    # Load BSC token dates
    bsc_dates = {}
    dates_file = DATA_DIR / "bsc_token_dates.json"
    if dates_file.exists():
        with open(dates_file) as f:
            bsc_dates = json.load(f)

    # Load BSC tokens
    with open(DATA_DIR / "evm_tokens.json") as f:
        raw = json.load(f)
    tokens = raw["evm_tokens"] if isinstance(raw, dict) else raw

    bsc_tokens = []
    for t in tokens:
        contracts = t.get("contracts", {})
        if "binance-smart-chain" in contracts:
            bsc_tokens.append({
                "coin_id": t["coin_id"],
                "symbol": t.get("symbol", "?"),
                "name": t.get("name", "?"),
                "category": t.get("category", "unknown"),
                "multiplier": t.get("multiplier", 0),
                "contract": contracts["binance-smart-chain"],
                "chain_id": 56,
            })

    # Add special tokens (known manipulators)
    special_tokens = [
        {
            "coin_id": "merlin-chain",
            "symbol": "MERL",
            "name": "Merlin Chain",
            "category": "loser",  # -97% from ATH
            "multiplier": 0.03,
            "contract": "0xda360309c59cb8c434b28a91b823344a96444278",
            "chain_id": 56,
            "peak_date": "2025-01-15",  # approximate ATH
        },
        {
            "coin_id": "chainopera-ai",
            "symbol": "COAI",
            "name": "ChainOpera AI",
            "category": "pump_and_dump",
            "multiplier": 40.0,  # 4000% pump then -93%
            "contract": "0x0A8D6C86e1bcE73fE4D0bD531e1a567306836EA5",
            "chain_id": 56,
            "start_date_override": "2025-10-01",
        },
    ]

    # Add specials if not already present
    existing_ids = {t["coin_id"] for t in bsc_tokens}
    for st in special_tokens:
        if st["coin_id"] not in existing_ids:
            bsc_tokens.append(st)

    print(f"BSC tokens: {len(bsc_tokens)}")

    # Load progress
    progress = load_progress()
    done = set(progress["completed"])
    skipped = set(progress["skipped"])

    # Sort by estimated transfer count (collect small ones first)
    # Quick estimate: sample first 10k blocks for each token
    print("Estimating transfer counts...")
    estimates = {}
    for i, token in enumerate(bsc_tokens):
        cid = token["coin_id"]
        if cid in done or cid in skipped:
            continue

        # Check if BSC version already collected
        # Use _bsc suffix if ETH version exists for same coin_id
        out_file = TRANSFERS_DIR / f"{cid}.json"
        out_file_bsc = TRANSFERS_DIR / f"{cid}_bsc.json"
        if out_file_bsc.exists():
            done.add(cid)
            if cid not in progress["completed"]:
                progress["completed"].append(cid)
            continue
        if out_file.exists():
            # Check if existing file is BSC
            try:
                with open(out_file) as _f:
                    existing = json.load(_f)
                if existing.get("chain_id") == 56:
                    done.add(cid)
                    if cid not in progress["completed"]:
                        progress["completed"].append(cid)
                    continue
            except Exception:
                pass
            # Existing file is ETH — save BSC as separate file
            out_file = out_file_bsc

        # Quick sample to estimate size
        contract = token["contract"]
        # Use a recent 10k block window to estimate activity
        latest_block = CALIBRATION_POINTS[-1][0]  # latest calibration block
        time.sleep(REQUEST_DELAY)
        logs = get_transfer_logs(contract, latest_block - 50000, latest_block)
        count = len(logs) if logs else 0
        estimates[cid] = count

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(bsc_tokens)}] estimated...")

    # Sort by activity (ascending — small first)
    remaining = [t for t in bsc_tokens if t["coin_id"] not in done and t["coin_id"] not in skipped]
    remaining.sort(key=lambda t: estimates.get(t["coin_id"], 0))

    print(f"\nRemaining: {len(remaining)} tokens")
    print(f"Already done: {len(done)}")
    if remaining:
        print(f"Smallest: {remaining[0]['coin_id']} (~{estimates.get(remaining[0]['coin_id'],0)} recent transfers)")
        print(f"Largest: {remaining[-1]['coin_id']} (~{estimates.get(remaining[-1]['coin_id'],0)} recent transfers)")

    # Collect transfers
    for i, token in enumerate(remaining):
        cid = token["coin_id"]
        contract = token["contract"]

        # Compute block range: T-14 to T (peak/event date)
        # For tokens in our dataset, we need to find the peak date from evm_tokens
        # For now, use a default window of recent 14 days
        # We'll refine with actual peak dates from evm_tokens.json later

        # Get event date from bsc_token_dates.json or token data
        if "start_date_override" in token:
            event_ts = int(datetime.strptime(token["start_date_override"], "%Y-%m-%d").timestamp())
        elif cid in bsc_dates:
            # T = start_date for ALL tokens (beginning of pump or dump)
            # We look for leading indicators BEFORE the move starts
            date_str = bsc_dates[cid].get("start_date")
            if date_str:
                event_ts = int(datetime.strptime(date_str, "%Y-%m-%d").timestamp())
            else:
                event_ts = int(time.time()) - 14 * 86400
        else:
            event_ts = int(time.time()) - 14 * 86400

        t_minus_14_ts = event_ts - 14 * 86400
        t_minus_7_ts = event_ts - 7 * 86400
        t_plus_7_ts = event_ts + 7 * 86400

        # Piecewise interpolation (accurate to <1h with 9 calibration points)
        block_start = ts_to_block(t_minus_14_ts)
        block_t7 = ts_to_block(t_minus_7_ts)
        block_t = ts_to_block(event_ts)
        block_end = ts_to_block(t_plus_7_ts)

        print(f"\n[{i+1}/{len(remaining)}] {cid} ({token['symbol']}) cat={token['category']}")
        print(f"  Contract: {contract}")
        print(f"  Blocks: {block_start} → {block_end} ({block_end-block_start} blocks)")

        try:
            transfers = collect_token_transfers(
                contract, block_start, block_end,
                max_transfers=200000,
            )

            if not transfers:
                print(f"  No transfers found — skipping")
                progress["skipped"].append(cid)
                save_progress(progress)
                continue

            # Verify/correct timestamps for first and last transfer
            first_ts = get_block_timestamp(int(transfers[0]["blockNumber"]))
            last_ts = get_block_timestamp(int(transfers[-1]["blockNumber"]))
            time.sleep(REQUEST_DELAY)

            # Save in same format as ETH transfers
            output = {
                "coin_id": cid,
                "symbol": token["symbol"],
                "name": token["name"],
                "category": token["category"],
                "multiplier": token.get("multiplier", 0),
                "chain_id": 56,
                "chain_name": "BSC",
                "contract": contract,
                "event_date": datetime.utcfromtimestamp(event_ts).strftime("%Y-%m-%d"),
                "blocks": {
                    "t_minus_14": block_start,
                    "t_minus_7": block_t7,
                    "t_event": block_t,
                    "t_plus_7": block_end,
                },
                "timestamps": {
                    "t_minus_14": t_minus_14_ts,
                    "t_minus_7": t_minus_7_ts,
                    "t_event": event_ts,
                    "t_plus_7": t_plus_7_ts,
                },
                "transfer_count": len(transfers),
                "transfers": transfers,
            }

            # Use _bsc suffix if ETH version exists
            save_file = TRANSFERS_DIR / f"{cid}.json"
            if save_file.exists():
                try:
                    with open(save_file) as _f:
                        ex = json.load(_f)
                    if ex.get("chain_id") != 56:
                        save_file = TRANSFERS_DIR / f"{cid}_bsc.json"
                except Exception:
                    save_file = TRANSFERS_DIR / f"{cid}_bsc.json"
            with open(save_file, "w") as f:
                json.dump(output, f)

            print(f"  Saved: {len(transfers)} transfers → {save_file}")
            progress["completed"].append(cid)
            save_progress(progress)

        except Exception as e:
            print(f"  ERROR: {e}")
            progress["errors"].append({"coin_id": cid, "error": str(e)})
            save_progress(progress)

    print(f"\n{'='*60}")
    print(f"DONE: {len(progress['completed'])} completed, {len(progress['skipped'])} skipped, {len(progress['errors'])} errors")


if __name__ == "__main__":
    main()
