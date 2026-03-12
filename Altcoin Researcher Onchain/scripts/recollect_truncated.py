"""
Re-collect BSC tokens truncated at 10k transfers.
Uses startblock sliding (best practice for Etherscan pagination).
Two API keys alternating for 2x throughput.
"""

import json
import os
import sys
import time
import urllib3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

urllib3.disable_warnings()
load_dotenv()

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSFERS_DIR = DATA_DIR / "transfers"

# Three API keys for 3x throughput (15 req/sec total)
API_KEYS = [
    os.getenv("ETHERSCAN_API_KEY"),
    os.getenv("ETHERSCAN_API_KEY_2"),
    "ZP4XQHMUR7TFKA3947VUDAGICWPA97XUBZ",
]

# Etherscan V2 via IP (DNS broken on this machine)
BASE_URL = "https://23.92.68.154/v2/api"
HEADERS = {"Host": "api.etherscan.io"}


def fetch_transfers(contract, start_block, end_block, api_key, retries=3):
    """Single API call with retry."""
    params = {
        "chainid": 56,
        "module": "account",
        "action": "tokentx",
        "contractaddress": contract,
        "startblock": start_block,
        "endblock": end_block,
        "page": 1,
        "offset": 10000,
        "sort": "asc",
        "apikey": api_key,
    }
    for attempt in range(retries):
        try:
            r = requests.get(BASE_URL, params=params, headers=HEADERS,
                             timeout=15, verify=False)
            data = r.json()
            result = data.get("result")
            if isinstance(result, list):
                return result
            # Rate limit message
            if isinstance(result, str) and "rate" in result.lower():
                time.sleep(1)
                continue
            return []
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(0.5 + attempt)
            else:
                sys.stdout.write(f"    ! timeout at block {start_block}\n")
                sys.stdout.flush()
    return []


def collect_all(contract, start_block, end_block, max_transfers=500000):
    """
    Collect all transfers using startblock sliding.
    page=1, offset=10000, sort=asc. Move startblock = last_block + 1.
    Alternate API keys for 2x speed.
    """
    all_transfers = []
    current_start = start_block
    key_idx = 0
    req_count = 0
    total_range = end_block - start_block

    while current_start <= end_block:
        if len(all_transfers) >= max_transfers:
            print(f"    Hit max ({max_transfers})")
            break

        api_key = API_KEYS[key_idx % len(API_KEYS)]
        key_idx += 1

        batch = fetch_transfers(contract, current_start, end_block, api_key)
        req_count += 1

        if not batch:
            break

        all_transfers.extend(batch)

        if len(batch) < 10000:
            break  # Got everything

        # Slide startblock to last block + 1
        last_block = int(batch[-1]["blockNumber"])
        if last_block + 1 <= current_start:
            # Stuck — too many tx in one block, skip it
            current_start += 1
        else:
            current_start = last_block + 1

        # Rate limit: 5 req/sec per key × 3 keys = 15 req/sec, ~0.07s between
        time.sleep(0.08)

        if req_count % 10 == 0:
            pct = (current_start - start_block) / max(total_range, 1) * 100
            print(f"    [{pct:.0f}%] {len(all_transfers):,} tx, {req_count} reqs", flush=True)

    print(f"    Done: {len(all_transfers):,} transfers, {req_count} reqs", flush=True)
    return all_transfers


def main():
    # Find truncated BSC files (exactly 10k, API-collected)
    truncated = []
    for f in sorted(TRANSFERS_DIR.glob("*.json")):
        with open(f) as fh:
            d = json.load(fh)
        if d.get("chain_id") == 56 and d.get("transfer_count") == 10000:
            if d.get("transfers") and "blockHash" in d["transfers"][0]:
                truncated.append(f)

    # Also include aria-ai if it hit max_transfers and we want to verify
    print(f"Truncated BSC files: {len(truncated)}")

    for i, filepath in enumerate(truncated):
        with open(filepath) as fh:
            data = json.load(fh)

        coin_id = data["coin_id"]
        contract = data["contract"]
        start_block = data["blocks"]["t_minus_14"]
        end_block = data["blocks"]["t_plus_7"]

        print(f"\n[{i+1}/{len(truncated)}] {coin_id} ({data.get('symbol', '?')})")
        print(f"  Blocks: {start_block:,} → {end_block:,} ({end_block - start_block:,} blocks)")

        transfers = collect_all(contract, start_block, end_block)

        if len(transfers) <= 10000:
            print(f"  Same count ({len(transfers)}), keeping")
            continue

        data["transfer_count"] = len(transfers)
        data["transfers"] = transfers

        with open(filepath, "w") as f:
            json.dump(data, f)

        print(f"  UPDATED: {len(transfers):,} (was 10,000)")

    print(f"\n{'='*60}\nDONE!")


if __name__ == "__main__":
    main()
