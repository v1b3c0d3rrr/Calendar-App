"""
Resolve chain duplicates: when a token exists on both ETH and BSC,
keep the version with more transfers (higher liquidity/activity).

For tokens only on one chain, keep as-is.
For duplicates: compare transfer_count, keep the better one,
rename the other to {coin_id}_alt.json (backup).
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TRANSFERS_DIR = DATA_DIR / "transfers"


def resolve_duplicates():
    """Find and resolve chain duplicates."""
    # Group files by coin_id
    files_by_coin = {}
    for f in sorted(TRANSFERS_DIR.glob("*.json")):
        stem = f.stem
        # Strip _bsc suffix to get coin_id
        coin_id = stem.replace("_bsc", "")
        if coin_id not in files_by_coin:
            files_by_coin[coin_id] = []
        files_by_coin[coin_id].append(f)

    duplicates = {k: v for k, v in files_by_coin.items() if len(v) > 1}
    print(f"Total coin_ids: {len(files_by_coin)}")
    print(f"Duplicates (both ETH and BSC): {len(duplicates)}")

    resolved = 0
    for coin_id, files in duplicates.items():
        # Load all versions
        versions = []
        for f in files:
            with open(f) as fh:
                d = json.load(fh)
            versions.append({
                "file": f,
                "chain": d.get("chain_name", "unknown"),
                "chain_id": d.get("chain_id", 0),
                "transfers": d.get("transfer_count", 0),
            })

        # Sort by transfer count (descending)
        versions.sort(key=lambda v: v["transfers"], reverse=True)
        best = versions[0]
        others = versions[1:]

        print(f"\n{coin_id}:")
        for v in versions:
            marker = " <-- BEST" if v == best else ""
            print(f"  {v['chain']} ({v['file'].name}): {v['transfers']} transfers{marker}")

        # If best is _bsc file, swap: rename _bsc to main, main to _alt
        if "_bsc" in best["file"].name:
            # BSC version is better — make it the main file
            main_file = TRANSFERS_DIR / f"{coin_id}.json"
            alt_file = TRANSFERS_DIR / f"{coin_id}_alt.json"
            bsc_file = best["file"]

            # Rename existing main to _alt
            if main_file.exists():
                main_file.rename(alt_file)
            # Rename _bsc to main
            bsc_file.rename(main_file)
            print(f"  -> Swapped: BSC is now main, ETH moved to _alt")
        else:
            # ETH version is better — rename BSC to _alt
            for other in others:
                alt_file = TRANSFERS_DIR / f"{coin_id}_alt.json"
                other["file"].rename(alt_file)
            print(f"  -> ETH is main, BSC moved to _alt")

        resolved += 1

    print(f"\nResolved {resolved} duplicates")

    # Summary
    main_files = list(TRANSFERS_DIR.glob("*.json"))
    main_files = [f for f in main_files if "_alt" not in f.name]
    chain_counts = {}
    for f in main_files:
        with open(f) as fh:
            d = json.load(fh)
        chain = d.get("chain_name", "unknown")
        chain_counts[chain] = chain_counts.get(chain, 0) + 1
    print(f"\nFinal main files by chain: {json.dumps(chain_counts)}")


if __name__ == "__main__":
    resolve_duplicates()
