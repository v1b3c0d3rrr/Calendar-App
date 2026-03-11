"""
Collect ERC-20 token transfers for T-14 to T (peak/bottom date).

For each EVM token from calibration data:
1. Compute T-14 and T-7 timestamps
2. Get block numbers via Etherscan block-by-timestamp
3. Collect all ERC-20 transfers in [T-14, T] window
4. Save per-token JSON

Periods:
- T-14 to T-7: baseline (normal activity)
- T-7 to T: pre-pump/pre-dump (signal window)

Only processes tokens on FREE Etherscan chains (ETH=1, Polygon=137, Arbitrum=42161).
BSC (56) requires paid plan but we try it — many tokens are BSC-only.
"""

import json
import os
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from explorer_api import (
    get_block_by_timestamp, get_token_transfers,
    resolve_chain_id, is_chain_available, ChainNotSupportedError,
    FREE_CHAINS, CHAINS,
)

DATA_DIR = Path(__file__).parent.parent / "data"
CALIBRATION_DIR = Path(__file__).parent.parent.parent / "Alt Boss" / "calibration"
TRANSFERS_DIR = DATA_DIR / "transfers"
PROGRESS_FILE = DATA_DIR / "transfer_collection_progress.json"

# Prioritize chains: free first, then paid
CHAIN_PRIORITY = [1, 137, 42161, 59144, 534352, 56, 10, 8453, 43114, 250]


def load_evm_tokens() -> list:
    """Load EVM tokens with their contract addresses and dates."""
    with open(DATA_DIR / "evm_tokens.json") as f:
        data = json.load(f)

    # Load dates from candidates_clean.json
    with open(CALIBRATION_DIR / "candidates_clean.json") as f:
        candidates = json.load(f)

    # Build date lookup: coin_id -> {start_date, peak_date/bottom_date, category}
    date_lookup = {}
    for t in candidates.get("pure_winners", []):
        date_lookup[t["coin_id"]] = {
            "start_date": t["start_date"],
            "event_date": t["start_date"],  # T = start_date (beginning of pump)
            "peak_date": t["peak_date"],
            "category": "winner",
        }
    for t in candidates.get("pump_and_dump", []):
        date_lookup[t["coin_id"]] = {
            "start_date": t["start_date"],
            "event_date": t["start_date"],  # T = start_date
            "peak_date": t["peak_date"],
            "category": "pump_and_dump",
        }
    for t in candidates.get("losers", []):
        date_lookup[t["coin_id"]] = {
            "start_date": t["start_date"],
            "event_date": t["start_date"],  # T = start_date (beginning of dump)
            "peak_date": t.get("bottom_date", t["start_date"]),
            "category": "loser",
        }

    # Merge EVM token data with dates
    tokens = []
    for t in data["evm_tokens"]:
        dates = date_lookup.get(t["coin_id"])
        if not dates:
            continue

        # Pick best chain (prefer free chains)
        best_chain = None
        best_contract = None
        for chain_name in CHAIN_PRIORITY:
            # Convert chain_id back to CoinGecko name
            for cg_name, cid in CHAINS.items():
                if cid == chain_name and cg_name in t.get("contracts", {}):
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


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "errors": [], "skipped": []}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def date_to_timestamp(date_str: str) -> int:
    """Convert YYYY-MM-DD to Unix timestamp (midnight UTC)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp())


def collect_all_transfers(chain_id: int, contract: str, start_block: int, end_block: int) -> list:
    """Collect all transfers with pagination. Returns list of transfer dicts."""
    all_transfers = []
    page = 1
    page_size = 10000  # Etherscan max

    while True:
        try:
            transfers = get_token_transfers(
                chain_id=chain_id,
                contract=contract,
                start_block=start_block,
                end_block=end_block,
                page=page,
                offset=page_size,
                sort="asc",
            )
        except ChainNotSupportedError:
            raise
        except Exception as e:
            print(f"    Error on page {page}: {e}")
            break

        if not transfers or not isinstance(transfers, list):
            break

        all_transfers.extend(transfers)
        print(f"    Page {page}: {len(transfers)} transfers (total: {len(all_transfers)})")

        if len(transfers) < page_size:
            break

        page += 1
        time.sleep(0.3)  # Small delay between pages

    return all_transfers


def process_token(token: dict, progress: dict) -> bool:
    """Collect transfers for a single token. Returns True if successful."""
    coin_id = token["coin_id"]
    chain_id = token["chain_id"]
    contract = token["contract"]
    event_date = token["event_date"]

    # Compute T-14, T-7, T, T+7 timestamps
    # T = start_date (beginning of pump/dump)
    # T-14→T-7: baseline period
    # T-7→T: signal period (leading indicators)
    # T→T+7: confirmation period (what happens after move starts)
    t_event = date_to_timestamp(event_date)
    t_minus_7 = t_event - 7 * 86400
    t_minus_14 = t_event - 14 * 86400
    t_plus_7 = t_event + 7 * 86400

    print(f"  Event date (T): {event_date}, chain: {token['chain_name']} ({chain_id})")
    print(f"  Contract: {contract}")
    print(f"  T-14: {datetime.fromtimestamp(t_minus_14).strftime('%Y-%m-%d')}")
    print(f"  T-7:  {datetime.fromtimestamp(t_minus_7).strftime('%Y-%m-%d')}")
    print(f"  T+7:  {datetime.fromtimestamp(t_plus_7).strftime('%Y-%m-%d')}")

    # Get block numbers
    try:
        block_t14 = get_block_by_timestamp(chain_id, t_minus_14, "after")
        time.sleep(0.3)
        block_t7 = get_block_by_timestamp(chain_id, t_minus_7, "before")
        time.sleep(0.3)
        block_t = get_block_by_timestamp(chain_id, t_event, "before")
        time.sleep(0.3)
        block_t_plus_7 = get_block_by_timestamp(chain_id, t_plus_7, "before")
        time.sleep(0.3)
    except ChainNotSupportedError as e:
        print(f"  SKIP: {e}")
        progress["skipped"].append({"coin_id": coin_id, "reason": str(e)})
        return False
    except Exception as e:
        print(f"  ERROR getting blocks: {e}")
        progress["errors"].append({"coin_id": coin_id, "error": str(e), "phase": "blocks"})
        return False

    print(f"  Blocks: T-14={block_t14}, T-7={block_t7}, T={block_t}, T+7={block_t_plus_7}")

    if block_t14 == 0 or block_t == 0:
        print(f"  SKIP: invalid block numbers")
        progress["skipped"].append({"coin_id": coin_id, "reason": "invalid blocks"})
        return False

    # Collect transfers for full [T-14, T+7] window
    try:
        transfers = collect_all_transfers(chain_id, contract, block_t14, block_t_plus_7)
    except ChainNotSupportedError as e:
        print(f"  SKIP: {e}")
        progress["skipped"].append({"coin_id": coin_id, "reason": str(e)})
        return False
    except Exception as e:
        print(f"  ERROR collecting transfers: {e}")
        progress["errors"].append({"coin_id": coin_id, "error": str(e), "phase": "transfers"})
        return False

    # Save transfer data
    output = {
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
        "blocks": {
            "t_minus_14": block_t14,
            "t_minus_7": block_t7,
            "t_event": block_t,
            "t_plus_7": block_t_plus_7,
        },
        "timestamps": {
            "t_minus_14": t_minus_14,
            "t_minus_7": t_minus_7,
            "t_event": t_event,
            "t_plus_7": t_plus_7,
        },
        "transfer_count": len(transfers),
        "transfers": transfers,
    }

    outfile = TRANSFERS_DIR / f"{coin_id}.json"
    with open(outfile, "w") as f:
        json.dump(output, f)

    print(f"  OK: {len(transfers)} transfers saved to {outfile.name}")
    return True


def main():
    TRANSFERS_DIR.mkdir(parents=True, exist_ok=True)

    tokens = load_evm_tokens()
    progress = load_progress()

    print(f"Total EVM tokens with dates: {len(tokens)}")
    print(f"Already completed: {len(progress['completed'])}")

    # Filter by chain availability and completion
    completed_set = set(progress["completed"])
    skipped_set = {s["coin_id"] for s in progress.get("skipped", [])}

    to_process = [t for t in tokens if t["coin_id"] not in completed_set and t["coin_id"] not in skipped_set]

    # Sort: free chains first, then by category (winners first)
    cat_priority = {"winner": 0, "pump_and_dump": 1, "loser": 2}
    to_process.sort(key=lambda t: (
        0 if t["chain_id"] in FREE_CHAINS else 1,
        cat_priority.get(t["category"], 9),
    ))

    print(f"To process: {len(to_process)}")

    chain_counts = {}
    for t in to_process:
        cn = t["chain_name"]
        chain_counts[cn] = chain_counts.get(cn, 0) + 1
    print(f"By chain: {json.dumps(chain_counts)}")

    cat_counts = {}
    for t in to_process:
        cat_counts[t["category"]] = cat_counts.get(t["category"], 0) + 1
    print(f"By category: {json.dumps(cat_counts)}")

    for i, token in enumerate(to_process):
        print(f"\n[{i+1}/{len(to_process)}] {token['symbol']} ({token['coin_id']}) — {token['category']}")

        success = process_token(token, progress)
        if success:
            progress["completed"].append(token["coin_id"])

        # Save progress every 5 tokens
        if (i + 1) % 5 == 0:
            save_progress(progress)
            print(f"  [Progress saved: {len(progress['completed'])} done, {len(progress.get('skipped', []))} skipped, {len(progress['errors'])} errors]")

    save_progress(progress)
    print(f"\n{'='*60}")
    print(f"DONE: {len(progress['completed'])} completed, {len(progress.get('skipped', []))} skipped, {len(progress['errors'])} errors")


if __name__ == "__main__":
    main()
