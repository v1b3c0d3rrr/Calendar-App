"""
Whale tracking and large transaction analysis for ACU token.
Identifies whales, tracks their movements, and generates alerts.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, or_, select

from db.database import get_db_session
from db.models import Holder, Swap, Transfer


# Whale thresholds (configurable)
WHALE_BALANCE_THRESHOLD = Decimal(100_000)  # 100k ACU to be considered a whale
LARGE_TRADE_THRESHOLD_USDT = Decimal(1_000)  # $1k+ trade is "large"
LARGE_TRADE_THRESHOLD_ACU = Decimal(10_000)  # 10k ACU trade is "large"


async def get_whales(
    min_balance: Optional[Decimal] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Get list of whale wallets (top holders).
    """
    min_balance = min_balance or WHALE_BALANCE_THRESHOLD

    async with get_db_session() as session:
        # Get total supply for percentage calculation
        total_result = await session.execute(
            select(func.sum(Holder.balance)).where(Holder.balance > 0)
        )
        total_supply = total_result.scalar_one_or_none() or Decimal(1)

        # Get top holders
        result = await session.execute(
            select(Holder)
            .where(Holder.balance >= min_balance)
            .order_by(Holder.balance.desc())
            .limit(limit)
        )
        holders = result.scalars().all()

        whales = []
        for h in holders:
            whales.append({
                "address": h.address,
                "balance": float(h.balance),
                "percentage_of_supply": float(h.balance / total_supply * 100),
                "trade_count": h.trade_count,
                "first_seen": h.first_seen.isoformat(),
                "last_active": h.last_active.isoformat(),
                "label": h.label,
                "is_contract": h.is_contract,
            })

        return whales


async def get_whale_concentration() -> dict:
    """
    Calculate whale concentration metrics.
    """
    async with get_db_session() as session:
        # Get total supply
        total_result = await session.execute(
            select(func.sum(Holder.balance)).where(Holder.balance > 0)
        )
        total_supply = total_result.scalar_one_or_none() or Decimal(1)

        # Top 10 holders
        top10_holders = await session.execute(
            select(Holder.balance)
            .where(Holder.balance > 0)
            .order_by(Holder.balance.desc())
            .limit(10)
        )
        top10_balances = [row[0] for row in top10_holders.fetchall()]
        top10_total = sum(top10_balances)

        # Top 50 holders
        top50_holders = await session.execute(
            select(Holder.balance)
            .where(Holder.balance > 0)
            .order_by(Holder.balance.desc())
            .limit(50)
        )
        top50_balances = [row[0] for row in top50_holders.fetchall()]
        top50_total = sum(top50_balances)

        # Whale holders (above threshold)
        whale_result = await session.execute(
            select(
                func.count(Holder.id).label("count"),
                func.sum(Holder.balance).label("total"),
            ).where(Holder.balance >= WHALE_BALANCE_THRESHOLD)
        )
        whale_row = whale_result.first()

        return {
            "total_supply": float(total_supply),
            "top_10": {
                "total_balance": float(top10_total),
                "percentage": float(top10_total / total_supply * 100),
            },
            "top_50": {
                "total_balance": float(top50_total),
                "percentage": float(top50_total / total_supply * 100),
            },
            "whales": {
                "threshold": float(WHALE_BALANCE_THRESHOLD),
                "count": whale_row.count or 0,
                "total_balance": float(whale_row.total or 0),
                "percentage": float((whale_row.total or 0) / total_supply * 100),
            },
        }


async def get_large_trades(
    hours: int = 24,
    min_usdt: Optional[Decimal] = None,
    min_acu: Optional[Decimal] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Get large trades (potential whale activity).
    """
    min_usdt = min_usdt or LARGE_TRADE_THRESHOLD_USDT
    min_acu = min_acu or LARGE_TRADE_THRESHOLD_ACU

    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await session.execute(
            select(Swap)
            .where(
                and_(
                    Swap.timestamp >= cutoff,
                    or_(
                        Swap.amount_usdt >= min_usdt,
                        Swap.amount_acu >= min_acu,
                    ),
                )
            )
            .order_by(Swap.amount_usdt.desc())
            .limit(limit)
        )
        swaps = result.scalars().all()

        trades = []
        for s in swaps:
            trades.append({
                "tx_hash": s.tx_hash,
                "timestamp": s.timestamp.isoformat(),
                "type": "buy" if s.is_buy else "sell",
                "amount_acu": float(s.amount_acu),
                "amount_usdt": float(s.amount_usdt),
                "price_usdt": float(s.price_usdt),
                "sender": s.sender,
                "recipient": s.recipient,
            })

        return trades


async def get_whale_activity(hours: int = 24) -> list[dict]:
    """
    Get recent trading activity from whale wallets.
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Get whale addresses
        whale_result = await session.execute(
            select(Holder.address).where(Holder.balance >= WHALE_BALANCE_THRESHOLD)
        )
        whale_addresses = [row[0] for row in whale_result.fetchall()]

        if not whale_addresses:
            return []

        # Get their recent trades
        result = await session.execute(
            select(Swap)
            .where(
                and_(
                    Swap.timestamp >= cutoff,
                    or_(
                        Swap.sender.in_(whale_addresses),
                        Swap.recipient.in_(whale_addresses),
                    ),
                )
            )
            .order_by(Swap.timestamp.desc())
            .limit(100)
        )
        swaps = result.scalars().all()

        whale_set = set(whale_addresses)
        activity = []

        for s in swaps:
            whale_addr = s.recipient if s.recipient in whale_set else s.sender
            is_buying = s.recipient in whale_set

            activity.append({
                "tx_hash": s.tx_hash,
                "timestamp": s.timestamp.isoformat(),
                "whale_address": whale_addr,
                "action": "buy" if is_buying else "sell",
                "amount_acu": float(s.amount_acu),
                "amount_usdt": float(s.amount_usdt),
                "price_usdt": float(s.price_usdt),
            })

        return activity


async def get_whale_transfers(hours: int = 24, min_amount: Optional[Decimal] = None) -> list[dict]:
    """
    Get large token transfers (not just swaps).
    Useful for tracking whale wallet-to-wallet movements.
    """
    min_amount = min_amount or LARGE_TRADE_THRESHOLD_ACU

    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await session.execute(
            select(Transfer)
            .where(
                and_(
                    Transfer.timestamp >= cutoff,
                    Transfer.amount >= min_amount,
                )
            )
            .order_by(Transfer.amount.desc())
            .limit(50)
        )
        transfers = result.scalars().all()

        return [
            {
                "tx_hash": t.tx_hash,
                "timestamp": t.timestamp.isoformat(),
                "from_address": t.from_address,
                "to_address": t.to_address,
                "amount": float(t.amount),
            }
            for t in transfers
        ]


async def get_accumulation_wallets(days: int = 7, min_increase_pct: float = 10.0) -> list[dict]:
    """
    Identify wallets that have been accumulating (increasing holdings).
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Get wallets with net positive inflow
        result = await session.execute(
            select(
                Swap.recipient.label("address"),
                func.sum(Swap.amount_acu).label("bought"),
            )
            .where(Swap.timestamp >= cutoff)
            .group_by(Swap.recipient)
            .having(func.sum(Swap.amount_acu) > 0)
            .order_by(func.sum(Swap.amount_acu).desc())
            .limit(50)
        )
        buyers = {row.address: float(row.bought) for row in result.fetchall()}

        # Get their sells
        result = await session.execute(
            select(
                Swap.sender.label("address"),
                func.sum(Swap.amount_acu).label("sold"),
            )
            .where(
                and_(
                    Swap.timestamp >= cutoff,
                    Swap.sender.in_(list(buyers.keys())),
                )
            )
            .group_by(Swap.sender)
        )
        sellers = {row.address: float(row.sold) for row in result.fetchall()}

        # Calculate net accumulation
        accumulators = []
        for address, bought in buyers.items():
            sold = sellers.get(address, 0)
            net = bought - sold

            if net > 0:
                # Get current balance
                holder_result = await session.execute(
                    select(Holder).where(Holder.address == address)
                )
                holder = holder_result.scalar_one_or_none()
                current_balance = float(holder.balance) if holder else 0

                accumulators.append({
                    "address": address,
                    "bought_acu": bought,
                    "sold_acu": sold,
                    "net_accumulated": net,
                    "current_balance": current_balance,
                })

        # Sort by net accumulation
        accumulators.sort(key=lambda x: x["net_accumulated"], reverse=True)

        return accumulators[:20]


async def get_distribution_wallets(days: int = 7) -> list[dict]:
    """
    Identify wallets that have been distributing (decreasing holdings).
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Get wallets with net negative outflow
        result = await session.execute(
            select(
                Swap.sender.label("address"),
                func.sum(Swap.amount_acu).label("sold"),
            )
            .where(Swap.timestamp >= cutoff)
            .group_by(Swap.sender)
            .having(func.sum(Swap.amount_acu) > 0)
            .order_by(func.sum(Swap.amount_acu).desc())
            .limit(50)
        )
        sellers = {row.address: float(row.sold) for row in result.fetchall()}

        # Get their buys
        result = await session.execute(
            select(
                Swap.recipient.label("address"),
                func.sum(Swap.amount_acu).label("bought"),
            )
            .where(
                and_(
                    Swap.timestamp >= cutoff,
                    Swap.recipient.in_(list(sellers.keys())),
                )
            )
            .group_by(Swap.recipient)
        )
        buyers = {row.address: float(row.bought) for row in result.fetchall()}

        # Calculate net distribution
        distributors = []
        for address, sold in sellers.items():
            bought = buyers.get(address, 0)
            net = sold - bought

            if net > 0:
                holder_result = await session.execute(
                    select(Holder).where(Holder.address == address)
                )
                holder = holder_result.scalar_one_or_none()
                current_balance = float(holder.balance) if holder else 0

                distributors.append({
                    "address": address,
                    "sold_acu": sold,
                    "bought_acu": bought,
                    "net_distributed": net,
                    "current_balance": current_balance,
                })

        distributors.sort(key=lambda x: x["net_distributed"], reverse=True)

        return distributors[:20]


async def get_whale_summary() -> dict:
    """
    Get comprehensive whale analysis summary.
    """
    whales = await get_whales(limit=10)
    concentration = await get_whale_concentration()
    large_trades = await get_large_trades(hours=24, limit=10)
    activity = await get_whale_activity(hours=24)

    # Count buy vs sell activity
    whale_buys = sum(1 for a in activity if a["action"] == "buy")
    whale_sells = len(activity) - whale_buys

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "concentration": concentration,
        "top_whales": whales[:5],
        "activity_24h": {
            "total_trades": len(activity),
            "buys": whale_buys,
            "sells": whale_sells,
            "sentiment": "bullish" if whale_buys > whale_sells else "bearish" if whale_sells > whale_buys else "neutral",
        },
        "large_trades_24h": large_trades[:5],
    }


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import json

    async def main():
        print("=== Whale Summary ===")
        summary = await get_whale_summary()
        print(json.dumps(summary, indent=2, default=str))

        print("\n=== Accumulating Wallets (7d) ===")
        accumulators = await get_accumulation_wallets(7)
        for a in accumulators[:5]:
            print(f"  {a['address'][:10]}... +{a['net_accumulated']:,.0f} ACU")

    asyncio.run(main())
