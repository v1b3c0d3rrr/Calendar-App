"""
Etherscan v2 API client — single key, multi-chain.

Free plan supports: ETH (1), Polygon (137), Arbitrum (42161), Linea (59144), Scroll (534352)
Paid plan adds: BSC (56), Optimism (10), Base (8453), Avalanche (43114), Fantom (250), etc.

Key endpoints for onchain analysis:
- Token transfers (whale movements, accumulation patterns)
- Event logs (swaps, liquidity events)
- Contract info (source, ABI)
- Block-by-timestamp (align onchain with price data)
- Balance queries
"""

import os
import time
import requests
from typing import Optional
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry

load_dotenv()

API_KEY = os.getenv("ETHERSCAN_API_KEY")
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

# Chain IDs (CoinGecko platform name -> chain_id)
CHAINS = {
    "ethereum": 1,
    "binance-smart-chain": 56,
    "polygon-pos": 137,
    "arbitrum-one": 42161,
    "optimistic-ethereum": 10,
    "base": 8453,
    "avalanche": 43114,
    "fantom": 250,
    "cronos": 25,
    "linea": 59144,
    "scroll": 534352,
    "zksync": 324,
    "blast": 81457,
    "mantle": 5000,
}

# Free-plan chains (tested 2026-03-11)
FREE_CHAINS = {1, 137, 42161, 59144, 534352}

CG_TO_CHAIN_ID = CHAINS.copy()


class ChainNotSupportedError(Exception):
    """Raised when a chain is not available on the current API plan."""
    pass


@sleep_and_retry
@limits(calls=5, period=1)
def _request(chain_id: int, module: str, action: str, **params) -> dict:
    """Rate-limited Etherscan v2 API request."""
    params.update({
        "chainid": chain_id,
        "module": module,
        "action": action,
        "apikey": API_KEY,
    })

    resp = requests.get(ETHERSCAN_V2_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") == "0" and "No transactions found" not in data.get("message", ""):
        result_str = str(data.get("result", ""))
        if "rate limit" in result_str.lower():
            time.sleep(2)
            return _request(chain_id, module, action, **params)
        if "not supported" in result_str.lower() or "upgrade" in result_str.lower():
            raise ChainNotSupportedError(
                f"Chain {chain_id} requires paid plan: {result_str[:100]}"
            )
    return data


def is_chain_available(chain_id: int) -> bool:
    """Check if chain is available on current plan."""
    return chain_id in FREE_CHAINS


# ============================================================
# Token Info
# ============================================================

def get_token_info(chain_id: int, contract: str) -> dict:
    """Get token name, symbol, decimals, total supply."""
    supply_data = _request(chain_id, "stats", "tokensupply", contractaddress=contract)
    source_data = _request(chain_id, "contract", "getsourcecode", address=contract)

    return {
        "contract": contract,
        "chain_id": chain_id,
        "total_supply": supply_data.get("result"),
        "source_info": source_data.get("result", [{}])[0] if isinstance(source_data.get("result"), list) else {},
    }


# ============================================================
# Token Transfers
# ============================================================

def get_token_transfers(
    chain_id: int,
    contract: str,
    start_block: int = 0,
    end_block: int = 99999999,
    page: int = 1,
    offset: int = 100,
    sort: str = "desc",
) -> list:
    """Get ERC-20 token transfer events."""
    data = _request(
        chain_id, "account", "tokentx",
        contractaddress=contract,
        startblock=start_block,
        endblock=end_block,
        page=page,
        offset=offset,
        sort=sort,
    )
    return data.get("result", [])


def get_token_transfers_by_address(
    chain_id: int,
    address: str,
    contract: Optional[str] = None,
    start_block: int = 0,
    end_block: int = 99999999,
    page: int = 1,
    offset: int = 100,
    sort: str = "desc",
) -> list:
    """Get ERC-20 transfers for a specific address."""
    params = {
        "address": address,
        "startblock": start_block,
        "endblock": end_block,
        "page": page,
        "offset": offset,
        "sort": sort,
    }
    if contract:
        params["contractaddress"] = contract
    data = _request(chain_id, "account", "tokentx", **params)
    return data.get("result", [])


def get_normal_transactions(
    chain_id: int,
    address: str,
    start_block: int = 0,
    end_block: int = 99999999,
    page: int = 1,
    offset: int = 100,
    sort: str = "desc",
) -> list:
    """Get normal (ETH/BNB) transactions for an address."""
    data = _request(
        chain_id, "account", "txlist",
        address=address,
        startblock=start_block,
        endblock=end_block,
        page=page,
        offset=offset,
        sort=sort,
    )
    return data.get("result", [])


def get_internal_transactions(
    chain_id: int,
    address: str,
    start_block: int = 0,
    end_block: int = 99999999,
    page: int = 1,
    offset: int = 100,
    sort: str = "desc",
) -> list:
    """Get internal transactions — contract-to-contract calls."""
    data = _request(
        chain_id, "account", "txlistinternal",
        address=address,
        startblock=start_block,
        endblock=end_block,
        page=page,
        offset=offset,
        sort=sort,
    )
    return data.get("result", [])


# ============================================================
# Balance & Supply
# ============================================================

def get_eth_balance(chain_id: int, address: str) -> str:
    """Get native token balance (ETH/MATIC)."""
    data = _request(chain_id, "account", "balance", address=address, tag="latest")
    return data.get("result", "0")


def get_multi_balance(chain_id: int, addresses: list[str]) -> list:
    """Get balances for multiple addresses (max 20)."""
    addr_str = ",".join(addresses[:20])
    data = _request(chain_id, "account", "balancemulti", address=addr_str, tag="latest")
    return data.get("result", [])


def get_token_balance(chain_id: int, contract: str, address: str) -> str:
    """Get ERC-20 token balance for an address."""
    data = _request(
        chain_id, "account", "tokenbalance",
        contractaddress=contract,
        address=address,
        tag="latest",
    )
    return data.get("result", "0")


# ============================================================
# Contract & Logs
# ============================================================

def get_contract_abi(chain_id: int, address: str) -> str:
    """Get verified contract ABI."""
    data = _request(chain_id, "contract", "getabi", address=address)
    return data.get("result", "")


def get_logs(
    chain_id: int,
    address: str,
    from_block: int = 0,
    to_block: int = 99999999,
    topic0: Optional[str] = None,
    page: int = 1,
    offset: int = 1000,
) -> list:
    """Get event logs — the backbone of onchain analysis."""
    params = {
        "address": address,
        "fromBlock": from_block,
        "toBlock": to_block,
        "page": page,
        "offset": offset,
    }
    if topic0:
        params["topic0"] = topic0
    data = _request(chain_id, "logs", "getLogs", **params)
    return data.get("result", [])


# ============================================================
# Block info
# ============================================================

def get_block_by_timestamp(chain_id: int, timestamp: int, closest: str = "before") -> int:
    """Get block number closest to a Unix timestamp."""
    data = _request(
        chain_id, "block", "getblocknobytime",
        timestamp=timestamp,
        closest=closest,
    )
    return int(data.get("result", 0))


# ============================================================
# Utility
# ============================================================

def resolve_chain_id(cg_platform: str) -> Optional[int]:
    """Convert CoinGecko platform name to chain_id."""
    return CG_TO_CHAIN_ID.get(cg_platform)


def test_api():
    """Quick connectivity test on free-plan chains."""
    print("Testing Etherscan v2 API...")
    print(f"  API key: {API_KEY[:8]}...")

    test_chains = [
        ("ETH", 1),
        ("Polygon", 137),
        ("Arbitrum", 42161),
    ]
    for name, cid in test_chains:
        try:
            data = _request(cid, "proxy", "eth_blockNumber")
            block = int(data.get("result", "0x0"), 16)
            print(f"  {name} (chain={cid}): block {block}")
        except Exception as e:
            print(f"  {name} (chain={cid}): FAILED - {e}")

    print("\nFree chains: ETH, Polygon, Arbitrum, Linea, Scroll")
    print("Paid chains: BSC, Optimism, Base, Avalanche, Fantom, etc.")
    print("API OK!")
    return True


if __name__ == "__main__":
    test_api()
