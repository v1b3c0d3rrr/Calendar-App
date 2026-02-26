"""
Trading metrics analysis for ACU token.
Calculates volume, trade counts, unique traders, and market statistics.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, text

from db.database import get_db_session
from db.models import Holder, Price, Swap


async def get_volume_stats(hours: int = 24) -> dict:
    """
    Get trading volume statistics for the specified time period.
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await session.execute(
            select(
                func.sum(Swap.amount_usdt).label("volume_usdt"),
                func.sum(Swap.amount_acu).label("volume_acu"),
                func.count(Swap.id).label("trade_count"),
                func.count(func.distinct(Swap.sender)).label("unique_buyers"),
                func.count(func.distinct(Swap.recipient)).label("unique_sellers"),
            ).where(Swap.timestamp >= cutoff)
        )
        row = result.first()

        return {
            "period_hours": hours,
            "volume_usdt": float(row.volume_usdt or 0),
            "volume_acu": float(row.volume_acu or 0),
            "trade_count": row.trade_count or 0,
            "unique_buyers": row.unique_buyers or 0,
            "unique_sellers": row.unique_sellers or 0,
        }


async def get_buy_sell_stats(hours: int = 24) -> dict:
    """
    Get buy/sell ratio and volume breakdown.
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        from sqlalchemy import case

        result = await session.execute(
            select(
                func.sum(
                    case((Swap.is_buy == True, Swap.amount_usdt), else_=Decimal(0))
                ).label("buy_volume_usdt"),
                func.sum(
                    case((Swap.is_buy == False, Swap.amount_usdt), else_=Decimal(0))
                ).label("sell_volume_usdt"),
                func.sum(
                    case((Swap.is_buy == True, Swap.amount_acu), else_=Decimal(0))
                ).label("buy_volume_acu"),
                func.sum(
                    case((Swap.is_buy == False, Swap.amount_acu), else_=Decimal(0))
                ).label("sell_volume_acu"),
                func.sum(case((Swap.is_buy == True, 1), else_=0)).label("buy_count"),
                func.count(Swap.id).label("total_count"),
            ).where(Swap.timestamp >= cutoff)
        )
        row = result.first()

        buy_count = int(row.buy_count or 0)
        total_count = row.total_count or 0
        sell_count = total_count - buy_count

        buy_volume = float(row.buy_volume_usdt or 0)
        sell_volume = float(row.sell_volume_usdt or 0)

        # Calculate ratios
        buy_sell_ratio = buy_count / sell_count if sell_count > 0 else float('inf')
        volume_ratio = buy_volume / sell_volume if sell_volume > 0 else float('inf')

        return {
            "period_hours": hours,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_sell_ratio": buy_sell_ratio if buy_sell_ratio != float('inf') else None,
            "buy_volume_usdt": buy_volume,
            "sell_volume_usdt": sell_volume,
            "buy_volume_acu": float(row.buy_volume_acu or 0),
            "sell_volume_acu": float(row.sell_volume_acu or 0),
            "volume_ratio": volume_ratio if volume_ratio != float('inf') else None,
            "net_flow_usdt": buy_volume - sell_volume,
        }


async def get_trade_size_stats(hours: int = 24) -> dict:
    """
    Get trade size statistics (average, median, min, max).
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await session.execute(
            select(
                func.avg(Swap.amount_usdt).label("avg_trade_usdt"),
                func.min(Swap.amount_usdt).label("min_trade_usdt"),
                func.max(Swap.amount_usdt).label("max_trade_usdt"),
                func.avg(Swap.amount_acu).label("avg_trade_acu"),
            ).where(Swap.timestamp >= cutoff)
        )
        row = result.first()

        # Get median using percentile (TimescaleDB/PostgreSQL)
        median_result = await session.execute(
            text("""
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY amount_usdt) as median_usdt
                FROM swaps
                WHERE timestamp >= :cutoff
            """),
            {"cutoff": cutoff}
        )
        median_row = median_result.first()

        return {
            "period_hours": hours,
            "avg_trade_usdt": float(row.avg_trade_usdt or 0),
            "median_trade_usdt": float(median_row.median_usdt or 0) if median_row.median_usdt else 0,
            "min_trade_usdt": float(row.min_trade_usdt or 0),
            "max_trade_usdt": float(row.max_trade_usdt or 0),
            "avg_trade_acu": float(row.avg_trade_acu or 0),
        }


async def get_price_stats(hours: int = 24) -> dict:
    """
    Get price statistics for the period.
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await session.execute(
            select(
                func.min(Swap.price_usdt).label("low"),
                func.max(Swap.price_usdt).label("high"),
            ).where(Swap.timestamp >= cutoff)
        )
        row = result.first()

        # Get open price (first trade in period)
        open_result = await session.execute(
            select(Swap.price_usdt)
            .where(Swap.timestamp >= cutoff)
            .order_by(Swap.timestamp.asc())
            .limit(1)
        )
        open_price = open_result.scalar_one_or_none()

        # Get close price (last trade)
        close_result = await session.execute(
            select(Swap.price_usdt)
            .where(Swap.timestamp >= cutoff)
            .order_by(Swap.timestamp.desc())
            .limit(1)
        )
        close_price = close_result.scalar_one_or_none()

        # Calculate change
        price_change = None
        price_change_pct = None
        if open_price and close_price:
            price_change = float(close_price - open_price)
            price_change_pct = float((close_price - open_price) / open_price * 100)

        return {
            "period_hours": hours,
            "open": float(open_price) if open_price else None,
            "high": float(row.high) if row.high else None,
            "low": float(row.low) if row.low else None,
            "close": float(close_price) if close_price else None,
            "change": price_change,
            "change_pct": price_change_pct,
        }


async def get_hourly_volume(hours: int = 24) -> list[dict]:
    """
    Get hourly volume breakdown.
    """
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await session.execute(
            text("""
                SELECT
                    date_trunc('hour', timestamp) AS hour,
                    SUM(amount_usdt) AS volume_usdt,
                    SUM(amount_acu) AS volume_acu,
                    COUNT(*) AS trade_count,
                    SUM(CASE WHEN is_buy THEN 1 ELSE 0 END) AS buys,
                    SUM(CASE WHEN NOT is_buy THEN 1 ELSE 0 END) AS sells
                FROM swaps
                WHERE timestamp >= :cutoff
                GROUP BY hour
                ORDER BY hour
            """),
            {"cutoff": cutoff}
        )
        rows = result.fetchall()

        return [
            {
                "hour": row.hour.isoformat(),
                "volume_usdt": float(row.volume_usdt or 0),
                "volume_acu": float(row.volume_acu or 0),
                "trade_count": row.trade_count,
                "buys": row.buys,
                "sells": row.sells,
            }
            for row in rows
        ]


async def get_market_overview() -> dict:
    """
    Get comprehensive market overview combining all metrics.
    """
    # Fetch all stats in parallel would be ideal, but for simplicity:
    volume_24h = await get_volume_stats(24)
    volume_7d = await get_volume_stats(168)  # 7 days
    buy_sell = await get_buy_sell_stats(24)
    trade_size = await get_trade_size_stats(24)
    price_stats = await get_price_stats(24)

    # Get holder count
    async with get_db_session() as session:
        holder_result = await session.execute(
            select(func.count(Holder.id)).where(Holder.balance > 0)
        )
        holder_count = holder_result.scalar_one() or 0

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price": {
            "current": price_stats["close"],
            "change_24h": price_stats["change"],
            "change_24h_pct": price_stats["change_pct"],
            "high_24h": price_stats["high"],
            "low_24h": price_stats["low"],
        },
        "volume": {
            "volume_24h_usdt": volume_24h["volume_usdt"],
            "volume_24h_acu": volume_24h["volume_acu"],
            "volume_7d_usdt": volume_7d["volume_usdt"],
            "trades_24h": volume_24h["trade_count"],
            "trades_7d": volume_7d["trade_count"],
        },
        "trading": {
            "buy_count_24h": buy_sell["buy_count"],
            "sell_count_24h": buy_sell["sell_count"],
            "buy_sell_ratio": buy_sell["buy_sell_ratio"],
            "net_flow_usdt": buy_sell["net_flow_usdt"],
            "avg_trade_usdt": trade_size["avg_trade_usdt"],
            "median_trade_usdt": trade_size["median_trade_usdt"],
        },
        "holders": {
            "total_holders": holder_count,
            "unique_traders_24h": volume_24h["unique_buyers"],
        },
    }


async def get_trading_activity_by_hour() -> list[dict]:
    """
    Get trading activity patterns by hour of day (UTC).
    Useful for identifying active trading hours.
    """
    async with get_db_session() as session:
        result = await session.execute(
            text("""
                SELECT
                    EXTRACT(HOUR FROM timestamp) AS hour_of_day,
                    COUNT(*) AS trade_count,
                    SUM(amount_usdt) AS volume_usdt,
                    AVG(amount_usdt) AS avg_trade_usdt
                FROM swaps
                WHERE timestamp >= NOW() - INTERVAL '7 days'
                GROUP BY hour_of_day
                ORDER BY hour_of_day
            """)
        )
        rows = result.fetchall()

        return [
            {
                "hour_utc": int(row.hour_of_day),
                "trade_count": row.trade_count,
                "volume_usdt": float(row.volume_usdt or 0),
                "avg_trade_usdt": float(row.avg_trade_usdt or 0),
            }
            for row in rows
        ]


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import json

    async def main():
        print("=== Market Overview ===")
        overview = await get_market_overview()
        print(json.dumps(overview, indent=2, default=str))

        print("\n=== Hourly Volume (24h) ===")
        hourly = await get_hourly_volume(24)
        for h in hourly[-5:]:  # Last 5 hours
            print(f"  {h['hour']}: ${h['volume_usdt']:,.2f} ({h['trade_count']} trades)")

    asyncio.run(main())
