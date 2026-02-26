"""
Wallet profit/loss analysis for ACU token.
Calculates realized and unrealized P&L, entry prices, and holding metrics.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, or_, select

from db.database import get_db_session
from db.models import Holder, Swap


async def get_wallet_trades(address: str, limit: int = 100) -> list[dict]:
    """
    Get all trades for a specific wallet.
    """
    address = address.lower()

    async with get_db_session() as session:
        result = await session.execute(
            select(Swap)
            .where(or_(Swap.sender == address, Swap.recipient == address))
            .order_by(Swap.timestamp.desc())
            .limit(limit)
        )
        swaps = result.scalars().all()

        trades = []
        for s in swaps:
            # Determine if this wallet bought or sold
            is_buyer = s.recipient.lower() == address

            trades.append({
                "tx_hash": s.tx_hash,
                "timestamp": s.timestamp.isoformat(),
                "block_number": s.block_number,
                "type": "buy" if is_buyer else "sell",
                "amount_acu": float(s.amount_acu),
                "amount_usdt": float(s.amount_usdt),
                "price_usdt": float(s.price_usdt),
            })

        return trades


async def calculate_wallet_pnl(address: str, current_price: Optional[Decimal] = None) -> dict:
    """
    Calculate profit/loss for a wallet using FIFO method.

    Returns:
        - Total bought/sold amounts and values
        - Average buy price
        - Realized P&L (from sales)
        - Unrealized P&L (current holdings)
        - Total P&L
    """
    address = address.lower()

    async with get_db_session() as session:
        # Get all swaps involving this wallet, ordered by time
        result = await session.execute(
            select(Swap)
            .where(or_(Swap.sender == address, Swap.recipient == address))
            .order_by(Swap.timestamp.asc())
        )
        swaps = result.scalars().all()

        if not swaps:
            return {
                "address": address,
                "error": "No trades found",
            }

        # Track purchases for FIFO P&L calculation
        # Each purchase: (amount_remaining, price)
        purchase_queue: list[tuple[Decimal, Decimal]] = []

        total_bought_acu = Decimal(0)
        total_bought_usdt = Decimal(0)
        total_sold_acu = Decimal(0)
        total_sold_usdt = Decimal(0)
        realized_pnl = Decimal(0)

        first_trade_time = None
        last_trade_time = None

        for swap in swaps:
            is_buyer = swap.recipient.lower() == address

            if first_trade_time is None:
                first_trade_time = swap.timestamp
            last_trade_time = swap.timestamp

            if is_buyer:
                # Buy: add to purchase queue
                total_bought_acu += swap.amount_acu
                total_bought_usdt += swap.amount_usdt
                purchase_queue.append((swap.amount_acu, swap.price_usdt))
            else:
                # Sell: calculate realized P&L using FIFO
                total_sold_acu += swap.amount_acu
                total_sold_usdt += swap.amount_usdt

                sell_amount = swap.amount_acu
                sell_price = swap.price_usdt

                while sell_amount > 0 and purchase_queue:
                    buy_amount, buy_price = purchase_queue[0]

                    if buy_amount <= sell_amount:
                        # Use entire purchase lot
                        realized_pnl += buy_amount * (sell_price - buy_price)
                        sell_amount -= buy_amount
                        purchase_queue.pop(0)
                    else:
                        # Partial use of purchase lot
                        realized_pnl += sell_amount * (sell_price - buy_price)
                        purchase_queue[0] = (buy_amount - sell_amount, buy_price)
                        sell_amount = Decimal(0)

        # Calculate current holdings
        current_holdings = sum(amount for amount, _ in purchase_queue)
        avg_buy_price = Decimal(0)

        if purchase_queue:
            total_cost = sum(amount * price for amount, price in purchase_queue)
            avg_buy_price = total_cost / current_holdings if current_holdings > 0 else Decimal(0)

        # Calculate unrealized P&L
        unrealized_pnl = Decimal(0)
        if current_price and current_holdings > 0:
            unrealized_pnl = current_holdings * (current_price - avg_buy_price)

        # Get holder info
        holder_result = await session.execute(
            select(Holder).where(Holder.address == address)
        )
        holder = holder_result.scalar_one_or_none()

        return {
            "address": address,
            "summary": {
                "total_bought_acu": float(total_bought_acu),
                "total_bought_usdt": float(total_bought_usdt),
                "total_sold_acu": float(total_sold_acu),
                "total_sold_usdt": float(total_sold_usdt),
                "current_holdings_acu": float(current_holdings),
                "avg_buy_price": float(avg_buy_price),
            },
            "pnl": {
                "realized_pnl_usdt": float(realized_pnl),
                "unrealized_pnl_usdt": float(unrealized_pnl) if current_price else None,
                "total_pnl_usdt": float(realized_pnl + unrealized_pnl) if current_price else float(realized_pnl),
                "roi_pct": float(realized_pnl / total_bought_usdt * 100) if total_bought_usdt > 0 else 0,
            },
            "activity": {
                "trade_count": len(swaps),
                "buy_count": sum(1 for s in swaps if s.recipient.lower() == address),
                "sell_count": sum(1 for s in swaps if s.sender.lower() == address),
                "first_trade": first_trade_time.isoformat() if first_trade_time else None,
                "last_trade": last_trade_time.isoformat() if last_trade_time else None,
                "holding_days": (last_trade_time - first_trade_time).days if first_trade_time and last_trade_time else 0,
            },
            "holder_info": {
                "db_balance": float(holder.balance) if holder else None,
                "label": holder.label if holder else None,
                "is_contract": holder.is_contract if holder else None,
            },
        }


async def get_top_profitable_wallets(limit: int = 20) -> list[dict]:
    """
    Get wallets with highest realized P&L.
    Note: This is computationally expensive for many wallets.
    """
    async with get_db_session() as session:
        # Get unique traders
        result = await session.execute(
            select(func.distinct(Swap.recipient)).limit(limit * 2)
        )
        addresses = [row[0] for row in result.fetchall()]

        # Calculate P&L for each (simplified - just compare buy/sell totals)
        wallet_stats = []

        for address in addresses:
            # Get buy totals
            buy_result = await session.execute(
                select(
                    func.sum(Swap.amount_usdt).label("total_usdt"),
                    func.sum(Swap.amount_acu).label("total_acu"),
                ).where(Swap.recipient == address)
            )
            buy_row = buy_result.first()

            # Get sell totals
            sell_result = await session.execute(
                select(
                    func.sum(Swap.amount_usdt).label("total_usdt"),
                    func.sum(Swap.amount_acu).label("total_acu"),
                ).where(Swap.sender == address)
            )
            sell_row = sell_result.first()

            bought_usdt = float(buy_row.total_usdt or 0)
            sold_usdt = float(sell_row.total_usdt or 0)

            # Simple P&L: sold - bought (ignoring current holdings)
            simple_pnl = sold_usdt - bought_usdt

            wallet_stats.append({
                "address": address,
                "bought_usdt": bought_usdt,
                "sold_usdt": sold_usdt,
                "simple_pnl_usdt": simple_pnl,
            })

        # Sort by P&L
        wallet_stats.sort(key=lambda x: x["simple_pnl_usdt"], reverse=True)

        return wallet_stats[:limit]


async def get_top_losers(limit: int = 20) -> list[dict]:
    """
    Get wallets with worst P&L (biggest losses).
    """
    wallets = await get_top_profitable_wallets(limit * 2)
    # Sort by P&L ascending (worst first)
    wallets.sort(key=lambda x: x["simple_pnl_usdt"])
    return wallets[:limit]


async def get_wallet_holding_stats() -> dict:
    """
    Get aggregate statistics about wallet holdings.
    """
    async with get_db_session() as session:
        # Distribution of holding sizes
        result = await session.execute(
            select(
                func.count(Holder.id).label("total_holders"),
                func.sum(Holder.balance).label("total_supply"),
                func.avg(Holder.balance).label("avg_balance"),
                func.max(Holder.balance).label("max_balance"),
                func.min(Holder.balance).filter(Holder.balance > 0).label("min_balance"),
            ).where(Holder.balance > 0)
        )
        row = result.first()

        # Get holders by size tiers
        tiers = [
            ("dust", 0, 100),
            ("small", 100, 1000),
            ("medium", 1000, 10000),
            ("large", 10000, 100000),
            ("whale", 100000, float('inf')),
        ]

        tier_stats = []
        for tier_name, min_bal, max_bal in tiers:
            tier_result = await session.execute(
                select(
                    func.count(Holder.id).label("count"),
                    func.sum(Holder.balance).label("total"),
                ).where(
                    and_(
                        Holder.balance >= min_bal,
                        Holder.balance < max_bal if max_bal != float('inf') else True,
                    )
                )
            )
            tier_row = tier_result.first()
            tier_stats.append({
                "tier": tier_name,
                "min_balance": min_bal,
                "max_balance": max_bal if max_bal != float('inf') else None,
                "holder_count": tier_row.count or 0,
                "total_balance": float(tier_row.total or 0),
            })

        total_supply = float(row.total_supply or 1)

        # Add percentage to tiers
        for tier in tier_stats:
            tier["percentage_of_supply"] = tier["total_balance"] / total_supply * 100

        return {
            "total_holders": row.total_holders or 0,
            "total_supply": total_supply,
            "avg_balance": float(row.avg_balance or 0),
            "max_balance": float(row.max_balance or 0),
            "min_balance": float(row.min_balance or 0),
            "distribution_tiers": tier_stats,
        }


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import json
    import sys

    async def main():
        if len(sys.argv) > 1:
            address = sys.argv[1]
            print(f"=== Wallet P&L: {address} ===")
            pnl = await calculate_wallet_pnl(address)
            print(json.dumps(pnl, indent=2, default=str))
        else:
            print("=== Holding Stats ===")
            stats = await get_wallet_holding_stats()
            print(json.dumps(stats, indent=2, default=str))

            print("\n=== Top Profitable Wallets ===")
            top = await get_top_profitable_wallets(10)
            for w in top:
                print(f"  {w['address'][:10]}... P&L: ${w['simple_pnl_usdt']:,.2f}")

    asyncio.run(main())
