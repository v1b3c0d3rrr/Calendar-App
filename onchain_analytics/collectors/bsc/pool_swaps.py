"""
Pool swap collector for ACU/USDT PancakeSwap V3 pool.
Fetches Swap events and stores them in the database.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from eth_abi import decode
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from web3 import Web3

from collectors.bsc.abi import PANCAKESWAP_V3_POOL_ABI, SWAP_TOPIC
from collectors.bsc.bscscan_logs import BSCScanClient
from collectors.bsc.connection import BSCConnection, bsc_connection
from config import settings
from db.database import get_db_session
from db.models import Swap, SyncState
from utils.logging import get_logger

logger = get_logger(__name__)

# Constants
COLLECTOR_NAME = "pool_swaps"
Q96 = 2**96


class PoolInfo:
    """Cached pool information."""

    def __init__(self):
        self.token0: Optional[str] = None
        self.token1: Optional[str] = None
        self.acu_is_token0: Optional[bool] = None
        self.fee: Optional[int] = None
        self.initialized = False


pool_info = PoolInfo()


async def initialize_pool_info(conn: BSCConnection) -> PoolInfo:
    """
    Fetch and cache pool token order.
    Critical: need to know if ACU is token0 or token1 for price calculation.
    """
    if pool_info.initialized:
        return pool_info

    # Use sync web3 for reliability
    w3 = conn.get_sync_web3()
    pool_address = Web3.to_checksum_address(settings.pool_address)
    pool_contract = w3.eth.contract(address=pool_address, abi=PANCAKESWAP_V3_POOL_ABI)

    # Fetch token addresses
    await conn.rate_limiter.acquire()
    token0 = pool_contract.functions.token0().call()
    await conn.rate_limiter.acquire()
    token1 = pool_contract.functions.token1().call()

    pool_info.token0 = token0.lower()
    pool_info.token1 = token1.lower()
    pool_info.acu_is_token0 = pool_info.token0 == settings.acu_token_address.lower()
    pool_info.initialized = True

    logger.info(
        f"Pool initialized: token0={pool_info.token0}, token1={pool_info.token1}, "
        f"ACU is token{'0' if pool_info.acu_is_token0 else '1'}"
    )

    return pool_info


def calculate_price_from_sqrt(sqrt_price_x96: int, acu_is_token0: bool) -> Decimal:
    """
    Calculate ACU price in USDT from sqrtPriceX96.

    sqrtPriceX96 = sqrt(price) * 2^96
    price = (sqrtPriceX96 / 2^96)^2

    The raw price is token1/token0.
    We need to adjust for decimal differences and get USDT per ACU.

    In this pool: token0=USDT(18), token1=ACU(12)
    """
    price_ratio = (Decimal(sqrt_price_x96) / Decimal(Q96)) ** 2

    # Decimal adjustment factor
    decimal_adjustment = Decimal(10 ** (settings.usdt_decimals - settings.acu_decimals))

    if acu_is_token0:
        # token0=ACU, token1=USDT
        # raw price is USDT/ACU, adjust for decimals
        return price_ratio * Decimal(10 ** (settings.acu_decimals - settings.usdt_decimals))
    else:
        # token0=USDT, token1=ACU (our case)
        # raw price is ACU/USDT
        # ACU per USDT (real) = raw_price * 10^(usdt_decimals - acu_decimals)
        # USDT per ACU = 1 / (ACU per USDT)
        acu_per_usdt = price_ratio * decimal_adjustment
        return Decimal(1) / acu_per_usdt if acu_per_usdt > 0 else Decimal(0)


def parse_swap_event(log: dict, block_timestamp: int, acu_is_token0: bool) -> dict:
    """
    Parse a Swap event log into a structured dict.
    """
    # Decode non-indexed parameters
    # amount0, amount1, sqrtPriceX96, liquidity, tick
    data = bytes.fromhex(log["data"].hex()[2:]) if isinstance(log["data"], bytes) else bytes.fromhex(log["data"][2:])
    amount0, amount1, sqrt_price_x96, liquidity, tick = decode(
        ["int256", "int256", "uint160", "uint128", "int24"],
        data,
    )

    # Decode indexed parameters (sender, recipient from topics)
    sender = "0x" + log["topics"][1].hex()[-40:]
    recipient = "0x" + log["topics"][2].hex()[-40:]

    # Determine amounts based on token order
    if acu_is_token0:
        amount_acu = Decimal(amount0) / Decimal(10**settings.acu_decimals)
        amount_usdt = Decimal(amount1) / Decimal(10**settings.usdt_decimals)
    else:
        amount_acu = Decimal(amount1) / Decimal(10**settings.acu_decimals)
        amount_usdt = Decimal(amount0) / Decimal(10**settings.usdt_decimals)

    # Calculate price
    price_usdt = calculate_price_from_sqrt(sqrt_price_x96, acu_is_token0)

    # Determine if this is a buy or sell (from ACU holder perspective)
    # Buy: ACU amount is positive (receiving ACU)
    # Sell: ACU amount is negative (sending ACU)
    is_buy = amount_acu > 0

    return {
        "tx_hash": log["transactionHash"].hex() if isinstance(log["transactionHash"], bytes) else log["transactionHash"],
        "block_number": log["blockNumber"],
        "timestamp": datetime.fromtimestamp(block_timestamp, tz=timezone.utc),
        "log_index": log["logIndex"],
        "sender": sender,
        "recipient": recipient,
        "amount_acu": abs(amount_acu),
        "amount_usdt": abs(amount_usdt),
        "price_usdt": price_usdt,
        "is_buy": is_buy,
        "sqrt_price_x96": str(sqrt_price_x96),
        "liquidity": str(liquidity),
        "tick": tick,
    }


async def get_last_synced_block() -> int:
    """Get the last synced block from database."""
    async with get_db_session() as session:
        result = await session.execute(
            select(SyncState.last_block).where(SyncState.collector_name == COLLECTOR_NAME)
        )
        row = result.scalar_one_or_none()
        return row if row else settings.start_block


async def update_sync_state(block_number: int) -> None:
    """Update sync state in database."""
    async with get_db_session() as session:
        stmt = (
            insert(SyncState)
            .values(
                collector_name=COLLECTOR_NAME,
                last_block=block_number,
                last_timestamp=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                index_elements=["collector_name"],
                set_={"last_block": block_number, "updated_at": datetime.now(timezone.utc)},
            )
        )
        await session.execute(stmt)
        await session.commit()


async def save_swaps(swaps: list[dict]) -> int:
    """Save swaps to database, ignoring duplicates."""
    if not swaps:
        return 0

    async with get_db_session() as session:
        # Use upsert to handle duplicates gracefully
        stmt = insert(Swap).values(swaps)
        stmt = stmt.on_conflict_do_nothing(index_elements=["block_number", "log_index"])
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or len(swaps)


async def fetch_swaps_batch(
    conn: BSCConnection,
    from_block: int,
    to_block: int,
) -> list[dict]:
    """
    Fetch swap events for a block range.
    """
    await initialize_pool_info(conn)

    logs = await conn.get_logs(
        address=settings.pool_address,
        from_block=from_block,
        to_block=to_block,
        topics=[SWAP_TOPIC],
    )

    if not logs:
        return []

    # Get block timestamps for all unique blocks
    block_numbers = list(set(log["blockNumber"] for log in logs))
    block_timestamps = {}

    for block_num in block_numbers:
        block = await conn.get_block(block_num)
        block_timestamps[block_num] = block["timestamp"]

    # Parse all swap events
    swaps = []
    for log in logs:
        try:
            swap = parse_swap_event(
                log,
                block_timestamps[log["blockNumber"]],
                pool_info.acu_is_token0,
            )
            swaps.append(swap)
        except Exception as e:
            logger.error(f"Error parsing swap event: {e}, log: {log}")
            continue

    return swaps


async def sync_swaps(
    conn: Optional[BSCConnection] = None,
    batch_size: int = None,
    max_blocks: int = None,
) -> dict:
    """
    Main sync function - fetches new swaps since last sync.

    Args:
        conn: BSC connection (uses global if not provided)
        batch_size: Blocks per batch (default from settings)
        max_blocks: Max blocks to sync (None = sync to current)

    Returns:
        Dict with sync stats
    """
    conn = conn or bsc_connection
    batch_size = batch_size or settings.batch_size

    # Get current state
    last_block = await get_last_synced_block()
    current_block = await conn.get_block_number()

    if max_blocks:
        target_block = min(last_block + max_blocks, current_block)
    else:
        target_block = current_block

    logger.info(f"Syncing swaps from block {last_block} to {target_block}")

    total_swaps = 0
    blocks_processed = 0
    batch_count = 0
    start_block = last_block + 1

    while start_block <= target_block:
        end_block = min(start_block + batch_size - 1, target_block)

        try:
            swaps = await fetch_swaps_batch(conn, start_block, end_block)
            saved = await save_swaps(swaps)
            await update_sync_state(end_block)

            total_swaps += saved
            blocks_processed += end_block - start_block + 1
            batch_count += 1

            if swaps:
                logger.info(
                    f"Blocks {start_block}-{end_block}: {len(swaps)} swaps found, {saved} saved"
                )
            elif batch_count % 100 == 0:
                remaining = target_block - end_block
                logger.info(f"Progress: block {end_block}, {blocks_processed} processed, ~{remaining} remaining")

            start_block = end_block + 1

        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = any(s in error_msg for s in ["429", "rate", "limit", "timeout", "too many"])
            if is_rate_limit:
                logger.warning(f"Rate limited at blocks {start_block}-{end_block}, waiting 60s...")
                await asyncio.sleep(60)
                # Reset connection to primary endpoint
                conn._current_endpoint_idx = 0
                conn._w3 = None
                conn._sync_w3 = None
                continue
            logger.error(f"Error syncing blocks {start_block}-{end_block}: {e}")
            raise

    return {
        "blocks_processed": blocks_processed,
        "swaps_saved": total_swaps,
        "last_block": target_block,
        "current_block": current_block,
    }


async def run_continuous_sync(interval_seconds: int = 3) -> None:
    """
    Run continuous sync loop.
    BSC block time is ~3 seconds.
    """
    logger.info("Starting continuous swap sync...")

    while True:
        try:
            result = await sync_swaps()
            if result["swaps_saved"] > 0:
                logger.info(f"Sync complete: {result['swaps_saved']} new swaps")
        except Exception as e:
            logger.error(f"Sync error: {e}")

        await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# BSCScan-based collection (alternative to RPC — no tight rate limits)
# ---------------------------------------------------------------------------


def normalize_bscscan_log(raw: dict) -> dict:
    """
    Convert a BSCScan log dict to the format expected by parse_swap_event().

    BSCScan returns hex strings; parse_swap_event expects bytes-like objects
    with .hex() method or plain hex strings with "0x" prefix.
    """
    # BSCScan topics come as list of hex strings
    topics = raw.get("topics", [])
    # Ensure topics are plain hex strings (parse_swap_event handles "0x..." strings)
    # We need objects with .hex() — simplest: keep as strings and adapt parsing

    return {
        "data": raw["data"],  # hex string "0x..."
        "topics": topics,     # list of hex strings "0x..."
        "transactionHash": raw["transactionHash"],
        "blockNumber": int(raw["blockNumber"], 16),
        "logIndex": int(raw["logIndex"], 16),
        "timeStamp": int(raw["timeStamp"], 16),
    }


def parse_bscscan_swap(log: dict, acu_is_token0: bool) -> dict:
    """
    Parse a normalized BSCScan Swap log into a swap dict.

    Similar to parse_swap_event() but handles BSCScan string format
    (no .hex() on bytes, timestamps come from the log itself).
    """
    # Decode data (amount0, amount1, sqrtPriceX96, liquidity, tick)
    data_hex = log["data"]
    if data_hex.startswith("0x"):
        data_hex = data_hex[2:]
    data = bytes.fromhex(data_hex)

    amount0, amount1, sqrt_price_x96, liquidity, tick = decode(
        ["int256", "int256", "uint160", "uint128", "int24"],
        data,
    )

    # Topics are hex strings — extract sender and recipient
    topics = log["topics"]
    sender = "0x" + topics[1][-40:]
    recipient = "0x" + topics[2][-40:]

    # Amounts based on token order
    if acu_is_token0:
        amount_acu = Decimal(amount0) / Decimal(10 ** settings.acu_decimals)
        amount_usdt = Decimal(amount1) / Decimal(10 ** settings.usdt_decimals)
    else:
        amount_acu = Decimal(amount1) / Decimal(10 ** settings.acu_decimals)
        amount_usdt = Decimal(amount0) / Decimal(10 ** settings.usdt_decimals)

    price_usdt = calculate_price_from_sqrt(sqrt_price_x96, acu_is_token0)
    is_buy = amount_acu > 0

    return {
        "tx_hash": log["transactionHash"],
        "block_number": log["blockNumber"],
        "timestamp": datetime.fromtimestamp(log["timeStamp"], tz=timezone.utc),
        "log_index": log["logIndex"],
        "sender": sender,
        "recipient": recipient,
        "amount_acu": abs(amount_acu),
        "amount_usdt": abs(amount_usdt),
        "price_usdt": price_usdt,
        "is_buy": is_buy,
        "sqrt_price_x96": str(sqrt_price_x96),
        "liquidity": str(liquidity),
        "tick": tick,
    }


async def detect_pool_token_order() -> bool:
    """
    Determine if ACU is token0 via RPC (needed once).
    Falls back to known value (False — USDT is token0 in this pool).
    """
    if pool_info.initialized:
        return pool_info.acu_is_token0

    try:
        conn = bsc_connection
        await initialize_pool_info(conn)
        return pool_info.acu_is_token0
    except Exception as e:
        logger.warning(
            "Could not detect token order via RPC, using default (ACU is token1)",
            error=str(e),
        )
        # Known for this pool: token0=USDT, token1=ACU
        pool_info.acu_is_token0 = False
        pool_info.initialized = True
        return False


async def sync_swaps_via_bscscan(
    batch_blocks: int = 50000,
    max_blocks: int | None = None,
) -> dict:
    """
    Fetch all historical swaps via BSCScan getLogs API.

    This is much more reliable than RPC for historical data because:
    - BSCScan has no tight block range limits
    - Timestamps are included in each log (no extra get_block calls)
    - Pagination handles large result sets

    Args:
        batch_blocks: Block range per BSCScan query (50k is safe)
        max_blocks: Max blocks to process (None = sync to current)

    Returns:
        Dict with sync stats
    """
    client = BSCScanClient()
    acu_is_token0 = await detect_pool_token_order()

    # Get current sync state
    last_block = await get_last_synced_block()

    # Get current block number via BSCScan-friendly method
    conn = bsc_connection
    try:
        current_block = await conn.get_block_number()
    except Exception:
        # Fallback: use a recent BSCScan request to estimate
        logger.warning("Could not get block number via RPC, using BSCScan")
        first_block = await client.get_first_tx_block(settings.pool_address)
        current_block = first_block + 10_000_000 if first_block else 50_000_000

    if max_blocks:
        target_block = min(last_block + max_blocks, current_block)
    else:
        target_block = current_block

    start_block = last_block + 1
    total_swaps = 0
    total_pages = 0

    logger.info(
        "Starting BSCScan swap sync",
        from_block=start_block,
        to_block=target_block,
        total_blocks=target_block - start_block + 1,
    )

    while start_block <= target_block:
        end_block = min(start_block + batch_blocks - 1, target_block)

        try:
            # Fetch all logs for this block range (handles pagination internally)
            raw_logs = await client.get_all_logs(
                address=settings.pool_address,
                topic0=SWAP_TOPIC,
                from_block=start_block,
                to_block=end_block,
            )

            if raw_logs:
                # Normalize and parse
                swaps = []
                for raw in raw_logs:
                    try:
                        log = normalize_bscscan_log(raw)
                        swap = parse_bscscan_swap(log, acu_is_token0)
                        swaps.append(swap)
                    except Exception as e:
                        logger.error(
                            "Error parsing BSCScan swap log",
                            error=str(e),
                            tx_hash=raw.get("transactionHash", "?"),
                        )
                        continue

                saved = await save_swaps(swaps)
                total_swaps += saved
                total_pages += 1

                logger.info(
                    "BSCScan batch complete",
                    blocks=f"{start_block}-{end_block}",
                    raw_logs=len(raw_logs),
                    parsed=len(swaps),
                    saved=saved,
                    total_swaps=total_swaps,
                )
            else:
                logger.debug(
                    "No swaps in block range",
                    blocks=f"{start_block}-{end_block}",
                )

            # Update sync state after each batch
            await update_sync_state(end_block)

        except Exception as e:
            logger.error(
                "Error in BSCScan batch",
                blocks=f"{start_block}-{end_block}",
                error=str(e),
            )
            raise

        start_block = end_block + 1

    logger.info(
        "BSCScan sync complete",
        total_swaps=total_swaps,
        total_batches=total_pages,
        last_block=target_block,
    )

    return {
        "total_swaps": total_swaps,
        "total_batches": total_pages,
        "last_block": target_block,
        "current_block": current_block,
    }


# CLI entry point
if __name__ == "__main__":
    import sys

    from utils.logging import setup_logging
    setup_logging()

    async def main():
        if "--bscscan" in sys.argv:
            # Historical sync via BSCScan API
            result = await sync_swaps_via_bscscan()
            print(f"BSCScan sync complete: {result}")
        elif "--continuous" in sys.argv:
            await run_continuous_sync()
        else:
            # One-time RPC sync
            result = await sync_swaps()
            print(f"Sync complete: {result}")

    asyncio.run(main())
