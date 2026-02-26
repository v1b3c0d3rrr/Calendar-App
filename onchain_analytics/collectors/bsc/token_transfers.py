"""
ACU token transfer collector and holder tracker.
Fetches Transfer events and maintains holder balances.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from eth_abi import decode
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from collectors.bsc.abi import TRANSFER_TOPIC
from collectors.bsc.connection import BSCConnection, bsc_connection
from config import settings
from db.database import get_db_session
from db.models import Holder, SyncState, Transfer
from utils.logging import get_logger

logger = get_logger(__name__)

COLLECTOR_NAME = "token_transfers"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def parse_transfer_event(log: dict, block_timestamp: int) -> dict:
    """Parse a Transfer event log."""
    # Decode value from data
    data = bytes.fromhex(log["data"].hex()[2:]) if isinstance(log["data"], bytes) else bytes.fromhex(log["data"][2:])
    (value,) = decode(["uint256"], data)

    # Decode from/to from topics
    from_address = "0x" + log["topics"][1].hex()[-40:]
    to_address = "0x" + log["topics"][2].hex()[-40:]

    amount = Decimal(value) / Decimal(10**settings.acu_decimals)

    return {
        "tx_hash": log["transactionHash"].hex() if isinstance(log["transactionHash"], bytes) else log["transactionHash"],
        "block_number": log["blockNumber"],
        "timestamp": datetime.fromtimestamp(block_timestamp, tz=timezone.utc),
        "log_index": log["logIndex"],
        "from_address": from_address.lower(),
        "to_address": to_address.lower(),
        "amount": amount,
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


async def save_transfers(transfers: list[dict]) -> int:
    """Save transfers to database."""
    if not transfers:
        return 0

    async with get_db_session() as session:
        stmt = insert(Transfer).values(transfers)
        stmt = stmt.on_conflict_do_nothing(index_elements=["block_number", "log_index"])
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or len(transfers)


async def update_holder_balances(transfers: list[dict]) -> None:
    """Update holder balances based on transfers."""
    if not transfers:
        return

    async with get_db_session() as session:
        # Group balance changes by address
        balance_changes: dict[str, Decimal] = {}
        first_seen: dict[str, datetime] = {}
        last_active: dict[str, datetime] = {}

        for t in transfers:
            from_addr = t["from_address"]
            to_addr = t["to_address"]
            amount = t["amount"]
            timestamp = t["timestamp"]

            # Skip zero address (mints/burns)
            if from_addr != ZERO_ADDRESS:
                balance_changes[from_addr] = balance_changes.get(from_addr, Decimal(0)) - amount
                if from_addr not in first_seen:
                    first_seen[from_addr] = timestamp
                last_active[from_addr] = timestamp

            if to_addr != ZERO_ADDRESS:
                balance_changes[to_addr] = balance_changes.get(to_addr, Decimal(0)) + amount
                if to_addr not in first_seen:
                    first_seen[to_addr] = timestamp
                last_active[to_addr] = timestamp

        # Update each holder
        for address, change in balance_changes.items():
            # Try to get existing holder
            result = await session.execute(
                select(Holder).where(Holder.address == address)
            )
            holder = result.scalar_one_or_none()

            if holder:
                # Update existing holder
                holder.balance = holder.balance + change
                holder.last_active = last_active[address]
                holder.trade_count = holder.trade_count + 1
            else:
                # Create new holder
                new_holder = Holder(
                    address=address,
                    balance=max(change, Decimal(0)),  # Can't have negative balance for new holder
                    first_seen=first_seen[address],
                    last_active=last_active[address],
                    trade_count=1,
                )
                session.add(new_holder)

        await session.commit()


async def fetch_transfers_batch(
    conn: BSCConnection,
    from_block: int,
    to_block: int,
) -> list[dict]:
    """Fetch transfer events for a block range."""
    logs = await conn.get_logs(
        address=settings.acu_token_address,
        from_block=from_block,
        to_block=to_block,
        topics=[TRANSFER_TOPIC],
    )

    if not logs:
        return []

    # Get block timestamps
    block_numbers = list(set(log["blockNumber"] for log in logs))
    block_timestamps = {}

    for block_num in block_numbers:
        block = await conn.get_block(block_num)
        block_timestamps[block_num] = block["timestamp"]

    # Parse all transfer events
    transfers = []
    for log in logs:
        try:
            transfer = parse_transfer_event(log, block_timestamps[log["blockNumber"]])
            transfers.append(transfer)
        except Exception as e:
            logger.error(f"Error parsing transfer event: {e}, log: {log}")
            continue

    return transfers


async def sync_transfers(
    conn: Optional[BSCConnection] = None,
    batch_size: int = None,
    max_blocks: int = None,
    update_holders: bool = True,
) -> dict:
    """
    Main sync function - fetches new transfers since last sync.
    """
    conn = conn or bsc_connection
    batch_size = batch_size or settings.batch_size

    last_block = await get_last_synced_block()
    current_block = await conn.get_block_number()

    if max_blocks:
        target_block = min(last_block + max_blocks, current_block)
    else:
        target_block = current_block

    logger.info(f"Syncing transfers from block {last_block} to {target_block}")

    total_transfers = 0
    blocks_processed = 0
    start_block = last_block + 1

    while start_block <= target_block:
        end_block = min(start_block + batch_size - 1, target_block)

        try:
            transfers = await fetch_transfers_batch(conn, start_block, end_block)
            saved = await save_transfers(transfers)

            if update_holders and transfers:
                await update_holder_balances(transfers)

            await update_sync_state(end_block)

            total_transfers += saved
            blocks_processed += end_block - start_block + 1

            if transfers:
                logger.info(
                    f"Blocks {start_block}-{end_block}: {len(transfers)} transfers found"
                )

            start_block = end_block + 1

        except Exception as e:
            logger.error(f"Error syncing blocks {start_block}-{end_block}: {e}")
            raise

    return {
        "blocks_processed": blocks_processed,
        "transfers_saved": total_transfers,
        "last_block": target_block,
    }


async def get_top_holders(limit: int = 100) -> list[dict]:
    """Get top ACU holders by balance."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Holder)
            .where(Holder.balance > 0)
            .order_by(Holder.balance.desc())
            .limit(limit)
        )
        holders = result.scalars().all()

        # Calculate total supply for percentage
        total_result = await session.execute(
            select(func.sum(Holder.balance)).where(Holder.balance > 0)
        )
        total_supply = total_result.scalar_one_or_none() or Decimal(1)

        return [
            {
                "address": h.address,
                "balance": float(h.balance),
                "percentage": float(h.balance / total_supply * 100),
                "trade_count": h.trade_count,
                "first_seen": h.first_seen.isoformat(),
                "last_active": h.last_active.isoformat(),
                "label": h.label,
            }
            for h in holders
        ]


async def get_holder_count() -> int:
    """Get total number of holders with positive balance."""
    async with get_db_session() as session:
        result = await session.execute(
            select(func.count(Holder.id)).where(Holder.balance > 0)
        )
        return result.scalar_one() or 0


async def get_holder_stats(address: str) -> Optional[dict]:
    """Get stats for a specific holder."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Holder).where(Holder.address == address.lower())
        )
        holder = result.scalar_one_or_none()

        if not holder:
            return None

        return {
            "address": holder.address,
            "balance": float(holder.balance),
            "total_bought": float(holder.total_bought),
            "total_sold": float(holder.total_sold),
            "trade_count": holder.trade_count,
            "first_seen": holder.first_seen.isoformat(),
            "last_active": holder.last_active.isoformat(),
            "avg_buy_price": float(holder.avg_buy_price) if holder.avg_buy_price else None,
            "label": holder.label,
            "is_contract": holder.is_contract,
        }


async def run_continuous_sync(interval_seconds: int = 3) -> None:
    """Run continuous sync loop."""
    logger.info("Starting continuous transfer sync...")

    while True:
        try:
            result = await sync_transfers()
            if result["transfers_saved"] > 0:
                logger.info(f"Sync complete: {result['transfers_saved']} new transfers")
        except Exception as e:
            logger.error(f"Sync error: {e}")

        await asyncio.sleep(interval_seconds)


# CLI entry point
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    async def main():
        if len(sys.argv) > 1:
            if sys.argv[1] == "--continuous":
                await run_continuous_sync()
            elif sys.argv[1] == "--holders":
                holders = await get_top_holders(20)
                for h in holders:
                    print(f"{h['address']}: {h['balance']:,.2f} ACU ({h['percentage']:.2f}%)")
        else:
            result = await sync_transfers()
            print(f"Sync complete: {result}")

    asyncio.run(main())
