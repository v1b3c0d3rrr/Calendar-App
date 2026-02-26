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
    start_block = last_block + 1

    while start_block <= target_block:
        end_block = min(start_block + batch_size - 1, target_block)

        try:
            swaps = await fetch_swaps_batch(conn, start_block, end_block)
            saved = await save_swaps(swaps)
            await update_sync_state(end_block)

            total_swaps += saved
            blocks_processed += end_block - start_block + 1

            if swaps:
                logger.info(
                    f"Blocks {start_block}-{end_block}: {len(swaps)} swaps found, {saved} saved"
                )

            start_block = end_block + 1

        except Exception as e:
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


# CLI entry point
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    async def main():
        if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
            await run_continuous_sync()
        else:
            # One-time sync
            result = await sync_swaps()
            print(f"Sync complete: {result}")

    asyncio.run(main())
