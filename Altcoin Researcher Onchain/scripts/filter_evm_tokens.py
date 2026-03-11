"""
Filter Alt Boss calibration tokens for EVM-compatible chains.
Queries CoinGecko /coins/{id} for platform data, saves EVM tokens.
"""

import json
import os
import time
import requests
from pathlib import Path

# CoinGecko API
CG_API_KEY = "CG-eeDr2ysuZoJe631HW3b4JK3j"
CG_BASE = "https://api.coingecko.com/api/v3"
HEADERS = {"x-cg-demo-api-key": CG_API_KEY}

# EVM-compatible platform IDs on CoinGecko
EVM_PLATFORMS = {
    "ethereum", "binance-smart-chain", "polygon-pos", "arbitrum-one",
    "optimistic-ethereum", "avalanche", "base", "fantom", "cronos",
    "gnosis", "celo", "moonbeam", "moonriver", "harmony-shard-0",
    "aurora", "boba", "metis-andromeda", "linea", "scroll",
    "zksync", "polygon-zkevm", "mantle", "blast", "manta-pacific",
    "zkfair", "mode", "sei-network",  # sei v2 is EVM-compatible
}

# Paths
CALIBRATION_DIR = Path(__file__).parent.parent.parent / "Alt Boss" / "calibration"
DATA_DIR = Path(__file__).parent.parent / "data"
PROGRESS_FILE = DATA_DIR / "evm_filter_progress.json"
OUTPUT_FILE = DATA_DIR / "evm_tokens.json"


def load_all_coin_ids():
    """Extract all unique coin_ids from candidates_clean.json."""
    with open(CALIBRATION_DIR / "candidates_clean.json") as f:
        data = json.load(f)

    tokens = {}
    for category in ["pure_winners", "pump_and_dump", "losers"]:
        for t in data.get(category, []):
            cid = t["coin_id"]
            tokens[cid] = {
                "coin_id": cid,
                "symbol": t["symbol"],
                "name": t["name"],
                "category": category,
                "multiplier": t.get("multiplier"),
                "start_mc": t.get("start_mc"),
                "peak_mc": t.get("peak_mc"),
            }
    return tokens


def load_progress():
    """Load progress to resume interrupted runs."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"queried": {}, "errors": []}


def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def query_coin_platforms(coin_id: str) -> dict:
    """Get platform/contract data from CoinGecko."""
    url = f"{CG_BASE}/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }
    resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    platforms = data.get("platforms", {})
    # detail_platforms has chain names + contract addresses
    detail = data.get("detail_platforms", {})
    categories = data.get("categories", [])
    description = data.get("description", {}).get("en", "")[:300]

    return {
        "platforms": platforms,
        "detail_platforms": detail,
        "categories": categories,
        "description_snippet": description,
        "asset_platform_id": data.get("asset_platform_id"),
    }


def main():
    tokens = load_all_coin_ids()
    progress = load_progress()
    queried = progress["queried"]

    print(f"Total unique tokens: {len(tokens)}")
    print(f"Already queried: {len(queried)}")

    to_query = [cid for cid in tokens if cid not in queried]
    print(f"Remaining: {len(to_query)}")

    for i, cid in enumerate(to_query):
        try:
            print(f"[{i+1}/{len(to_query)}] {cid}...", end=" ", flush=True)
            result = query_coin_platforms(cid)
            queried[cid] = result
            print(f"platforms: {list(result['platforms'].keys())}")

            # Save progress every 20 tokens
            if (i + 1) % 20 == 0:
                save_progress(progress)

            # CoinGecko demo: ~30 req/min => 2s between calls
            time.sleep(2.1)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("RATE LIMITED, waiting 60s...")
                save_progress(progress)
                time.sleep(60)
                # retry this one
                try:
                    result = query_coin_platforms(cid)
                    queried[cid] = result
                    print(f"  retry OK: {list(result['platforms'].keys())}")
                except Exception as e2:
                    print(f"  retry FAILED: {e2}")
                    progress["errors"].append({"coin_id": cid, "error": str(e2)})
            elif e.response.status_code == 404:
                print(f"NOT FOUND (delisted?)")
                queried[cid] = {"platforms": {}, "not_found": True}
            else:
                print(f"HTTP {e.response.status_code}")
                progress["errors"].append({"coin_id": cid, "error": str(e)})
        except Exception as e:
            print(f"ERROR: {e}")
            progress["errors"].append({"coin_id": cid, "error": str(e)})

    save_progress(progress)

    # Filter EVM tokens
    evm_tokens = []
    non_evm = []

    for cid, token_info in tokens.items():
        platform_data = queried.get(cid, {})
        platforms = set(platform_data.get("platforms", {}).keys())
        evm_chains = platforms & EVM_PLATFORMS

        if evm_chains:
            # Get contract addresses for EVM chains
            contracts = {}
            detail = platform_data.get("detail_platforms", {})
            for chain in evm_chains:
                addr = platform_data["platforms"].get(chain, "")
                if addr:
                    contracts[chain] = addr

            evm_tokens.append({
                **token_info,
                "evm_chains": sorted(evm_chains),
                "contracts": contracts,
                "all_platforms": sorted(platforms),
                "categories": platform_data.get("categories", []),
                "asset_platform_id": platform_data.get("asset_platform_id"),
            })
        else:
            non_evm.append({
                **token_info,
                "platforms": sorted(platforms),
            })

    # Sort by category then symbol
    evm_tokens.sort(key=lambda x: (x["category"], x["symbol"]))

    output = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_candidates": len(tokens),
        "evm_count": len(evm_tokens),
        "non_evm_count": len(non_evm),
        "evm_tokens": evm_tokens,
        "non_evm_tokens": non_evm,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Total tokens: {len(tokens)}")
    print(f"  EVM tokens: {len(evm_tokens)}")
    print(f"  Non-EVM: {len(non_evm)}")
    print(f"\nEVM by chain:")
    chain_counts = {}
    for t in evm_tokens:
        for c in t["evm_chains"]:
            chain_counts[c] = chain_counts.get(c, 0) + 1
    for chain, count in sorted(chain_counts.items(), key=lambda x: -x[1]):
        print(f"  {chain}: {count}")

    print(f"\nEVM by category:")
    cat_counts = {}
    for t in evm_tokens:
        cat_counts[t["category"]] = cat_counts.get(t["category"], 0) + 1
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print(f"\nSaved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
